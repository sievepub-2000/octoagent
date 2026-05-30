"""Persistent task-state middleware for resumable long-running work."""

from __future__ import annotations

import logging
import os
import re
import threading
from html import unescape
from typing import Annotated, Any, NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime

from src.agents.core.termination import classify_run_outcome
from src.agents.thread_state import merge_runtime_state
from src.utils.datetime import utc_now_iso as _utc_now
from src.utils.messages import message_text as _message_text

_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_TASK_STATE_MARKER = "OctoAgent persistent task state"
_TASK_STATE_VERSION = 1
_MAX_FIELD_CHARS = 1_200
_MAX_CHECKPOINT_CHARS = 6_000

_COMPLEX_TASK_PATTERN = re.compile(
    r"(修复|重构|实现|优化|分析|评估|排查|检查|测试|验证|继续|完成|全部|系统|"
    r"部署|方案|建议|推荐|收益|赚钱|具体|查询|查找|查一下|搜索|新闻|调研|研究|"
    r"research|analy[sz]e|implement|refactor|fix|debug|verify|continue|all)",
    re.IGNORECASE,
)
_RECOVERY_HUMAN_PATTERN = re.compile(
    r"^\s*(?:"
    r"\[system:\s*session context compressed\b|"
    r"continue the unfinished work in this conversation\b|"
    r"continue the latest unfinished user task\b|"
    r"continue the current task using the visible conversation context\b"
    r")",
    re.IGNORECASE,
)


logger = logging.getLogger(__name__)


def _generate_task_completion_summary(task_state: dict[str, Any]) -> str:
    """Generate a structured task completion summary for long-term memory."""
    goal = task_state.get("goal", "unknown")
    status = task_state.get("status", "unknown")
    completed = task_state.get("completed_steps", [])
    failed = task_state.get("failed_attempts", [])
    evidence = task_state.get("evidence", [])

    lines = [
        "## Task Completion Summary",
        f"Goal: {str(goal)[:500]}",
        f"Status: {status}",
        f"Completed steps ({len(completed)}):",
    ]
    for step in completed[:10]:
        lines.append(f"  - {str(step)[:200]}")

    if failed:
        lines.append(f"Failed attempts ({len(failed)}):")
        for attempt in failed[:5]:
            lines.append(f"  - {str(attempt)[:200]}")

    if evidence:
        lines.append(f"Key evidence ({len(evidence)}):")
        for ev in evidence[:5]:
            lines.append(f"  - {str(ev)[:200]}")

    return "\n".join(lines)


def _persist_task_summary_async(summary: str, thread_id: str) -> None:
    """Write task completion summary to long-term memory asynchronously."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        logger.debug("Skipping async task summary persistence under pytest")
        return

    def _worker():
        try:
            from src.agents.memory.simplemem_bridge import get_simplemem_bridge

            bridge = get_simplemem_bridge()
            bridge.store_fact(
                summary,
                namespace="conversation_summary",
                metadata={"thread_id": thread_id, "type": "task_summary"},
            )
            logger.info("Task completion summary persisted for thread %s", thread_id[:8])
        except Exception as exc:
            logger.debug("Failed to persist task summary: %s", exc)

    thread = threading.Thread(
        target=_worker,
        name=f"task-summary-{thread_id[:8]}",
        daemon=True,
    )
    thread.start()


class TaskStateMiddlewareState(AgentState):
    """Compatible with the `ThreadState` schema."""

    runtime: Annotated[dict[str, Any] | None, merge_runtime_state]
    task_state: NotRequired[dict[str, Any] | None]
    todos: NotRequired[list[dict[str, Any]] | None]






def _visible_message_text(message: Any) -> str:
    """Return visible text after removing provider thought tags and markup."""

    text = _message_text(message)
    text = _THINK_BLOCK_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _truncate(value: Any, limit: int = _MAX_FIELD_CHARS) -> str:
    """Trim a value to a compact, model-friendly string."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _latest_human_text(messages: list[Any]) -> str:
    """Return the latest human message text, if any."""
    for message in reversed(messages):
        if getattr(message, "type", "") == "human":
            return _message_text(message)
    return ""


def _latest_user_human_text(messages: list[Any]) -> str:
    """Return the latest real user request, ignoring synthetic recovery turns."""
    fallback = ""
    for message in reversed(messages):
        if getattr(message, "type", "") != "human":
            continue
        text = _message_text(message)
        if not fallback:
            fallback = text
        if _RECOVERY_HUMAN_PATTERN.match(text):
            continue
        return text
    return fallback


