"""Recover failed tool calls through soft constraints and self-iteration."""
from __future__ import annotations

import hashlib
import json
import logging
import os as _os
import re
import threading
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any, override
from urllib.parse import urlparse

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse, ToolCallRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime

from src.utils.messages import latest_human_index, message_text as _message_text

logger = logging.getLogger(__name__)

# ── Constants ──

_ERROR_PREFIXES = ("error:", "failed:", "http error")
_ERROR_MARKERS = ("connection refused", "connection reset", "timeout", "500 ", "502 ", "503 ", "permission denied", "not found", "no such", "could not")
_TOOL_RECOVERY_LEGACY_BLOCK_FINAL_TOOLS_REQUESTED = _os.getenv("OCTO_BLOCK_FINAL_TOOLS_ON_REPEATED_ERROR") == "1"
_DUPLICATE_TOOL_CALL_LIMIT = int(_os.getenv("OCTO_DUPLICATE_TOOL_CALL_LIMIT", "3"))
_DUPLICATE_TOOL_CALL_HARD_LIMIT = int(_os.getenv("OCTO_DUPLICATE_TOOL_CALL_HARD_LIMIT", "8"))
_DUPLICATE_TOOL_CALL_HARD_STOP_ENABLED = _os.getenv("OCTO_DUPLICATE_TOOL_CALL_HARD_STOP") == "1"
_AUTO_DESCRIPTION_TOOLS: frozenset = frozenset()
_SOFT_BUDGET_FROM_MEMORY_KEY = "octo_soft_tool_budget"
_PLANNING_LOOP_FINALIZE_DUP = int(_os.getenv("OCTO_PLANNING_LOOP_FINALIZE_DUP", "12"))

# ── Dataclasses ──

@dataclass
class ToolErrorEntry:
    tool_name: str
    tool_call_id: str | None
    text_snippet: str
    is_recovery_guard: bool = False


# ── Helpers ──

def _tool_message_is_error(message: ToolMessage) -> bool:
    if getattr(message, "status", None) == "error":
        return True
    text = _message_text(message).strip().lower()
    return any(marker in text for marker in _ERROR_MARKERS) if not text.startswith(_ERROR_PREFIXES) else True


def _json_tool_payload_is_error(text: str) -> bool:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return False
    if isinstance(data, dict):
        return bool(data.get("error")) or bool(data.get("error_code"))
    return False


def _messages_since_latest_human(messages: list[object]) -> list[object]:
    start = latest_human_index(messages) + 1
    return messages[start:]


def _tool_call_args_signature(tool_name: str, args: object) -> str:
    """Stable string key: same args → same key."""
    if not isinstance(args, dict):
        args = {}
    stable = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    return f"{tool_name}:{hashlib.md5(stable.encode()).hexdigest()[:12]}"


def _tool_call_by_id(messages: list[object], tool_call_id: str | None) -> tuple[str | None, object | None]:
    if tool_call_id is None:
        return None, None
    for msg in messages:
        if isinstance(msg, ToolMessage) and getattr(msg, "tool_call_id", None) == tool_call_id:
            return str(getattr(msg, "name", None) or "tool") or None, getattr(msg, "additional_kwargs", None)
    return None, None


def _tool_error_entries(messages: list[object], *, include_recovery_guards: bool = False) -> list[ToolErrorEntry]:
    entries: list[ToolErrorEntry] = []
    for msg in messages[latest_human_index(messages) + 1:]:
        if not isinstance(msg, ToolMessage):
            continue
        text = _message_text(msg).strip().lower()
        is_error = _tool_message_is_error(msg) or _json_tool_payload_is_error(text)
        if not is_error:
            continue
        entries.append(ToolErrorEntry(
            tool_name=str(getattr(msg, "name", None) or "tool"),
            tool_call_id=getattr(msg, "tool_call_id", None),
            text_snippet=text[:420],
        ))
    return entries


