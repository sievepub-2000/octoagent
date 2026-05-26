"""Build compact execution run records from agent state.

The single source of truth for "did this run finish?" is
:func:`src.agents.core.termination.classify_run_outcome`. The record builder
records the classification result rather than inferring completion from text
heuristics on the final assistant message.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from html import unescape
from typing import Any

from src.agents.core.termination import classify_run_outcome
from src.utils.datetime import utc_now_iso as _utc_now
from src.utils.messages import message_text as _message_text






_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _visible_message_text(message: Any) -> str:
    """Return user-visible assistant text, excluding hidden thought markup."""

    text = _message_text(message)
    if not text:
        return ""
    text = _THINK_BLOCK_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _final_evaluation_status(
    runtime: dict[str, Any],
    task_state: Any,
    messages: list[Any],
    explicit: str | None,
) -> tuple[str, str | None]:
    """Reconcile run status with the centralized termination classifier.

    Priority:
      1. An explicit override from the caller (e.g. ``submit_final_answer``)
         always wins.
      2. A pending recoverable_failure from runtime is incomplete.
      3. The :func:`classify_run_outcome` verdict on the message history is
         authoritative. ``task_state.status`` is used only as a tie-breaker for
         ``completed`` -- the model may have produced clean visible text while
         middleware still tracks pending todos.
    """

    if explicit:
        return explicit, None
    if runtime.get("recoverable_failure"):
        return "incomplete", "recoverable_failure_present"

    outcome = classify_run_outcome(messages, tool_errors=runtime.get("tool_errors") or None)
    if outcome.status == "completed":
        # If task_state is still actively tracking pending steps, the model may
        # have ended the turn before working through them. Trust task_state.
        if isinstance(task_state, dict):
            ts_status = str(task_state.get("status") or "")
            if ts_status == "incomplete":
                return "incomplete", str(task_state.get("current_step") or "task_state_incomplete")
        return "completed", None
    if outcome.status == "active":
        # An "active" classification at record time means the run was cut off
        # while it still wanted control (pending tool_calls). Treat as incomplete.
        return "incomplete", outcome.reason or "agent_was_still_active"
    return "incomplete", outcome.reason


def _tool_calls_from_messages(messages: list[Any]) -> tuple[list[str], list[str]]:
    used: list[str] = []
    failed: list[str] = []
    for message in messages:
        for tool_call in getattr(message, "tool_calls", None) or []:
            name = tool_call.get("name", "") if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
            if name and name not in used:
                used.append(name)
        if getattr(message, "type", "") == "tool":
            name = getattr(message, "name", "") or ""
            if name and name not in used:
                used.append(name)
            text = _message_text(message).lower()
            if name and any(marker in text for marker in ("error", "failed", "exception", "traceback", "\u5931\u8d25", "\u9519\u8bef")):
                failed.append(name)
    return used, list(dict.fromkeys(failed))


def _todo_summary(todos: list[dict[str, Any]] | None) -> dict[str, int]:
    items = list(todos or [])
    return {
        "total": len(items),
        "completed": sum(1 for item in items if item.get("status") == "completed"),
        "in_progress": sum(1 for item in items if item.get("status") == "in_progress"),
        "pending": sum(1 for item in items if item.get("status") == "pending"),
    }


def _task_state_for_record(task_state: Any, status: str) -> Any:
    """Reconcile task_state.status with the final evaluation outcome.

    When the final evaluation concludes the run is ``completed`` but the
    persistent task_state still says ``active``/``incomplete``, the middleware
    will not get a chance to update it before this record is written. Align the
    snapshot for downstream consumers (frontend auto-resume etc.).
    """

    if not isinstance(task_state, dict):
        return task_state
    if status != "completed":
        return task_state
    if str(task_state.get("status") or "") not in {"active", "incomplete"}:
        return task_state
    aligned = dict(task_state)
    goal = aligned.get("goal")
    aligned["status"] = "completed"
    aligned["current_step"] = "assistant delivered a final answer"
    aligned["next_action"] = "none"
    if not aligned.get("completed_steps") and goal:
        aligned["completed_steps"] = [goal]
    aligned["pending_steps"] = []
    return aligned


def build_execution_run_record(
    state: dict[str, Any],
    *,
    final_status: str | None = None,
    evaluation_reason: str | None = None,
) -> dict[str, Any]:
    """Return a single auditable run record for the latest agent execution."""

    runtime = dict(state.get("runtime") or {})
    messages = list(state.get("messages") or [])
    tool_used, tool_failed = _tool_calls_from_messages(messages)
    final_message = ""
    task_state = state.get("task_state") or None
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai" and _visible_message_text(message):
            final_message = _visible_message_text(message)
            break
    status, derived_reason = _final_evaluation_status(runtime, task_state, messages, final_status)
    record_task_state = _task_state_for_record(task_state, status)

    return {
        "recorded_at": _utc_now(),
        "instruction_contract": runtime.get("instruction_contract") or {},
        "model": {
            "primary_model": runtime.get("primary_model"),
            "active_model": runtime.get("active_model") or runtime.get("primary_model"),
            "fallback_switches": list(runtime.get("fallback_switches") or []),
            "final_error": runtime.get("final_error"),
        },
        "tools": {
            "used": tool_used,
            "failed": tool_failed,
            "count": len(tool_used),
        },
        "todos": _todo_summary(state.get("todos")),
        "memory": runtime.get("memory_write") or {"status": "unknown"},
        "task_state": record_task_state,
        "recoverable_failure": runtime.get("recoverable_failure") or None,
        "fallback": {
            "used": bool(runtime.get("fallback_switches")),
            "chain": list(runtime.get("fallback_chain") or []),
        },
        "final_evaluation": {
            "status": status,
            "reason": evaluation_reason or derived_reason,
            "final_message_preview": final_message[:500],
        },
    }


__all__ = ["build_execution_run_record"]
