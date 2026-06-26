"""Middleware for memory mechanism with goal-anchoring and source-tagged recall."""

import asyncio
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest
from langgraph.runtime import Runtime

from src.agents.memory.queue import get_memory_queue
from src.runtime.config.memory_config import get_memory_config
from src.utils.messages import message_text as _message_text

logger = logging.getLogger(__name__)
_simplemem_write_lock = threading.Lock()
_simplemem_executor = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="simplemem-writer",
)


def _dispatch_simplemem_worker(worker, thread_id: str) -> None:
    def _log_failure(done) -> None:
        try:
            done.result()
        except Exception as exc:
            logger.debug("SimpleMem async write skipped for thread %s: %s", thread_id, exc)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        future = _simplemem_executor.submit(worker)
        future.add_done_callback(_log_failure)
        return

    future = loop.run_in_executor(_simplemem_executor, worker)
    future.add_done_callback(_log_failure)


def _store_simplemem_conversation_async(
    *,
    messages: list[Any],
    thread_id: str,
    agent_name: str | None,
    metadata: dict[str, Any],
) -> None:
    messages_snapshot = list(messages)

    def _worker() -> None:
        try:
            with _simplemem_write_lock:
                from src.agents.memory.simplemem_bridge import get_simplemem_bridge
                bridge = get_simplemem_bridge()
                bridge.store_conversation(
                    messages_snapshot,
                    namespace="conversation_summary",
                    agent_name=agent_name,
                    thread_id=thread_id,
                    metadata=metadata,
                    enable_synthesis=True,
                )
        except Exception as exc:
            logger.debug("SimpleMem async write skipped for thread %s: %s", thread_id, exc)

    _dispatch_simplemem_worker(_worker, thread_id)


def _extract_user_query_from_messages(messages: list) -> str | None:
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human":
            content = getattr(msg, "content", "")
            if isinstance(content, list):
                content = " ".join(p.get("text", "") for p in content if isinstance(p, dict) and "text" in p)
            content = re.sub(r"<uploaded_files>[\s\S]*?</uploaded_files>", "", str(content)).strip()
            if len(content) >= 10:
                return content[:600]
    return None


def _extract_goal_from_context(request: ModelRequest) -> str | None:
    """Extract current task goal from system messages in the request."""
    for msg in request.messages:
        if getattr(msg, "type", None) == "system":
            content = str(getattr(msg, "content", "") or "")
            m = re.search(r'Goal:\s*(.+?)(?:\n|$)', content)
            if m:
                return m.group(1).strip()
            m = re.search(r'Current task:\s*(.+?)(?:\n|$)', content)
            if m:
                return m.group(1).strip()
    return None


def _build_semantic_recall_block(query: str, current_goal: str | None = None) -> str | None:
    """Search SystemRAG semantically and return a compact recall block with source tags.

    Threshold raised to 0.75 to only inject highly relevant memories.
    Each recalled memory includes its source namespace and project context.
    If a current goal is provided, it's injected as a reminder at the top.
    """
    try:
        from src.agents.memory.system_rag_store import get_system_rag_store
        store = get_system_rag_store()

        collected: list[tuple[float, str, str]] = []
        for namespace in ("conversation_summary", "archival_memory", "skill_evolution"):
            for entry in store.search(query, namespace=namespace, top_k=4):
                if entry.score >= 0.75:
                    collected.append((entry.score, namespace, str(entry.content).strip()))

        if not collected and not current_goal:
            return None

        collected.sort(key=lambda t: t[0], reverse=True)
        lines = ["<recalled_memories>"]
        lines.append("  Note: These are memories from PAST conversations. Verify they are relevant to the current task before using.")

        if current_goal:
            lines.append(f"  Current task reminder: {current_goal[:300]}")

        for _score, ns, content in collected[:6]:
            lines.append(f"- [{ns}] {content[:600]}")

        lines.append("</recalled_memories>")
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("Semantic memory recall skipped: %s", exc)
        return None


class MemoryMiddlewareState(AgentState):
    pass


def _filter_messages_for_memory(messages: list[Any]) -> list[Any]:
    _UPLOAD_BLOCK_RE = re.compile(r"<uploaded_files>[\s\S]*?</uploaded_files>\n*", re.IGNORECASE)
    filtered = []
    skip_next_ai = False
    for msg in messages:
        msg_type = getattr(msg, "type", None)
        if msg_type == "human":
            content = getattr(msg, "content", "")
            if isinstance(content, list):
                content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            content_str = str(content)
            if "<uploaded_files>" in content_str:
                stripped = _UPLOAD_BLOCK_RE.sub("", content_str).strip()
                if not stripped:
                    skip_next_ai = True
                    continue
                from copy import copy
                clean_msg = copy(msg)
                clean_msg.content = stripped
                filtered.append(clean_msg)
                skip_next_ai = False
            else:
                filtered.append(msg)
                skip_next_ai = False
        elif msg_type == "ai":
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                if skip_next_ai:
                    skip_next_ai = False
                    continue
                filtered.append(msg)
    return filtered


def _should_skip_heavy_memory_for_fast_turn(
    *,
    runtime_context: dict[str, Any],
    user_messages: list[Any],
    assistant_messages: list[Any],
) -> bool:
    route = runtime_context.get("dialogue_route")
    if isinstance(route, dict):
        route = route.get("kind")
    if route in {"direct_answer", "current_snapshot"}:
        return True
    if runtime_context.get("dialogue_needs_memory") is False:
        return True
    if runtime_context.get("mode") != "flash":
        return False
    if runtime_context.get("thinking_enabled") or runtime_context.get("is_plan_mode"):
        return False
    latest_user = _message_text(user_messages[-1]) if user_messages else ""
    latest_assistant = _message_text(assistant_messages[-1]) if assistant_messages else ""
    if re.search(r"记住|記住|remember|偏好|preference|以后都|always", latest_user, re.IGNORECASE):
        return False
    return len(latest_user) <= 240 and len(latest_assistant) <= 1200