def _recent_consecutive_errors(messages: list[object], *, include_recovery_guards: bool = False) -> list[ToolErrorEntry]:
    entries = _tool_error_entries(messages, include_recovery_guards=False)
    if not entries:
        return []
    end = len(entries)
    start = max(0, end - 20)
    return entries[start:end]


def _consecutive_recent_tool_signatures(messages: list[object], limit: int = 30) -> list[str]:
    sigs: list[str] = []
    for msg in reversed(messages[latest_human_index(messages) + 1:]):
        if isinstance(msg, ToolMessage):
            sigs.append(_tool_call_args_signature(
                str(getattr(msg, "name", None) or "tool"),
                getattr(msg, "additional_kwargs", None),
            ))
        if len(sigs) >= limit:
            break
    return sigs


def _duplicate_signature_recent_count(signatures: list[str], current_signature: str) -> int:
    return sum(1 for s in signatures[:15] if s == current_signature)


def _most_common_tool_count(entries: list[ToolErrorEntry], tool_name: str) -> int:
    return sum(1 for e in entries if e.tool_name == tool_name)


def _truncate_error(text: str, limit: int = 700) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:limit] + "..." if len(cleaned) > limit else cleaned


def _recovery_stage(error_count: int) -> str:
    if error_count <= 1:
        return "first_error"
    if error_count <= 3:
        return "retry_guidance"
    return "switch_tool"


def _recovery_instruction(entries: list[ToolErrorEntry]) -> str | None:
    if not entries:
        return None
    last = entries[-1]
    count = len(entries)
    if count <= 1:
        return (
            f"The tool `{last.tool_name}` returned an error. "
            "Inspect its schema and arguments, fix the issue, and retry. "
            f"Error preview: {_truncate_error(last.text_snippet)}"
        )
    if count <= 3:
        return (
            f"`{last.tool_name}` failed again ({count}x). "
            "Try a materially different approach: different tool, different arguments, or different strategy."
        )
    return (
        f"`{last.tool_name}` failed {count} consecutive times. "
        "Skip this step and continue with the next actionable step, or explain the blocker to the user."
    )


def _tool_texts(messages: list[object]) -> list[str]:
    return [_message_text(m) for m in messages if isinstance(m, ToolMessage)]


def _parse_soft_tool_budget(text: str) -> int | None:
    try:
        return int(text.strip())
    except (ValueError, TypeError):
        return None


def _runtime_soft_tool_budget(context: dict[str, Any]) -> int | None:
    val = context.get("soft_tool_budget") or context.get("tool_budget")
    return _parse_soft_tool_budget(val) if val is not None else None


def _system_memory_soft_tool_budget() -> int | None:
    try:
        from src.agents.memory.simplemem_bridge import get_simplemem_bridge
        bridge = get_simplemem_bridge()
        val = bridge.get_fact(_SOFT_BUDGET_FROM_MEMORY_KEY)
        return _parse_soft_tool_budget(val) if val else None
    except Exception:
        return None


def _soft_tool_budget_guidance(tool_count: int, budget: int) -> str:
    return (
        "<tool_soft_budget_policy>\n"
        f"This turn has used {tool_count} tool calls, approaching the soft budget of {budget}. "
        "Prefer non-tool reasoning or concise answers for the remaining work. "
        "Only use tools when essential.\n"
        "</tool_soft_budget_policy>"
    )


def _recovery_guard_message(*, content: str, name: str, tool_call_id: str | None) -> ToolMessage:
    return ToolMessage(content=content, name=name, tool_call_id=tool_call_id, status="success")


def _duplicate_step_summary_guard_message(*, tool_name: str, dup_count: int, tool_call_id: str | None) -> ToolMessage:
    return _recovery_guard_message(
        content=(
            f"Note: `{tool_name}` has been called with the same arguments {dup_count} times. "
            "If the previous call already succeeded, proceed with the result. "
            "If it failed repeatedly, switch strategy."
        ),
        name=tool_name,
        tool_call_id=tool_call_id,
    )