def _latest_ai_message(messages: list[Any]) -> AIMessage | None:
    """Return the latest assistant message, if any."""
    for message in reversed(messages):
        if isinstance(message, AIMessage) or getattr(message, "type", "") == "ai":
            return message
    return None


def _is_complex_task(text: str) -> bool:
    """Decide whether a request needs persistent progress tracking."""
    stripped = text.strip()
    if len(stripped) >= 180:
        return True
    if len(re.findall(r"[\n;；。]|\d+[.)、]", stripped)) >= 2:
        return True
    return bool(_COMPLEX_TASK_PATTERN.search(stripped))


def _goal_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _is_new_user_goal(latest_goal: str, task_state: dict[str, Any] | None) -> bool:
    if not latest_goal or task_state is None or not _is_complex_task(latest_goal):
        return False
    old_goal = _goal_key(task_state.get("goal"))
    new_goal = _goal_key(latest_goal)
    if not old_goal or old_goal == new_goal or old_goal in new_goal or new_goal in old_goal:
        return False
    return not re.match(r"^(继续|接着|然后|下一步|按上面|继续上|continue\b|go on\b)", new_goal)


def _todo_bucket(todos: list[dict[str, Any]], status: str) -> list[str]:
    """Return todo contents matching a specific status."""
    return [_truncate(todo.get("content"), 500) for todo in todos if str(todo.get("status") or "") == status and str(todo.get("content") or "").strip()][:12]


def _progress_key(value: Any) -> str:
    """Return a stable key for comparing todo/task progress entries."""

    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _dedupe_progress(
    completed_steps: list[Any],
    pending_steps: list[Any],
) -> tuple[list[Any], list[Any]]:
    """Deduplicate task progress and remove completed items from pending.

    Compaction checkpoints are intentionally terse. If an item appears in both
    buckets, models often treat it as still actionable after resume. Completed
    entries win: they are historical evidence, not work to repeat.
    """

    completed: list[Any] = []
    completed_keys: set[str] = set()
    for item in completed_steps:
        key = _progress_key(item)
        if not key or key in completed_keys:
            continue
        completed.append(item)
        completed_keys.add(key)

    pending: list[Any] = []
    pending_keys: set[str] = set()
    for item in pending_steps:
        key = _progress_key(item)
        if not key or key in completed_keys or key in pending_keys:
            continue
        pending.append(item)
        pending_keys.add(key)

    return completed, pending


def _tool_errors_since_latest_human(messages: list[Any]) -> list[str]:
    """Collect compact tool error summaries from the current turn."""
    start = 0
    for index in range(len(messages) - 1, -1, -1):
        if getattr(messages[index], "type", "") == "human":
            start = index + 1
            break

    errors: list[str] = []
    for message in messages[start:]:
        if not isinstance(message, ToolMessage):
            continue
        text = _message_text(message)
        lowered = text.lower()
        if getattr(message, "status", None) == "error" or lowered.startswith(("error:", "failed:", "http error")):
            name = str(getattr(message, "name", None) or "tool")
            errors.append(f"{name}: {_truncate(text, 420)}")
    return errors[-8:]


def _normalize_task_state(value: Any) -> dict[str, Any] | None:
    """Normalize an existing task-state object."""
    if not isinstance(value, dict):
        return None
    goal = _truncate(value.get("goal"))
    if not goal:
        return None
    completed_steps, pending_steps = _dedupe_progress(
        list(value.get("completed_steps") or [])[:16],
        list(value.get("pending_steps") or [])[:16],
    )
    return {
        "version": int(value.get("version") or _TASK_STATE_VERSION),
        "goal": goal,
        "status": str(value.get("status") or "active"),
        "current_step": _truncate(value.get("current_step")),
        "completed_steps": completed_steps,
        "pending_steps": pending_steps,
        "evidence": list(value.get("evidence") or [])[:12],
        "failed_attempts": list(value.get("failed_attempts") or [])[:12],
        "next_action": _truncate(value.get("next_action")),
        "updated_at": str(value.get("updated_at") or _utc_now()),
    }


