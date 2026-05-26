"""Middleware for memory mechanism."""

import logging
import re
import threading
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from src.agents.memory.queue import get_memory_queue
from src.runtime.config.memory_config import get_memory_config
from src.utils.messages import message_text as _message_text

logger = logging.getLogger(__name__)
_simplemem_write_lock = threading.Lock()


def _store_simplemem_conversation_async(
    *,
    messages: list[Any],
    thread_id: str,
    agent_name: str | None,
    metadata: dict[str, Any],
) -> None:
    """Store SimpleMem facts outside the LangGraph run completion path."""

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

    thread = threading.Thread(
        target=_worker,
        name=f"octoagent-simplemem-{thread_id[:8]}",
        daemon=True,
    )
    thread.start()


class MemoryMiddlewareState(AgentState):
    """Compatible with the `ThreadState` schema."""

    pass


def _filter_messages_for_memory(messages: list[Any]) -> list[Any]:
    """Filter messages to keep only user inputs and final assistant responses.

    This filters out:
    - Tool messages (intermediate tool call results)
    - AI messages with tool_calls (intermediate steps, not final responses)
    - The <uploaded_files> block injected by UploadsMiddleware into human messages
      (file paths are session-scoped and must not persist in long-term memory).
      The user's actual question is preserved; only turns whose content is entirely
      the upload block (nothing remains after stripping) are dropped along with
      their paired assistant response.

    Only keeps:
    - Human messages (with the ephemeral upload block removed)
    - AI messages without tool_calls (final assistant responses), unless the
      paired human turn was upload-only and had no real user text.

    Args:
        messages: List of all conversation messages.

    Returns:
        Filtered list containing only user inputs and final assistant responses.
    """
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
                # Strip the ephemeral upload block; keep the user's real question.
                stripped = _UPLOAD_BLOCK_RE.sub("", content_str).strip()
                if not stripped:
                    # Nothing left — the entire turn was upload bookkeeping;
                    # skip it and the paired assistant response.
                    skip_next_ai = True
                    continue
                # Rebuild the message with cleaned content so the user's question
                # is still available for memory summarisation.
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
        # Skip tool messages and AI messages with tool_calls

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
    """Build provenance metadata for long-term memory and SystemRAG writes."""
    metadata: dict[str, Any] = {
        "memory_pipeline": "conversation_compress_continue_extract_rag",
        "memory_scope": "system_long_term_candidate",
    }
    for key in (
        "continue_from_thread_id",
        "continue_from_title",
        "continue_cycle_id",
        "continue_cycle_started_at",
        "continue_cycle_base_tokens",
        "dialogue_route",
    ):
        value = runtime_context.get(key)
        if value is not None:
            metadata[key] = value
    for key in (
        "context_cycle_id",
        "context_cycle_started_at",
        "context_cycle_base_tokens",
        "compaction_strategy",
        "compaction_trigger",
        "compaction_saved_tokens",
        "recommended_memory_action",
        "context_pressure",
        "task_phase_id",
        "source_event_id",
        "completed_item_hashes",
        "completed_item_hash",
    ):
        value = runtime_state.get(key)
        if value is not None:
            metadata[key] = value
    if runtime_context.get("continue_trigger") == "continue":
        metadata["continuation_mode"] = "continued"
    return metadata


class MemoryMiddleware(AgentMiddleware[MemoryMiddlewareState]):
    """Middleware that queues conversation for memory update after agent execution.

    This middleware:
    1. After each agent execution, queues the conversation for memory update
    2. Only includes user inputs and final assistant responses (ignores tool calls)
    3. The queue uses debouncing to batch multiple updates together
    4. Memory is updated asynchronously via LLM summarization
    """

    state_schema = MemoryMiddlewareState

    def __init__(self, agent_name: str | None = None):
        """Initialize the MemoryMiddleware.

        Args:
            agent_name: If provided, memory is stored per-agent. If None, uses global memory.
        """
        super().__init__()
        self._agent_name = agent_name

    @override
    def after_agent(self, state: MemoryMiddlewareState, runtime: Runtime) -> dict | None:
        """Queue conversation for memory update after agent completes.

        Args:
            state: The current agent state.
            runtime: The runtime context.

        Returns:
            None (no state changes needed from this middleware).
        """
        config = get_memory_config()
        if not config.enabled:
            return None

        # Get thread ID from runtime context
        runtime_context = runtime.context or {}
        thread_id = runtime_context.get("thread_id")
        if not thread_id:
            print("MemoryMiddleware: No thread_id in context, skipping memory update")
            return None

        # Get messages from state
        messages = state.get("messages", [])
        if not messages:
            print("MemoryMiddleware: No messages in state, skipping memory update")
            return None

        # Filter to only keep user inputs and final assistant responses
        filtered_messages = _filter_messages_for_memory(messages)

        # Only queue if there's meaningful conversation
        # At minimum need one user message and one assistant response
        user_messages = [m for m in filtered_messages if getattr(m, "type", None) == "human"]
        assistant_messages = [m for m in filtered_messages if getattr(m, "type", None) == "ai"]

        if not user_messages or not assistant_messages:
            return None

        runtime_state = dict(state.get("runtime") or {})
        memory_metadata = _memory_pipeline_metadata(runtime_context, runtime_state)

        # Force memory write when context handoff is required
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

        # Enrich metadata with task state if available for better memory context
        task_state = state.get("task_state")
        if isinstance(task_state, dict) and task_state.get("status") == "completed":
            memory_metadata["task_completed"] = True
            memory_metadata["task_goal"] = str(task_state.get("goal", ""))[:500]
            memory_metadata["task_steps_completed"] = len(task_state.get("completed_steps", []))
            memory_metadata["memory_scope"] = "task_completion_long_term"

        # Queue the filtered conversation for memory update
        queue = get_memory_queue()
        queue.add(thread_id=thread_id, messages=filtered_messages, agent_name=self._agent_name, metadata=memory_metadata)
        runtime_state["memory_write"] = {
            "status": "queued",
            "message_count": len(filtered_messages),
            "thread_id": thread_id,
            "agent_name": self._agent_name,
            "metadata": memory_metadata,
        }

        # Store compressed atomic facts via SimpleMem bridge (Stage 1 + 2)
        # in the background. This keeps the visible chat run from waiting on
        # LLM compression, embedding, or DuckDB write locks.
        _store_simplemem_conversation_async(
            messages=filtered_messages,
            thread_id=thread_id,
            agent_name=self._agent_name,
            metadata=memory_metadata,
        )

        return {"runtime": runtime_state}
