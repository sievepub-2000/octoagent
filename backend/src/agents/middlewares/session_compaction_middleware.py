"""Middleware for session compaction — compresses long context before LLM call.

Integrates the claw-code SessionCompactor into the agent middleware stack.
When context tokens exceed the configured budget, older messages are
summarised to free up the context window.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.runtime import Runtime

from src.runtime.context_budget import (
    SYSTEM_SESSION_CONTINUE_PROMPT,
    MessageTokenLimits,
    copy_message_with_content,
    estimate_message_tokens,
    estimate_text_tokens,
    max_tokens_for_message,
    message_content_text,
    trim_messages_to_budget,
    trim_text_to_token_budget,
    truncate_oversized_messages,
)
from src.storage.session_compaction.compactor import (
    CompactionConfig,
    Message,
    SessionCompactor,
)

logger = logging.getLogger(__name__)
__all__ = ["SYSTEM_SESSION_CONTINUE_PROMPT", "SessionCompactionMiddleware"]

_MAX_TOOL_MESSAGE_TOKENS = 1_200
_MAX_HUMAN_MESSAGE_TOKENS = 5_000
_MAX_ASSISTANT_MESSAGE_TOKENS = 4_000
_CHECKPOINT_MARKER = "OctoAgent long-running context checkpoint"
_MESSAGE_TOKEN_LIMITS = MessageTokenLimits(
    tool=_MAX_TOOL_MESSAGE_TOKENS,
    human=_MAX_HUMAN_MESSAGE_TOKENS,
    ai=_MAX_ASSISTANT_MESSAGE_TOKENS,
    default=_MAX_ASSISTANT_MESSAGE_TOKENS,
)


def _context_cycle_runtime_update(runtime: Runtime) -> dict[str, Any]:
    context = getattr(runtime, "context", None) or {}
    if not isinstance(context, dict):
        return {}
    update: dict[str, Any] = {}
    cycle_id = context.get("continue_cycle_id")
    cycle_started_at = context.get("continue_cycle_started_at")
    cycle_base_tokens = context.get("continue_cycle_base_tokens")
    if cycle_id:
        update["context_cycle_id"] = cycle_id
    if cycle_started_at:
        update["context_cycle_started_at"] = cycle_started_at
    if isinstance(cycle_base_tokens, int | float):
        update["context_cycle_base_tokens"] = int(cycle_base_tokens)
    if context.get("continue_trigger") == "continue":
        update["continuation_mode"] = "continued"
        update["recommended_memory_action"] = "continue"
    return update


def _estimate_tokens(text: str) -> int:
    return estimate_text_tokens(text, minimum=1)


def _content_to_text(content: Any) -> str:
    return message_content_text({"content": content})


def _normalise_task_item(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("content", "title", "text", "description", "summary", "id"):
            candidate = value.get(key)
            if candidate:
                value = candidate
                break
    return " ".join(str(value or "").strip().split())


def _completed_item_hash(value: Any) -> str:
    normalised = _normalise_task_item(value).casefold()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16]


def _dedupe_task_items(values: Any) -> list[str]:
    if not isinstance(values, list | tuple):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = _normalise_task_item(value)
        if not item:
            continue
        item_hash = _completed_item_hash(item)
        if item_hash in seen:
            continue
        seen.add(item_hash)
        result.append(item)
    return result


def _todo_item_text(todo: dict[str, Any]) -> str:
    return _normalise_task_item(todo)


def _merge_task_progress_state(state: AgentState) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Merge todo completion into task_state before compaction/memory handoff.

    Context compaction used to summarise first and only then let memory extract
    completed work.  That ordering made completed todos look like fresh pending
    instructions in the next context cycle.  This helper creates a stable phase
    identity and completed-item hash registry before any summary is generated.
    """
    raw_task_state = state.get("task_state")
    task_state: dict[str, Any] = dict(raw_task_state) if isinstance(raw_task_state, dict) else {}

    completed_seed = list(task_state.get("completed_steps") or [])
    pending_seed = list(task_state.get("pending_steps") or [])
    todos = state.get("todos") or []
    if isinstance(todos, list):
        for todo in todos:
            if not isinstance(todo, dict):
                continue
            text = _todo_item_text(todo)
            if not text:
                continue
            status = str(todo.get("status") or "").strip().lower()
            if status in {"completed", "complete", "done", "success", "succeeded", "closed", "resolved"}:
                completed_seed.append(text)
            elif status in {"pending", "todo", "open", "in_progress", "in-progress", "running", "active"}:
                pending_seed.append(text)

    completed_steps = _dedupe_task_items(completed_seed)
    completed_hashes = [_completed_item_hash(item) for item in completed_steps]
    completed_hash_set = set(completed_hashes)
    pending_steps = [
        item
        for item in _dedupe_task_items(pending_seed)
        if _completed_item_hash(item) not in completed_hash_set
    ]

    if completed_steps:
        task_state["completed_steps"] = completed_steps
    if pending_steps:
        task_state["pending_steps"] = pending_steps
    elif "pending_steps" in task_state:
        task_state["pending_steps"] = []
    if completed_steps and not task_state.get("status"):
        task_state["status"] = "active"

    runtime_state = state.get("runtime") or {}
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    goal = _normalise_task_item(task_state.get("goal") or runtime_state.get("task_goal"))
    phase_seed = "|".join([goal, *completed_hashes[:24], *pending_steps[:12]]) or "octoagent-task-phase"
    task_phase_id = (
        runtime_state.get("task_phase_id")
        or runtime_state.get("context_cycle_id")
        or f"task-phase-{hashlib.sha256(phase_seed.encode('utf-8')).hexdigest()[:12]}"
    )
    source_seed = "|".join([str(task_phase_id), *completed_hashes[:32], _normalise_task_item(task_state.get("next_action"))])
    source_event_id = runtime_state.get("source_event_id") or f"compaction-event-{hashlib.sha256(source_seed.encode('utf-8')).hexdigest()[:16]}"

    metadata: dict[str, Any] = {
        "task_phase_id": task_phase_id,
        "source_event_id": source_event_id,
    }
    if completed_hashes:
        metadata["completed_item_hashes"] = completed_hashes

    if not task_state and not completed_hashes:
        return None, metadata
    return task_state, metadata