def _new_task_state(goal: str) -> dict[str, Any]:
    """Create a new persistent task-state snapshot."""
    trimmed_goal = _truncate(goal)
    return {
        "version": _TASK_STATE_VERSION,
        "goal": trimmed_goal,
        "status": "active",
        "current_step": "start work",
        "completed_steps": [],
        "pending_steps": [trimmed_goal] if trimmed_goal else [],
        "evidence": [],
        "failed_attempts": [],
        "next_action": "continue executing the user's task",
        "updated_at": _utc_now(),
    }


def _checkpoint_exists(messages: list[Any]) -> bool:
    """Return True if the task-state checkpoint is already visible."""
    return any(_TASK_STATE_MARKER in _message_text(message) for message in messages)


def _format_task_state(task_state: dict[str, Any]) -> str:
    """Render task state for hidden model context."""
    lines = [f"[{_TASK_STATE_MARKER}]", f"Goal: {task_state['goal']}"]
    lines.append(f"Status: {task_state.get('status') or 'active'}")
    if task_state.get("current_step"):
        lines.append(f"Current step: {task_state['current_step']}")
    if task_state.get("next_action"):
        lines.append(f"Next action: {task_state['next_action']}")
    for label, key in (
        ("Completed steps", "completed_steps"),
        ("Pending steps", "pending_steps"),
        ("Evidence", "evidence"),
        ("Failed attempts", "failed_attempts"),
    ):
        values = [str(item).strip() for item in task_state.get(key, []) if str(item).strip()]
        if not values:
            continue
        lines.append(f"{label}:")
        lines.extend(f"- {_truncate(item, 500)}" for item in values[:8])
    lines.append("Completed steps are historical evidence only; do not repeat them after context compaction or continuation.")
    lines.append("Continue only pending steps and the explicit next action. Do not ask the user to repeat prior context.")
    rendered = "\n".join(lines)
    if len(rendered) <= _MAX_CHECKPOINT_CHARS:
        return rendered
    return rendered[: _MAX_CHECKPOINT_CHARS - 3].rstrip() + "..."


def _runtime_update_for_task(task_state: dict[str, Any]) -> dict[str, Any]:
    """Build runtime telemetry fields for the task snapshot."""
    status = str(task_state.get("status") or "active")
    runtime_update: dict[str, Any] = {
        "task_state_status": status,
        "updated_at": _utc_now(),
    }
    if status == "incomplete":
        recoverable = {
            "status": "recoverable",
            "reason": task_state.get("current_step") or "Task ended before completion.",
            "next_action": task_state.get("next_action") or "continue the task",
            "task_goal": task_state.get("goal"),
        }
        runtime_update["recoverable_failure"] = recoverable
        runtime_update["incomplete_state"] = recoverable
        runtime_update["recommended_memory_action"] = "continue"
    elif status == "completed":
        runtime_update["recoverable_failure"] = None
        runtime_update["incomplete_state"] = None
    return runtime_update


def _merge_context_task_state(state: TaskStateMiddlewareState, runtime: Runtime) -> dict[str, Any] | None:
    """Return task state from persisted state or continuation context."""
    existing = _normalize_task_state(state.get("task_state"))
    if existing is not None:
        return existing
    context = runtime.context if runtime is not None and runtime.context else {}
    return _normalize_task_state(context.get("continue_task_state"))


