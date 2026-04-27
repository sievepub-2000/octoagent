"""Middleware that injects seamless continuation context for new threads."""

from __future__ import annotations

from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime


class ContinuationMiddleware(AgentMiddleware[AgentState]):
    """Inject a hidden continuation reminder when a new thread resumes prior work."""

    @staticmethod
    def _format_snapshot(snapshot: list[dict[str, str]]) -> str:
        lines: list[str] = []
        for item in snapshot:
            role = item.get("role", "message").strip() or "message"
            content = item.get("content", "").strip()
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
            goal = str(workflow.get("goal") or "").strip()
            expected = str(workflow.get("expectedOutput") or "").strip()
            lines.append(f"- {title} [{mode} / {status}]")
            if goal:
                lines.append(f"  Goal: {goal}")
            if expected:
                lines.append(f"  Expected output: {expected}")
        return "\n".join(lines)

    @override
    def before_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        if (runtime.context or {}).get("continue_trigger") != "continue":
            return None

        messages = list(state.get("messages", []))
        if not messages:
            return None

        last_message = messages[-1]
        if not isinstance(last_message, HumanMessage):
            return None

        if getattr(last_message, "name", None) == "workflow_continue":
            return None

        _ctx = runtime.context or {}
        source_thread_id = str(_ctx.get("continue_from_thread_id") or "").strip()
        source_title = str(_ctx.get("continue_from_title") or "").strip()
        message_count = _ctx.get("continue_message_count")
        workflows = _ctx.get("continue_workflows") or []
        snapshot = _ctx.get("continue_recent_messages") or []

        lines = ["<continue_context>"]
        lines.append(
            "This is a continuation handoff from a previous thread. Treat this turn as a request to continue the existing work seamlessly."
        )
        if source_thread_id:
            lines.append(f"Source thread ID: {source_thread_id}")
        if source_title:
            lines.append(f"Source thread title: {source_title}")
        if isinstance(message_count, int):
            lines.append(f"Source message count: {message_count}")

        if isinstance(snapshot, list) and snapshot:
            formatted_snapshot = self._format_snapshot(snapshot)
            if formatted_snapshot:
                lines.append("")
                lines.append("Recent conversation snapshot:")
                lines.append(formatted_snapshot)

        if isinstance(workflows, list) and workflows:
            formatted_workflows = self._format_workflows(workflows)
            if formatted_workflows:
                lines.append("")
                lines.append("Active workflow state to continue:")
                lines.append(formatted_workflows)

        lines.append("")
        lines.append(
            "Continue from the prior conversation state and workflow state unless the user explicitly changes direction."
        )
        lines.append("</continue_context>")

        original_content = ""
        if isinstance(last_message.content, str):
            original_content = last_message.content
        elif isinstance(last_message.content, list):
            text_parts = []
            for block in last_message.content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(str(block.get("text", "")))
            original_content = "\n".join(part for part in text_parts if part)

        messages[-1] = HumanMessage(
            content=f"{chr(10).join(lines)}\n\n{original_content}".strip(),
            id=last_message.id,
            name="workflow_continue",
            additional_kwargs=last_message.additional_kwargs,
        )

        return {"messages": messages}
