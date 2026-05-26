"""Middleware that injects seamless continuation context for new threads."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage, SystemMessage

_MAX_CONTINUATION_CONTEXT_CHARS = 12_000
_MAX_CONTINUATION_ITEM_CHARS = 1_200


def _truncate_text(value: str, limit: int = _MAX_CONTINUATION_ITEM_CHARS) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    head = max(1, int(limit * 0.72))
    tail = max(1, limit - head)
    return text[:head].rstrip() + "\n[continuation context shortened]\n" + text[-tail:].lstrip()


def _cap_continuation_message(message: SystemMessage) -> SystemMessage:
    content = str(message.content or "")
    if len(content) <= _MAX_CONTINUATION_CONTEXT_CHARS:
        return message
    head = max(1, int(_MAX_CONTINUATION_CONTEXT_CHARS * 0.76))
    tail = max(1, _MAX_CONTINUATION_CONTEXT_CHARS - head)
    shortened = content[:head].rstrip() + "\n\n[continuation context shortened to fit the active context window]\n\n" + content[-tail:].lstrip()
    return message.model_copy(update={"content": shortened})


class ContinuationMiddleware(AgentMiddleware[AgentState]):
    """Inject a hidden continuation reminder when a thread resumes prior work."""

    @staticmethod
    def _format_snapshot(snapshot: list[dict[str, str]]) -> str:
        lines: list[str] = []
        for item in snapshot:
            role = item.get("role", "message").strip() or "message"
            content = _truncate_text(item.get("content", ""))
            if not content:
                continue
            lines.append(f"- {role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _format_workflows(workflows: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for workflow in workflows[:6]:
            title = str(workflow.get("title") or "Untitled workflow")
            mode = str(workflow.get("mode") or "task")
            status = str(workflow.get("status") or "draft")
            goal = _truncate_text(str(workflow.get("goal") or ""), 700)
            expected = _truncate_text(str(workflow.get("expectedOutput") or ""), 700)
            lines.append(f"- {title} [{mode} / {status}]")
            if goal:
                lines.append(f"  Goal: {goal}")
            if expected:
                lines.append(f"  Expected output: {expected}")
        return "\n".join(lines)

    @staticmethod
    def _format_todos(todos: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for todo in todos[:12]:
            content = _truncate_text(str(todo.get("content") or ""), 500)
            if not content:
                continue
            status = str(todo.get("status") or "pending").strip() or "pending"
            lines.append(f"- [{status}] {content}")
        return "\n".join(lines)

    def _build_message(self, context: dict[str, Any]) -> SystemMessage | None:
        if context.get("continue_trigger") != "continue":
            return None

        source_thread_id = str(context.get("continue_from_thread_id") or "").strip()
        source_title = str(context.get("continue_from_title") or "").strip()
        message_count = context.get("continue_message_count")
        cycle_id = str(context.get("continue_cycle_id") or "").strip()
        cycle_started_at = str(context.get("continue_cycle_started_at") or "").strip()
        cycle_base_tokens = context.get("continue_cycle_base_tokens")
        todos = context.get("continue_todos") or []
        workflows = context.get("continue_workflows") or []
        task_state = context.get("continue_task_state") or None
        snapshot = context.get("continue_recent_messages") or []
        memory_summary = str(context.get("continue_memory_summary") or "").strip()

        lines = ["<continue_context>"]
        lines.append("This is a continuation handoff from a previous thread. Treat this turn as a request to continue the existing work seamlessly.")
        if source_thread_id:
            lines.append(f"Source thread ID: {source_thread_id}")
        if source_title:
            lines.append(f"Source thread title: {source_title}")
        if isinstance(message_count, int):
            lines.append(f"Source message count: {message_count}")
        if cycle_id:
            lines.append(f"Context cycle ID: {cycle_id}")
        if cycle_started_at:
            lines.append(f"Context cycle started at: {cycle_started_at}")
        if isinstance(cycle_base_tokens, int | float):
            lines.append(f"Context cycle base tokens: {int(cycle_base_tokens)}")

        if isinstance(snapshot, list) and snapshot:
            formatted_snapshot = self._format_snapshot(snapshot)
            if formatted_snapshot:
                lines.append("")
                lines.append("Latest three user/assistant exchanges:")
                lines.append(formatted_snapshot)

        if memory_summary:
            lines.append("")
            lines.append("Extracted continuation memory:")
            lines.append(_truncate_text(memory_summary, 2_400))

        if isinstance(todos, list) and todos:
            formatted_todos = self._format_todos(todos)
            if formatted_todos:
                lines.append("")
                lines.append("Active task todo state to continue:")
                lines.append(formatted_todos)

        if isinstance(task_state, dict) and task_state.get("goal"):
            lines.append("")
            lines.append("Persistent task state to continue:")
            for label, key in (
                ("Goal", "goal"),
                ("Status", "status"),
                ("Current step", "current_step"),
                ("Next action", "next_action"),
            ):
                value = _truncate_text(str(task_state.get(key) or ""), 700)
                if value:
                    lines.append(f"{label}: {value}")
            completed_steps = [str(item).strip() for item in task_state.get("completed_steps", []) if str(item).strip()]
            pending_steps = [str(item).strip() for item in task_state.get("pending_steps", []) if str(item).strip()]
            if completed_steps:
                lines.append("Completed steps (do not repeat):")
                lines.extend(f"- {_truncate_text(item, 360)}" for item in completed_steps[:8])
            if pending_steps:
                lines.append("Pending steps to resume:")
                lines.extend(f"- {_truncate_text(item, 360)}" for item in pending_steps[:8])

        if isinstance(workflows, list) and workflows:
            formatted_workflows = self._format_workflows(workflows)
            if formatted_workflows:
                lines.append("")
                lines.append("Active workflow state to continue:")
                lines.append(formatted_workflows)

        lines.append("")
        lines.append("Continue from the prior conversation state and workflow state unless the user explicitly changes direction. Treat the prior payload as a compressed handoff; do not ask the user to repeat it.")
        lines.append("")
        lines.append("CRITICAL RULES for continuation:")
        lines.append("1. The task goal in this context is your PRIMARY objective \u2014 do not drift from it")
        lines.append("2. Execute pending_steps in order; do not repeat completed_steps")
        lines.append("3. Do not ask the user to re-explain anything already in this context")
        lines.append("4. Begin your first action immediately \u2014 call a tool or execute the next step")
        lines.append("5. If the todo list has in_progress items, resume from there")
        lines.append("</continue_context>")

        return _cap_continuation_message(SystemMessage(content="\n".join(lines), name="workflow_continue"))

    def _inject(self, messages: list[Any], context: dict[str, Any]) -> list[Any] | None:
        continuation = self._build_message(context)
        if continuation is None:
            return None
        if any(getattr(message, "name", None) == "workflow_continue" for message in messages):
            return None

        insert_at = len(messages)
        for index in range(len(messages) - 1, -1, -1):
            if isinstance(messages[index], HumanMessage):
                insert_at = index
                break

        patched = list(messages)
        patched.insert(insert_at, continuation)
        return patched

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        patched = self._inject(list(request.messages), request.runtime.context or {})
        if patched is not None:
            request = request.override(messages=patched)
        return handler(request)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        patched = self._inject(list(request.messages), request.runtime.context or {})
        if patched is not None:
            request = request.override(messages=patched)
        return await handler(request)