class TaskStateMiddleware(AgentMiddleware[TaskStateMiddlewareState]):
    """Keep long-running task progress outside the shrinking message window."""

    state_schema = TaskStateMiddlewareState

    @override
    def before_agent(
        self,
        state: TaskStateMiddlewareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """Inject a compact task checkpoint for complex or resumed work."""
        messages = list(state.get("messages") or [])
        task_state = _merge_context_task_state(state, runtime)
        latest_goal = _latest_user_human_text(messages)
        if _is_new_user_goal(latest_goal, task_state):
            task_state = _new_task_state(latest_goal)
        if task_state is None:
            if not _is_complex_task(latest_goal):
                return None
            task_state = _new_task_state(latest_goal)

        runtime_state = dict(state.get("runtime") or {})
        runtime_state.update(_runtime_update_for_task(task_state))
        update: dict[str, Any] = {"task_state": task_state, "runtime": runtime_state}

        if task_state.get("status") in {"active", "incomplete"} and not _checkpoint_exists(messages):
            insert_at = 0
            while insert_at < len(messages) and getattr(messages[insert_at], "type", "") == "system":
                insert_at += 1
            patched = list(messages)
            patched.insert(insert_at, SystemMessage(content=_format_task_state(task_state), name="task_state_checkpoint"))
            update["messages"] = patched
        return update

    @override
    def after_agent(
        self,
        state: TaskStateMiddlewareState,
        runtime: Runtime,  # noqa: ARG002
    ) -> dict[str, Any] | None:
        """Update persistent task state after an agent run finishes."""
        messages = list(state.get("messages") or [])
        task_state = _normalize_task_state(state.get("task_state"))
        latest_goal = _latest_user_human_text(messages)
        if _is_new_user_goal(latest_goal, task_state):
            task_state = _new_task_state(latest_goal)
        if task_state is None:
            if not _is_complex_task(latest_goal):
                return None
            task_state = _new_task_state(latest_goal)

        todos = list(state.get("todos") or [])
        completed_steps = _todo_bucket(todos, "completed") or list(task_state.get("completed_steps") or [])
        pending_steps = [
            *_todo_bucket(todos, "in_progress"),
            *_todo_bucket(todos, "pending"),
        ] or list(task_state.get("pending_steps") or [])
        completed_steps, pending_steps = _dedupe_progress(completed_steps, pending_steps)

        tool_errors = _tool_errors_since_latest_human(messages)

        # Delegate completion/active/incomplete classification to the central
        # termination module. It inspects message structure only -- no keyword
        # heuristics on final-message text length or "is this substantive".
        outcome = classify_run_outcome(messages, tool_errors=tool_errors)

        if outcome.status == "completed":
            # Model produced visible text without pending tool calls. Trust it.
            status = "completed"
            current_step = outcome.current_step
            next_action = outcome.next_action
            if not completed_steps:
                completed_steps = [task_state.get("goal") or latest_goal]
            pending_steps = []
        elif outcome.status == "incomplete":
            status = "incomplete"
            # Prefer middleware-tracked pending_steps as the concrete next
            # action -- the classifier's reason is the *why*, pending_steps
            # are the *what*.
            if pending_steps:
                current_step = pending_steps[0]
                next_action = pending_steps[0]
            else:
                current_step = outcome.current_step
                next_action = outcome.next_action
        else:
            # outcome.status == "active" -- rare at after_agent (graph hop), but
            # treat it as "still tracking pending work".
            if pending_steps:
                status = "active"
                current_step = pending_steps[0]
                next_action = pending_steps[0]
            else:
                status = str(task_state.get("status") or "active")
                current_step = _truncate(task_state.get("current_step"))
                next_action = _truncate(task_state.get("next_action"))

        evidence = list(task_state.get("evidence") or [])
        for message in messages[-8:]:
            if isinstance(message, ToolMessage) and getattr(message, "status", None) != "error":
                name = str(getattr(message, "name", None) or "tool")
                evidence.append(f"{name}: {_truncate(_message_text(message), 420)}")
        evidence = list(dict.fromkeys(evidence))[-12:]

        failed_attempts = list(task_state.get("failed_attempts") or [])
        failed_attempts.extend(tool_errors)
        failed_attempts = list(dict.fromkeys(failed_attempts))[-12:]

        next_state = {
            **task_state,
            # Preserve original goal — never overwrite with derived text
            "goal": task_state.get("goal") or latest_goal,
            "status": status,
            "current_step": current_step,
            "completed_steps": completed_steps[:16],
            "pending_steps": pending_steps[:16],
            "evidence": evidence,
            "failed_attempts": failed_attempts,
            "next_action": next_action,
            "updated_at": _utc_now(),
        }
        runtime_state = dict(state.get("runtime") or {})
        runtime_state.update(_runtime_update_for_task(next_state))

        # When task completes, generate and persist a summary to long-term memory
        if status == "completed" and str(task_state.get("status")) != "completed":
            runtime_context = runtime.context or {} if runtime else {}
            thread_id = runtime_context.get("thread_id", "unknown")
            summary = _generate_task_completion_summary(next_state)
            _persist_task_summary_async(summary, thread_id)
            runtime_state["task_summary_persisted"] = True
            logger.info("Task completed — summary persisted to long-term memory")

        return {"task_state": next_state, "runtime": runtime_state}

    @override
    async def abefore_agent(
        self,
        state: TaskStateMiddlewareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """Async version of before_agent."""
        return self.before_agent(state, runtime)

    @override
    async def aafter_agent(
        self,
        state: TaskStateMiddlewareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """Async version of after_agent."""
        return self.after_agent(state, runtime)


__all__ = ["TaskStateMiddleware"]
