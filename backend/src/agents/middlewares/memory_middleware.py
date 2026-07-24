"""Middleware for memory mechanism with goal-anchoring and source-tagged recall."""

import logging
import re
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest
from langgraph.runtime import Runtime

from src.harness.memory import get_harness_memory
from src.runtime.config.memory_config import get_memory_config

logger = logging.getLogger(__name__)
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


def _build_semantic_recall_block(query: str) -> str | None:
    """Return a small, source-tagged recall block from the Harness index."""
    try:
        collected = [
            (entry.score, entry.source_path, entry.content.strip())
            for entry in get_harness_memory().search(query, top_k=4)
            if entry.score >= 0.55
        ]

        if not collected:
            return None

        collected.sort(key=lambda t: t[0], reverse=True)
        lines = ["<recalled_memories>"]
        lines.append("  Note: These are memories from PAST conversations. Verify they are relevant to the current task before using.")

        remaining = 1800
        for _score, source, content in collected[:4]:
            excerpt = content[: min(500, remaining)]
            if not excerpt:
                break
            lines.append(f"- [{source}] {excerpt}")
            remaining -= len(excerpt)

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


def _memory_pipeline_metadata(runtime_context: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {"memory_pipeline": "markdown_pgvector"}
    for key in ("dialogue_route", "project_id"):
        value = runtime_context.get(key)
        if value is not None:
            metadata[key] = value
    return metadata


class MemoryMiddleware(AgentMiddleware[MemoryMiddlewareState]):
    state_schema = MemoryMiddlewareState

    def __init__(self, agent_name: str | None = None):
        super().__init__()
        self._agent_name = agent_name

    def _inject_semantic_memory(self, request: ModelRequest) -> ModelRequest:
        """Inject a bounded set of relevant memories before the model call."""
        try:
            config = get_memory_config()
            if not config.enabled or not config.injection_enabled:
                return request

            query = _extract_user_query_from_messages(list(request.messages))
            recalled = _build_semantic_recall_block(query or "") if query else None
            blocks = [recalled] if recalled else []
            if not blocks:
                return request

            from langchain_core.messages import SystemMessage as _SystemMessage

            messages = list(request.messages)
            insert_at = 0
            for idx, msg in enumerate(messages):
                if getattr(msg, "type", None) == "system":
                    insert_at = idx + 1
                else:
                    break
            messages.insert(insert_at, _SystemMessage(content="\n\n".join(blocks)))
            request.messages = messages
        except Exception as exc:
            logger.debug("Semantic memory injection skipped: %s", exc)
        return request

    @override
    def modify_model_request(self, request: ModelRequest, state: MemoryMiddlewareState, runtime: Runtime) -> ModelRequest:
        return self._inject_semantic_memory(request)

    @override
    async def amodify_model_request(self, request: ModelRequest, state: MemoryMiddlewareState, runtime: Runtime) -> ModelRequest:
        import asyncio

        return await asyncio.to_thread(self._inject_semantic_memory, request)

    @override
    def after_agent(self, state: MemoryMiddlewareState, runtime: Runtime) -> dict | None:
        config = get_memory_config()
        if not config.enabled:
            return None

        runtime_context = runtime.context or {}
        thread_id = runtime_context.get("thread_id")
        if not thread_id:
            logger.info("MemoryMiddleware: No thread_id in context, skipping memory update")
            return None

        messages = state.get("messages", [])
        if not messages:
            logger.info("MemoryMiddleware: No messages in state, skipping memory update")
            return None

        filtered_messages = _filter_messages_for_memory(messages)
        user_messages = [m for m in filtered_messages if getattr(m, "type", None) == "human"]
        assistant_messages = [m for m in filtered_messages if getattr(m, "type", None) == "ai"]

        if not user_messages or not assistant_messages:
            return None

        runtime_state = dict(state.get("runtime") or {})
        memory_metadata = _memory_pipeline_metadata(runtime_context)
        task_state = state.get("task_state")
        if isinstance(task_state, dict) and task_state.get("status") == "completed":
            memory_metadata["task_completed"] = True
            memory_metadata["task_goal"] = str(task_state.get("goal", ""))[:500]
            memory_metadata["task_steps_completed"] = len(task_state.get("completed_steps", []))
            memory_metadata["memory_scope"] = "task_completion_long_term"

        write = get_harness_memory().capture(
            thread_id=thread_id,
            messages=filtered_messages,
            agent_name=self._agent_name,
            metadata=memory_metadata,
        )
        runtime_state["memory_write"] = {
            **write,
            "message_count": len(filtered_messages),
            "thread_id": thread_id,
            "agent_name": self._agent_name,
            "metadata": memory_metadata,
        }

        return {"runtime": runtime_state}

    @override
    async def aafter_agent(self, state: MemoryMiddlewareState, runtime: Runtime) -> dict | None:
        import asyncio

        return await asyncio.to_thread(self.after_agent, state, runtime)