def _alternate_tool_guidance(tool_name: str, tool_error_count: int) -> str:
    return (
        f"`{tool_name}` has failed {tool_error_count} times in this turn. "
        "Stop using this tool and try a different approach or tool."
    )


def _is_recovery_guard_message(message: ToolMessage) -> bool:
    text = _message_text(message).strip().lower()
    return text.startswith(("error:", "note:", "the tool `")) and "failed" in text


def _soft_constraint_reflection_already_injected(messages: list[object], kind: str) -> bool:
    marker = f"kind=\"{kind}\""
    for msg in messages:
        if isinstance(msg, SystemMessage) and marker in _message_text(msg):
            return True
    return False


def _self_constraint_memory_guidance(*, kind: str, observation: str, suggested_lesson: str, user_goal: str) -> str:
    return (
        f"<self_constraint kind=\"{kind}\">\n"
        f"Observation: {observation}\n"
        f"Suggested lesson: {suggested_lesson}\n"
        f"User goal: {user_goal[:300]}\n"
        "</self_constraint>"
    )


def _auto_description(tool_name: str, args: dict[str, Any]) -> str:
    return "auto"


def _latest_human_text(messages: list[object]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) or getattr(msg, "type", None) == "human":
            return _message_text(msg)
    return ""


# ── Middleware class ──