def _memory_pipeline_metadata(runtime_context: dict[str, Any], runtime_state: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "memory_pipeline": "conversation_compress_continue_extract_rag",
        "memory_scope": "system_long_term_candidate",
    }
    for key in (
        "continue_from_thread_id", "continue_from_title", "continue_cycle_id",
        "continue_cycle_started_at", "continue_cycle_base_tokens", "dialogue_route",
    ):
        value = runtime_context.get(key)
        if value is not None:
            metadata[key] = value
    for key in (
        "context_cycle_id", "context_cycle_started_at", "context_cycle_base_tokens",
        "compaction_strategy", "compaction_trigger", "compaction_saved_tokens",
        "recommended_memory_action", "context_pressure",
        "task_phase_id", "source_event_id",
        "completed_item_hashes", "completed_item_hash",
    ):
        value = runtime_state.get(key)
        if value is not None:
            metadata[key] = value
    if runtime_context.get("continue_trigger") == "continue":
        metadata["continuation_mode"] = "continued"
    return metadata


class MemoryMiddleware(AgentMiddleware[MemoryMiddlewareState]):
    state_schema = MemoryMiddlewareState

    def __init__(self, agent_name: str | None = None):
        super().__init__()
        self._agent_name = agent_name

    def _inject_semantic_memory(self, request: ModelRequest) -> ModelRequest:
        """Inject recalled memories with source tags AND current goal reminder."""
        try:
            config = get_memory_config()
            if not config.enabled or not config.injection_enabled:
                return request

            query = _extract_user_query_from_messages(list(request.messages))
            current_goal = _extract_goal_from_context(request)
            if not query and not current_goal:
                return request

            block = _build_semantic_recall_block(query or "", current_goal=current_goal)
            if not block:
                return request

            from langchain_core.messages import SystemMessage as _SystemMessage
            messages = list(request.messages)
            insert_at = 0
            for idx, msg in enumerate(messages):
                if getattr(msg, "type", None) == "system":
                    insert_at = idx + 1
                else:
                    break
            messages.insert(insert_at, _SystemMessage(content=block))
            request.messages = messages
        except Exception as exc:
            logger.debug("Semantic memory injection skipped: %s", exc)
        return request

    @override
    def modify_model_request(
        self, request: ModelRequest, state: MemoryMiddlewareState, runtime: Runtime
    ) -> ModelRequest:
        return self._inject_semantic_memory(request)

    @override
    async def amodify_model_request(
        self, request: ModelRequest, state: MemoryMiddlewareState, runtime: Runtime
    ) -> ModelRequest:
        return self._inject_semantic_memory(request)

    @override
    def after_agent(self, state: MemoryMiddlewareState, runtime: Runtime) -> dict | None:
        config = get_memory_config()
        if not config.enabled:
            return None

        runtime_context = runtime.context or {}
        thread_id = runtime_context.get("thread_id")
        if not thread_id:
            print("MemoryMiddleware: No thread_id in context, skipping memory update")
            return None

        messages = state.get("messages", [])
        if not messages:
            print("MemoryMiddleware: No messages in state, skipping memory update")
            return None

        filtered_messages = _filter_messages_for_memory(messages)
        user_messages = [m for m in filtered_messages if getattr(m, "type", None) == "human"]
        assistant_messages = [m for m in filtered_messages if getattr(m, "type", None) == "ai"]

        if not user_messages or not assistant_messages:
            return None

        runtime_state = dict(state.get("runtime") or {})
        memory_metadata = _memory_pipeline_metadata(runtime_context, runtime_state)
        memory_flush_required = runtime_state.get("memory_flush_required", False)

        if not memory_flush_required and _should_skip_heavy_memory_for_fast_turn(
            runtime_context=runtime_context,
            user_messages=user_messages,
            assistant_messages=assistant_messages,
        ):
            runtime_state["memory_write"] = {
                "status": "skipped_fast_turn",
                "message_count": len(filtered_messages),
                "thread_id": thread_id,
                "agent_name": self._agent_name,
                "metadata": memory_metadata,
            }
            return {"runtime": runtime_state}

        task_state = state.get("task_state")
        if isinstance(task_state, dict) and task_state.get("status") == "completed":
            memory_metadata["task_completed"] = True
            memory_metadata["task_goal"] = str(task_state.get("goal", ""))[:500]
            memory_metadata["task_steps_completed"] = len(task_state.get("completed_steps", []))
            memory_metadata["memory_scope"] = "task_completion_long_term"

        queue = get_memory_queue()
        queue.add(thread_id=thread_id, messages=filtered_messages, agent_name=self._agent_name, metadata=memory_metadata)
        runtime_state["memory_write"] = {
            "status": "queued",
            "message_count": len(filtered_messages),
            "thread_id": thread_id,
            "agent_name": self._agent_name,
            "metadata": memory_metadata,
        }

        _store_simplemem_conversation_async(
            messages=filtered_messages,
            thread_id=thread_id,
            agent_name=self._agent_name,
            metadata=memory_metadata,
        )

        return {"runtime": runtime_state}