def _append_phase_review(summary_message: str, task_state: dict[str, Any] | None) -> str:
    task_state_summary = _format_task_state_checkpoint(task_state)
    if not task_state_summary:
        return summary_message
    return "\n\n".join([summary_message, "[Compaction phase task review]\n" + task_state_summary])


def _format_task_state_checkpoint(task_state: Any) -> str:
    """Render persistent task state into a compact compaction checkpoint."""
    if not isinstance(task_state, dict):
        return ""
    goal = str(task_state.get("goal") or "").strip()
    if not goal:
        return ""
    lines = ["Persistent task state:", f"- Goal: {goal[:1200]}"]
    status = str(task_state.get("status") or "active").strip()
    if status:
        lines.append(f"- Status: {status}")
    current_step = str(task_state.get("current_step") or "").strip()
    if current_step:
        lines.append(f"- Current step: {current_step[:800]}")
    next_action = str(task_state.get("next_action") or "").strip()
    if next_action:
        lines.append(f"- Next action: {next_action[:800]}")
    for label, key in (
        ("Completed", "completed_steps"),
        ("Pending", "pending_steps"),
        ("Failed attempts", "failed_attempts"),
    ):
        values = [str(item).strip() for item in task_state.get(key, []) if str(item).strip()]
        if values:
            lines.append(f"- {label}: " + "; ".join(value[:300] for value in values[:6]))
    if task_state.get("completed_steps"):
        lines.append("- Completed items are historical evidence; never repeat them after compaction.")
    if task_state.get("pending_steps") or task_state.get("next_action"):
        lines.append("- Resume only pending items and the explicit next action.")
    return "\n".join(lines)