class ToolBudgetMiddleware(AgentMiddleware[AgentState]):
    """Recover tool failures and provide soft budget guidance."""

    def __init__(
        self,
        max_tool_messages: int | None = None,
        switch_tool_errors: int = 3,
        discover_tool_errors: int = 5,
        final_failure_errors: int = 5,
    ):
        super().__init__()
        self.max_tool_messages = max_tool_messages
        self.switch_tool_errors = switch_tool_errors
        self.discover_tool_errors = discover_tool_errors
        self.final_failure_errors = final_failure_errors

    def _effective_soft_tool_budget(self, runtime: Runtime | None) -> int | None:
        context = runtime.context if runtime is not None and runtime.context else {}
        runtime_budget = _runtime_soft_tool_budget(context)
        if runtime_budget is not None:
            return runtime_budget
        memory_budget = _system_memory_soft_tool_budget()
        if memory_budget is not None:
            return memory_budget
        return self.max_tool_messages

    def _inject_recovery_guidance(self, state: AgentState, runtime: Runtime | None) -> dict | None:
        messages = list(state.get("messages", []))
        if not messages:
            return None
        runtime_state = dict(state.get("runtime") or {})

        # Tool error recovery
        if isinstance(messages[-1], ToolMessage):
            entries = _recent_consecutive_errors(messages)
            if len(entries) >= self.final_failure_errors:
                if not _soft_constraint_reflection_already_injected(messages, "tool_failure_loop"):
                    runtime_state["self_feedback_action"] = "self_iterate_tool_failure_loop_with_memory"
                    runtime_state["tool_recovery"] = {
                        "stage": "final_soft_constraint",
                        "error_count": len(entries),
                        "last_tool": entries[-1].tool_name,
                        "hard_stop": False,
                    }
                    return {
                        "messages": [SystemMessage(content=_self_constraint_memory_guidance(
                            kind="tool_failure_loop",
                            observation=f"{len(entries)} consecutive tool failures; latest: {entries[-1].tool_name}.",
                            suggested_lesson="After repeated tool failures, skip the failing step or explain the blocker.",
                            user_goal=_latest_human_text(messages),
                        ))],
                        "runtime": runtime_state,
                    }

            instruction = _recovery_instruction(entries)
            if instruction is not None:
                runtime_state["tool_recovery"] = {
                    "stage": _recovery_stage(len(entries)),
                    "error_count": len(entries),
                    "last_tool": entries[-1].tool_name,
                }
                return {"messages": [SystemMessage(content=instruction)], "runtime": runtime_state}

        # Soft tool budget
        tool_texts = _tool_texts(messages)
        soft_budget = self._effective_soft_tool_budget(runtime)
        if soft_budget is not None and len(tool_texts) >= soft_budget:
            if not any(isinstance(m, SystemMessage) and "<tool_soft_budget_policy>" in _message_text(m)
                       for m in _messages_since_latest_human(messages)):
                runtime_state["tool_soft_budget"] = {
                    "status": "advisory",
                    "tool_messages": len(tool_texts),
                    "soft_budget": soft_budget,
                }
                return {
                    "messages": [SystemMessage(content=_soft_tool_budget_guidance(len(tool_texts), soft_budget))],
                    "runtime": runtime_state,
                }

        return None

    def _with_auto_description(self, request: ToolCallRequest) -> ToolCallRequest:
        return request

    def _blocked_repeated_tool_message(self, request: ToolCallRequest) -> ToolMessage | None:
        messages = list((request.state or {}).get("messages", [])) if isinstance(request.state, dict) else []
        tool_name_current = request.tool.name if request.tool else str(request.tool_call.get("name") or "unknown")
        current_sig = _tool_call_args_signature(tool_name_current, request.tool_call.get("args"))
        recent_signatures = _consecutive_recent_tool_signatures(messages, limit=60)
        dup_count = _duplicate_signature_recent_count(recent_signatures, current_sig)

        if (
            _DUPLICATE_TOOL_CALL_HARD_STOP_ENABLED
            and _DUPLICATE_TOOL_CALL_HARD_LIMIT > 0
            and dup_count >= _DUPLICATE_TOOL_CALL_HARD_LIMIT
        ):
            return _recovery_guard_message(
                content=f"Error: `{tool_name_current}` repeated identical args {dup_count}x. Switch strategy or skip.",
                name=tool_name_current,
                tool_call_id=request.tool_call.get("id"),
            )
        if dup_count >= _DUPLICATE_TOOL_CALL_LIMIT:
            return _duplicate_step_summary_guard_message(
                tool_name=tool_name_current,
                dup_count=dup_count,
                tool_call_id=request.tool_call.get("id"),
            )
        return None

    @staticmethod
    def _mark_error_result(result: ToolMessage) -> ToolMessage:
        if not isinstance(result, ToolMessage):
            return result
        if getattr(result, "status", None) == "error":
            return result
        text = _message_text(result).strip().lower()
        if text.startswith(_ERROR_PREFIXES) or any(marker in text for marker in _ERROR_MARKERS) or _json_tool_payload_is_error(text):
            return result.model_copy(update={"status": "error"})
        return result

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._inject_recovery_guidance(state, runtime)

    @override
    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._inject_recovery_guidance(state, runtime)

    @override
    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolMessage]) -> ToolMessage:
        blocked = self._blocked_repeated_tool_message(request)
        if blocked is not None:
            return blocked
        request = self._with_auto_description(request)
        return self._mark_error_result(handler(request))

    @override
    async def awrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]]) -> ToolMessage:
        blocked = self._blocked_repeated_tool_message(request)
        if blocked is not None:
            return blocked
        request = self._with_auto_description(request)
        return self._mark_error_result(await handler(request))

    def _maybe_finalize(self, state: AgentState, runtime: Runtime) -> dict | None:
        messages = list(state.get("messages", []))
        if not messages:
            return None
        last_message = messages[-1]
        if getattr(last_message, "type", None) != "ai":
            return None
        if not getattr(last_message, "tool_calls", None):
            return None

        error_entries = _tool_error_entries(messages)
        if len(error_entries) >= self.final_failure_errors:
            runtime_state = dict(state.get("runtime") or {})
            runtime_state["tool_recovery"] = {
                "stage": "final_soft_review",
                "error_count": len(error_entries),
                "hard_stop": False,
                "action": "let_model_self_iterate_after_repeated_tool_failures",
            }
            return {"runtime": runtime_state}
        return None

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_finalize(state, runtime)

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_finalize(state, runtime)
