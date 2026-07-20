"""Enforce tool safety at the execution seam without steering model reasoning.

The model owns planning, retries, reflection, and tool selection.  This module
only normalizes explicit tool failures and stops an identical failing action
from running forever.  It never injects system prompts and never rewrites a
successful tool result based on words that happen to appear in its payload.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage

from src.utils.messages import latest_human_index
from src.utils.messages import message_text as _message_text

_ERROR_PREFIXES = ("error:", "failed:", "http error")


def _json_tool_payload_is_error(text: str) -> bool:
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return False
    return isinstance(payload, dict) and bool(payload.get("error") or payload.get("error_code"))


def _tool_message_is_error(message: ToolMessage) -> bool:
    if getattr(message, "status", None) == "error":
        return True
    text = _message_text(message).strip().lower()
    return text.startswith(_ERROR_PREFIXES) or _json_tool_payload_is_error(text)


def _tool_call_signature(tool_name: str, args: object) -> str:
    stable_args = args if isinstance(args, dict) else {}
    stable = json.dumps(stable_args, sort_keys=True, ensure_ascii=False, default=str)
    return f"{tool_name}:{hashlib.sha256(stable.encode()).hexdigest()[:16]}"


def _failed_call_signatures(messages: list[object]) -> list[str]:
    scoped = messages[latest_human_index(messages) + 1 :]
    calls_by_id: dict[str, str] = {}
    for message in scoped:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls or []:
            call_id = str(call.get("id") or "")
            if call_id:
                calls_by_id[call_id] = _tool_call_signature(
                    str(call.get("name") or "tool"),
                    call.get("args"),
                )

    failures: list[str] = []
    for message in scoped:
        if not isinstance(message, ToolMessage) or not _tool_message_is_error(message):
            continue
        call_id = str(getattr(message, "tool_call_id", "") or "")
        signature = calls_by_id.get(call_id)
        if signature:
            failures.append(signature)
    return failures


class ToolExecutionGuardMiddleware(AgentMiddleware[AgentState]):
    """Normalize explicit failures and cap identical failed executions."""

    def __init__(self, max_identical_failures: int = 3, **_legacy_options: Any) -> None:
        super().__init__()
        self.max_identical_failures = max(1, int(max_identical_failures))

    def _blocked_repeated_failure(self, request: ToolCallRequest) -> ToolMessage | None:
        state = request.state if isinstance(request.state, Mapping) else {}
        messages = list(state.get("messages") or [])
        tool_name = request.tool.name if request.tool else str(request.tool_call.get("name") or "tool")
        signature = _tool_call_signature(tool_name, request.tool_call.get("args"))
        prior_failures = sum(1 for item in _failed_call_signatures(messages) if item == signature)
        if prior_failures < self.max_identical_failures:
            return None
        return ToolMessage(
            content=(
                f"Error: `{tool_name}` already failed with identical arguments "
                f"{prior_failures} times in this turn. Change the arguments or choose another approach."
            ),
            name=tool_name,
            tool_call_id=request.tool_call.get("id"),
            status="error",
        )

    @staticmethod
    def _normalize_result(result: ToolMessage) -> ToolMessage:
        if isinstance(result, ToolMessage) and _tool_message_is_error(result) and getattr(result, "status", None) != "error":
            return result.model_copy(update={"status": "error"})
        return result

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage],
    ) -> ToolMessage:
        blocked = self._blocked_repeated_failure(request)
        if blocked is not None:
            return blocked
        return self._normalize_result(handler(request))

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
    ) -> ToolMessage:
        blocked = self._blocked_repeated_failure(request)
        if blocked is not None:
            return blocked
        return self._normalize_result(await handler(request))


# Temporary import compatibility for extensions that referenced the old name.
ToolBudgetMiddleware = ToolExecutionGuardMiddleware

__all__ = ["ToolBudgetMiddleware", "ToolExecutionGuardMiddleware"]
