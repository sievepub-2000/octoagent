"""User confirmation gate for dangerous host-level tools."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from src.agents.thread_state import merge_runtime_state
from src.utils.messages import message_text as _message_text

_EMIT_INIT_LOCK = threading.Lock()
_NODE_EMIT_WINDOW = 3.0

_APPROVAL_WORDS = ("确认", "同意", "批准", "允许", "继续", "yes", "y", "approve", "approved", "confirm", "confirmed", "go ahead")
_DENY_WORDS = ("取消", "拒绝", "不同意", "不要", "停止", "no", "deny", "denied", "cancel", "stop")
_MARKER = '<dangerous_tool_confirmation origin="dangerous_tool_confirmation_middleware"'


class DangerousToolConfirmationState(AgentState):
    runtime: Annotated[dict[str, Any] | None, merge_runtime_state]


def _tool_name(request: ToolCallRequest) -> str:
    if request.tool is not None:
        return request.tool.name
    return str(request.tool_call.get("name") or "unknown")


def _tool_metadata(request: ToolCallRequest) -> dict[str, Any]:
    if request.tool is None:
        return {}
    return dict(getattr(request.tool, "metadata", None) or {})


def _requires_confirmation(request: ToolCallRequest) -> bool:
    metadata = _tool_metadata(request)
    active_mode = str(metadata.get("active_permission_mode") or "").strip().lower()
    if active_mode == "system":
        return False
    if "requires_confirmation" in metadata:
        return bool(metadata.get("requires_confirmation"))
    return metadata.get("permission_scope") == "system"


def _signature(tool_name: str, args: Any) -> str:
    payload = json.dumps({"tool": tool_name, "args": args}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]




def _latest_human_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "human":
            return _message_text(message).strip().lower()
    return ""


def _human_count(messages: list[Any]) -> int:
    return sum(1 for message in messages if getattr(message, "type", "") == "human")


def _user_decision_for_pending(messages: list[Any], pending: dict[str, Any] | None) -> str | None:
    if not pending:
        return None
    pending_human_count = pending.get("human_count")
    if isinstance(pending_human_count, int) and _human_count(messages) <= pending_human_count:
        return None
    text = _latest_human_text(messages)
    if not text:
        return None
    stripped = text.strip()
    if any(word in text for word in _DENY_WORDS) or stripped in {"2", "2.", "２"}:
        return "deny"
    if any(word in text for word in _APPROVAL_WORDS) or stripped in {"1", "1.", "１"}:
        return "approve"
    return None


def _confirmation_already_visible(messages: list[Any], signature: str) -> bool:
    """True if a confirmation prompt for ``signature`` is already the most recent
    bot output and the user has not replied since.

    Used to avoid re-emitting an identical confirmation message every time the
    tool node re-enters while ``dangerous_tool_pending`` is set. Fail-open: if no
    matching marker is found we return ``False`` so the prompt is emitted.
    """
    if not signature:
        return False
    marker = f'signature="{signature}"'
    for message in reversed(messages):
        if getattr(message, "type", "") == "human":
            return False
        text = _message_text(message)
        if _MARKER in text and marker in text:
            return True
    return False


def _runtime_state(request: ToolCallRequest) -> dict[str, Any]:
    state = getattr(request, "state", None)
    if isinstance(state, dict):
        runtime = state.get("runtime")
        if isinstance(runtime, dict):
            return dict(runtime)
    return {}


def _set_runtime_state(request: ToolCallRequest, runtime_state: dict[str, Any]) -> None:
    state = getattr(request, "state", None)
    if isinstance(state, dict):
        state["runtime"] = runtime_state


def _messages(request: ToolCallRequest) -> list[Any]:
    state = getattr(request, "state", None)
    if isinstance(state, dict):
        messages = state.get("messages")
        if isinstance(messages, list):
            return messages
    return []


def _build_confirmation_message(tool_name: str, args: Any, signature: str, tool_call_id: str) -> ToolMessage:
    args_preview = json.dumps(args, ensure_ascii=False, indent=2, default=str)[:3000]
    content = "\n".join(
        [
            f'{_MARKER} tool="{tool_name}" signature="{signature}">',
            "即将执行需要授权的能力，任务已暂停，等待你的选择。",
            "",
            f"工具: `{tool_name}`",
            "参数:",
            "```json",
            args_preview,
            "```",
            "",
            "1. 确认并继续执行本次操作",
            "2. 取消本次操作并停止当前任务",
            "",
            "请只回复 `1`/`确认` 或 `2`/`取消`。在你回复前，OctoAgent 不会执行该操作。",
            "</dangerous_tool_confirmation>",
        ]
    )
    return ToolMessage(content=content, tool_call_id=tool_call_id, name="ask_clarification")


def _build_cancelled_message(tool_name: str, signature: str, tool_call_id: str) -> ToolMessage:
    content = "\n".join(
        [
            f'{_MARKER} tool="{tool_name}" signature="{signature}" cancelled="true">',
            "已取消该操作，当前任务已停止。",
            "",
            f"工具: `{tool_name}`",
            "</dangerous_tool_confirmation>",
        ]
    )
    return ToolMessage(content=content, tool_call_id=tool_call_id, name="ask_clarification")


class DangerousToolConfirmationMiddleware(AgentMiddleware[DangerousToolConfirmationState]):
    """Pause dangerous tool execution until the user explicitly confirms."""

    state_schema = DangerousToolConfirmationState

    def _claim_emission(self, messages: list[Any]) -> bool:
        """Return True if this handler may emit a confirmation for the current node pass.

        Parallel dangerous tool calls in one node pass share the same ``messages``
        list object; only the first claimant emits, siblings (same list identity
        within ``_NODE_EMIT_WINDOW`` seconds) halt silently. Fail-open on any error.
        """
        import time as _time

        try:
            if getattr(self, "_emit_lock", None) is None:
                with _EMIT_INIT_LOCK:
                    if getattr(self, "_emit_lock", None) is None:
                        self._emit_node_id = None
                        self._emit_node_ts = 0.0
                        self._emit_lock = threading.Lock()
            node_id = id(messages)
            now = _time.monotonic()
            with self._emit_lock:
                if self._emit_node_id == node_id and (now - self._emit_node_ts) < _NODE_EMIT_WINDOW:
                    return False
                self._emit_node_id = node_id
                self._emit_node_ts = now
                return True
        except Exception:  # noqa: BLE001 - never block tool flow on dedup bookkeeping
            return True

    def _maybe_block(self, request: ToolCallRequest) -> Command | None:
        tool_name = _tool_name(request)
        args = request.tool_call.get("args", {})
        sig = _signature(tool_name, args)
        tool_call_id = str(request.tool_call.get("id") or "dangerous-tool-confirmation")
        runtime_state = _runtime_state(request)
        messages = _messages(request)
        pending = runtime_state.get("dangerous_tool_pending")
        pending = pending if isinstance(pending, dict) else None

        if pending and pending.get("signature") != sig:
            pending_tool_name = str(pending.get("tool_name") or "unknown")
            pending_signature = str(pending.get("signature") or "")
            decision = _user_decision_for_pending(messages, pending)
            if decision == "deny":
                runtime_state["dangerous_tool_pending"] = None
                runtime_state[f"dangerous_tool_denied:{pending_signature}"] = True
                _set_runtime_state(request, runtime_state)
                return Command(
                    update={
                        "messages": [_build_cancelled_message(pending_tool_name, pending_signature, tool_call_id)],
                        "runtime": runtime_state,
                    },
                    goto=END,
                )
            if _confirmation_already_visible(messages, pending_signature):
                _set_runtime_state(request, runtime_state)
                return Command(update={"runtime": runtime_state}, goto=END)
            if not self._claim_emission(messages):
                return Command(goto=END)
            return Command(
                update={
                    "messages": [
                        _build_confirmation_message(
                            pending_tool_name,
                            pending.get("args", {}),
                            pending_signature,
                            tool_call_id,
                        )
                    ],
                    "runtime": runtime_state,
                },
                goto=END,
            )

        if not _requires_confirmation(request):
            return None

        approved_key = f"dangerous_tool_approved:{sig}"
        if runtime_state.get(approved_key):
            return None

        decision = _user_decision_for_pending(messages, pending)
        if decision == "approve":
            runtime_state[approved_key] = True
            runtime_state["dangerous_tool_pending"] = None
            _set_runtime_state(request, runtime_state)
            return None
        if decision == "deny":
            runtime_state[f"dangerous_tool_denied:{sig}"] = True
            runtime_state["dangerous_tool_pending"] = None
            _set_runtime_state(request, runtime_state)
            return Command(
                update={"messages": [_build_cancelled_message(tool_name, sig, tool_call_id)], "runtime": runtime_state},
                goto=END,
            )

        if _confirmation_already_visible(messages, sig):
            _set_runtime_state(request, runtime_state)
            return Command(update={"runtime": runtime_state}, goto=END)
        if not self._claim_emission(messages):
            return Command(goto=END)
        runtime_state["dangerous_tool_pending"] = {
            "tool_name": tool_name,
            "signature": sig,
            "args": args,
            "human_count": _human_count(messages),
        }
        _set_runtime_state(request, runtime_state)
        return Command(
            update={
                "messages": [
                    _build_confirmation_message(
                        tool_name,
                        args,
                        sig,
                        tool_call_id,
                    )
                ],
                "runtime": runtime_state,
            },
            goto=END,
        )

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        blocked = self._maybe_block(request)
        if blocked is not None:
            return blocked
        return handler(request)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        blocked = self._maybe_block(request)
        if blocked is not None:
            return blocked
        return await handler(request)


__all__ = ["DangerousToolConfirmationMiddleware"]