def _max_tokens_for_message(msg: Any) -> int:
    return max_tokens_for_message(msg, _MESSAGE_TOKEN_LIMITS)


def _truncate_text(text: str, max_tokens: int) -> str:
    return trim_text_to_token_budget(text, max_tokens)


def _copy_message_with_content(msg: Any, content: str) -> Any:
    return copy_message_with_content(msg, content)


def _truncate_oversized_messages(messages: list[Any]) -> tuple[list[Any], bool]:
    return truncate_oversized_messages(messages, limits=_MESSAGE_TOKEN_LIMITS)


def _message_estimated_tokens(msg: Any) -> int:
    return estimate_message_tokens([msg])


def _coalesce_identical_tool_messages(messages: list[Any]) -> tuple[list[Any], int]:
    """Collapse runs of ToolMessages whose normalised content is identical.

    Reflects mature "tool noise reduction" pattern from Claude-code / Cursor:
    if the same tool returns the same content N consecutive times we keep one
    representative and replace the rest with a tiny placeholder. The model is
    informed via the trailing summary so it doesn't think it lost information.

    Returns (new_messages, coalesced_count).
    """
    if not messages:
        return messages, 0
    out: list[Any] = []
    coalesced = 0
    run_start_index: int | None = None
    run_signature: str | None = None
    run_count = 0

    def _flush(end_exclusive: int) -> None:
        nonlocal run_start_index, run_signature, run_count, coalesced
        if run_start_index is None or run_count <= 2:
            run_start_index = None
            run_signature = None
            run_count = 0
            return
        # Keep first occurrence and drop the rest; append one placeholder.
        first = messages[run_start_index]
        placeholder_text = f"(coalesced: previous tool output repeated {run_count - 1} more times with identical content — duplicates dropped)"
        # Replace already-appended duplicates after the first with the placeholder.
        # Walk back through `out` and remove the trailing (run_count-1) entries that
        # belong to this run; then append the placeholder.
        for _ in range(run_count - 1):
            out.pop()
        # We need to also drop the original first if user wanted; we keep first.
        placeholder = first.model_copy(update={"content": placeholder_text}) if isinstance(first, BaseMessage) else first
        out.append(placeholder)
        coalesced += run_count - 1
        run_start_index = None
        run_signature = None
        run_count = 0

    for index, msg in enumerate(messages):
        is_tool = getattr(msg, "type", "") == "tool"
        if is_tool:
            content_text = _content_to_text(getattr(msg, "content", ""))
            signature = (getattr(msg, "name", None) or "") + "::" + " ".join(content_text.split())[:240]
            if run_signature == signature:
                run_count += 1
                out.append(msg)
                continue
            # Different tool content — flush previous run (if any)
            _flush(index)
            run_start_index = index
            run_signature = signature
            run_count = 1
            out.append(msg)
        else:
            _flush(index)
            out.append(msg)
    _flush(len(messages))
    return out, coalesced


def _trim_messages_to_token_budget(messages: list[Any], max_tokens: int) -> tuple[list[Any], bool, int]:
    result = trim_messages_to_budget(
        messages,
        max_tokens,
        keep_recent_messages=None,
        system_budget_ratio=0.35,
    )
    return result.messages, result.changed, result.dropped_count


def _state_messages_to_compactor(messages: list[Any]) -> list[Message]:
    """Convert LangChain message objects to compactor Message format."""
    result: list[Message] = []
    for msg in messages:
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        content_str = str(content)
        msg_type = getattr(msg, "type", "")
        role = msg_type if msg_type in ("human", "ai", "system", "tool") else "human"
        token_count = _estimate_tokens(content_str)
        result.append(
            Message(
                role=role,
                content=content_str,
                token_count=token_count,
                is_system=(role == "system"),
                is_tool_boundary=(role == "tool" or bool(getattr(msg, "tool_calls", None))),
            )
        )
    return result


class SessionCompactionMiddleware(AgentMiddleware):
    """Compress conversation context when it exceeds token budget.

    Uses the ``before_model`` hook so compaction happens just before the LLM
    sees the messages.  The original messages list is replaced with the
    compacted version only when compaction actually occurs.
    """

    def __init__(
        self,
        max_context_tokens: int = 32_000,
        keep_recent_turns: int = 6,
        preflight_ratio: float = 0.5,
        aggressive_ratio: float = 0.85,
        allow_hard_truncation: bool | None = None,
    ) -> None:
        config = CompactionConfig(
            enabled=True,
            max_context_tokens=max_context_tokens,
            keep_recent_turns=keep_recent_turns,
            preflight_ratio=preflight_ratio,
            aggressive_ratio=aggressive_ratio,
        )
        self._compactor = SessionCompactor(config)
        self._allow_hard_truncation = os.getenv("OCTOAGENT_ALLOW_HARD_CONTEXT_TRUNCATION", "0") == "1" if allow_hard_truncation is None else allow_hard_truncation

    def _runtime_checkpoint_message(self, state: AgentState) -> SystemMessage | None:
        runtime_state = state.get("runtime") or {}
        summary = runtime_state.get("compaction_summary") if isinstance(runtime_state, dict) else None
        parts: list[str] = []
        if isinstance(summary, str) and summary.strip():
            parts.append(summary.strip())
        task_state_summary = _format_task_state_checkpoint(state.get("task_state"))
        if task_state_summary:
            parts.append(task_state_summary)
        if not parts:
            return None
        messages = list(state.get("messages") or [])
        if any(_CHECKPOINT_MARKER in _content_to_text(getattr(message, "content", "")) for message in messages):
            return None
        checkpoint_content = "\n\n".join(parts)
        return SystemMessage(
            content=(
                f"[{_CHECKPOINT_MARKER}]\n"
                "The following compact checkpoint preserves older conversation and task state that no longer fits verbatim. "
                "Use it silently to continue the user's task without asking them to repeat context.\n"
                f"{checkpoint_content}"
            )
        )

    @override
    def before_agent(self, state: AgentState, runtime: Runtime) -> dict | None:
        cycle_update = _context_cycle_runtime_update(runtime)
        merged_task_state, phase_update = _merge_task_progress_state(state)
        checkpoint_state = dict(state)
        if merged_task_state is not None:
            checkpoint_state["task_state"] = merged_task_state
        checkpoint_message = self._runtime_checkpoint_message(checkpoint_state)
        if checkpoint_message is None:
            if not cycle_update and not phase_update and merged_task_state is None:
                return None
            runtime_state = dict(state.get("runtime") or {})
            runtime_state.update(cycle_update)
            runtime_state.update(phase_update)
            update: dict[str, Any] = {"runtime": runtime_state}
            if merged_task_state is not None and merged_task_state != state.get("task_state"):
                update["task_state"] = merged_task_state
            return update
        messages = list(state.get("messages") or [])
        insert_at = 0
        while insert_at < len(messages) and getattr(messages[insert_at], "type", "") == "system":
            insert_at += 1
        messages.insert(insert_at, checkpoint_message)
        runtime_state = dict(state.get("runtime") or {})
        runtime_state.update(cycle_update)
        runtime_state.update(phase_update)
        runtime_state["continuation_mode"] = runtime_state.get("continuation_mode") or "resumed"
        runtime_state["recommended_memory_action"] = "continue"
        update = {"messages": messages, "runtime": runtime_state}
        if merged_task_state is not None and merged_task_state != state.get("task_state"):
            update["task_state"] = merged_task_state
        return update

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        """Check context pressure and compact if over budget.

        Tiered strategy selection follows the Hermes-style pressure gates:
          - < 85% of window  → no message rewriting on healthy hosts
          - >= 85%           → aggressive gateway compaction
          - OOM critical     → allow oversized-message truncation as a last resort
        """
        messages = state.get("messages")
        if not messages:
            return None

        merged_task_state, phase_update = _merge_task_progress_state(state)
        messages, coalesced_count = _coalesce_identical_tool_messages(list(messages))
        messages, truncated = _truncate_oversized_messages(messages) if self._allow_hard_truncation else (messages, False)
        compactor_msgs = _state_messages_to_compactor(messages)
        total_tokens = sum(m.token_count for m in compactor_msgs)
        budget = self._compactor.config.max_context_tokens

        aggressive_budget = max(1, int(budget * self._compactor.config.aggressive_ratio))

        if total_tokens < aggressive_budget:
            if not truncated and not coalesced_count:
                runtime_state = dict(state.get("runtime") or {})
                runtime_state.update(phase_update)
                if runtime_state.get("recommended_memory_action") == "truncate_oversized_messages":
                    runtime_state["context_pressure"] = "low"
                    runtime_state["context_guard_state"] = "ok"
                    runtime_state["recommended_memory_action"] = "continue"
                    update: dict[str, Any] = {"runtime": runtime_state}
                    if merged_task_state is not None and merged_task_state != state.get("task_state"):
                        update["task_state"] = merged_task_state
                    return update
                if merged_task_state is not None and merged_task_state != state.get("task_state"):
                    return {"runtime": runtime_state, "task_state": merged_task_state}
                return None  # Context fits — no compaction needed
            runtime_state = dict(state.get("runtime") or {})
            runtime_state.update(phase_update)
            runtime_state["context_pressure"] = "medium"
            runtime_state["context_guard_state"] = "coalesced" if not truncated else "truncated"
            runtime_state["recommended_memory_action"] = "compact" if truncated else "coalesce_tool_messages"
            if coalesced_count:
                runtime_state["tool_messages_coalesced"] = coalesced_count
            update = {"messages": messages, "runtime": runtime_state}
            if merged_task_state is not None and merged_task_state != state.get("task_state"):
                update["task_state"] = merged_task_state
            return update

        # ── Tiered strategy selection ─────────────────────────────────────
        pressure_ratio = total_tokens / max(budget, 1)
        original_strategy = self._compactor.config.strategy
        effective_strategy = "hybrid" if pressure_ratio < 2.0 else "summarize"
        compaction_trigger = "gateway_85_percent"
        compaction_budget = aggressive_budget

        original_budget = self._compactor.config.max_context_tokens

        try:
            if effective_strategy != original_strategy:
                logger.info(
                    "Session compaction: pressure ratio=%.2fx -> upgrading strategy %s -> %s",
                    pressure_ratio,
                    original_strategy,
                    effective_strategy,
                )
                self._compactor.config.strategy = effective_strategy
            self._compactor.config.max_context_tokens = compaction_budget
            result = self._compactor.compact(compactor_msgs)
        finally:
            self._compactor.config.strategy = original_strategy
            self._compactor.config.max_context_tokens = original_budget

        if not result.summary_inserted:
            if truncated:
                messages, budget_trimmed, dropped_count = _trim_messages_to_token_budget(list(messages), aggressive_budget)
                runtime_state = dict(state.get("runtime") or {})
                runtime_state.update(phase_update)
                runtime_state["context_pressure"] = "high"
                runtime_state["context_guard_state"] = "emergency_trimmed"
                runtime_state["recommended_memory_action"] = "compact"
                if budget_trimmed:
                    runtime_state["compaction_dropped_messages"] = dropped_count
                update = {"messages": messages, "runtime": runtime_state}
                if merged_task_state is not None and merged_task_state != state.get("task_state"):
                    update["task_state"] = merged_task_state
                return update
            return None  # Nothing was compacted

        logger.info(
            "Session compaction: %d → %d messages, saved ~%d tokens (strategy=%s, ratio=%.2fx)",
            result.original_count,
            result.compacted_count,
            result.tokens_saved,
            effective_strategy,
            pressure_ratio,
        )

        # Rebuild LangChain-compatible message dicts for the compacted result
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        rebuilt: list[Any] = []
        for cm in result.messages:
            if cm.is_system or cm.role == "system":
                rebuilt.append(SystemMessage(content=cm.content))
            elif cm.role == "ai":
                rebuilt.append(AIMessage(content=cm.content))
            else:
                rebuilt.append(HumanMessage(content=cm.content))

        rebuilt, budget_trimmed, dropped_count = _trim_messages_to_token_budget(rebuilt, aggressive_budget)

        runtime_state = dict(state.get("runtime") or {})
        runtime_state.update(phase_update)
        runtime_state["context_pressure"] = "high" if total_tokens >= aggressive_budget else "medium"
        runtime_state["context_guard_state"] = "compacted"
        runtime_state["compaction_strategy"] = effective_strategy
        runtime_state["compaction_trigger"] = compaction_trigger
        runtime_state["pressure_ratio"] = round(pressure_ratio, 2)
        runtime_state["recommended_memory_action"] = "compact"
        runtime_state["task_review_required"] = True
        runtime_state["self_feedback_action"] = "review_compaction_summary_and_update_next_step"
        runtime_state["resource_recovery_action"] = "run_stage_resource_recovery_if_pressure_persists"
        runtime_state["memory_followup_action"] = "promote_compaction_review_to_memory"
        runtime_state["capability_control_mode"] = "memory_guided_self_control"
        runtime_state["context_cycle_id"] = runtime_state.get("context_cycle_id") or f"context-cycle-{uuid.uuid4().hex[:12]}"
        runtime_state["context_cycle_started_at"] = runtime_state.get("context_cycle_started_at") or datetime.now(UTC).isoformat()
        runtime_state["context_cycle_base_tokens"] = total_tokens
        if budget_trimmed:
            runtime_state["compaction_dropped_messages"] = dropped_count
            runtime_state["context_guard_state"] = "emergency_trimmed"
        summary_message = next(
            (cm.content for cm in result.messages if cm.is_system and cm.content.startswith("[Session compaction")),
            None,
        )
        if summary_message:
            runtime_state["compaction_summary"] = _append_phase_review(summary_message, merged_task_state)
            runtime_state["compaction_saved_tokens"] = result.tokens_saved
        # 2026-05-16: Check if compaction was insufficient — trigger context handoff
        post_compaction_tokens = sum(m.token_count for m in result.messages)
        if post_compaction_tokens > budget * 0.95:
            runtime_state["context_handoff_required"] = True
            runtime_state["context_handoff_reason"] = "post_compaction_still_over_budget"
            runtime_state["context_handoff_pre_tokens"] = total_tokens
            runtime_state["context_handoff_post_tokens"] = post_compaction_tokens
            logger.warning(
                "Session compaction insufficient: %d -> %d tokens (budget=%d) — handoff required",
                total_tokens,
                post_compaction_tokens,
                budget,
            )
            # Force memory extraction before thread switch
            runtime_state["memory_flush_required"] = True
            runtime_state["thread_archive_at"] = datetime.now(UTC).isoformat()
            runtime_state["gc_trigger"] = "context_handoff"
        runtime_state["updated_at"] = datetime.now(UTC).isoformat()
        update = {"messages": rebuilt, "runtime": runtime_state}
        if merged_task_state is not None and merged_task_state != state.get("task_state"):
            update["task_state"] = merged_task_state
        return update

    @override
    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        """Async variant: offload heavy compaction work to a worker thread."""
        return await asyncio.to_thread(self.before_model, state, runtime)
