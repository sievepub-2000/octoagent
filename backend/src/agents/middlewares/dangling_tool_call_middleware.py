"""Middleware to fix dangling tool calls in message history.

A dangling tool call occurs when an AIMessage contains tool_calls but there are
no corresponding ToolMessages in the history (e.g., due to user interruption or
request cancellation). This causes LLM errors due to incomplete message format.

This middleware intercepts the model call to detect and patch such gaps by
inserting synthetic ToolMessages with an error indicator immediately after the
AIMessage that made the tool calls, ensuring correct message ordering.

Note: Uses wrap_model_call instead of before_model to ensure patches are inserted
at the correct positions (immediately after each dangling AIMessage), not appended
to the end of the message list as before_model + add_messages reducer would do.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.models.semantics import _normalize_ai_message_tool_calls

logger = logging.getLogger(__name__)


class DanglingToolCallMiddleware(AgentMiddleware[AgentState]):
    """Inserts placeholder ToolMessages for dangling tool calls before model invocation.

    Scans the message history for AIMessages whose tool_calls lack corresponding
    ToolMessages, and injects synthetic error responses immediately after the
    offending AIMessage so the LLM receives a well-formed conversation.
    """

    def _normalize_ai_tool_call_text(self, messages: list) -> tuple[list, bool]:
        normalized: list = []
        changed = False
        for msg in messages:
            if isinstance(msg, AIMessage):
                normalized_msg = _normalize_ai_message_tool_calls(msg)
                normalized.append(normalized_msg)
                changed = changed or normalized_msg is not msg
                continue
            normalized.append(msg)
        return normalized, changed

    def _normalize_response(self, response: ModelResponse) -> ModelResponse:
        normalized, changed = self._normalize_ai_tool_call_text(list(response.result))
        if not changed:
            return response
        logger.warning("Normalized XML-ish assistant tool-call text into structured tool_calls")
        return ModelResponse(result=normalized, structured_response=response.structured_response)

    def _repair_trailing_assistant_run(self, messages: list) -> tuple[list, bool]:
        trailing_start = len(messages)
        while trailing_start > 0 and getattr(messages[trailing_start - 1], "type", None) == "ai":
            trailing_start -= 1
        trailing = messages[trailing_start:]
        if not trailing:
            return messages, False

        last_text = str(getattr(trailing[-1], "content", "") or "")
        has_runtime_failure_tail = "我在执行这轮任务时遇到了运行时错误" in last_text or "NormalizedModelError" in last_text
        if len(trailing) < 2 and not has_runtime_failure_tail:
            return messages, False

        preserved: list[str] = []
        for index, msg in enumerate(trailing, start=1):
            text = str(getattr(msg, "content", "") or "").strip()
            tool_calls = getattr(msg, "tool_calls", None) or []
            if tool_calls:
                preserved.append(f"assistant[{index}] requested tool calls: {[tc.get('name') for tc in tool_calls if isinstance(tc, dict)]}")
            if text:
                preserved.append(f"assistant[{index}]: {text[:800]}")

        repaired = list(messages[:trailing_start])
        repaired.append(
            SystemMessage(
                content=(
                    "[OctoAgent message contract repair]\n"
                    "The previous request ended with assistant-only runtime/error/tool-call text. "
                    "That tail is preserved here for continuity but must not be sent as consecutive assistant messages.\n" + "\n".join(preserved[:6])
                )
            )
        )
        repaired.append(HumanMessage(content=("Continue the latest unfinished user task. Do not repeat prior runtime error text. If a tool is required, call it through the structured tool-call interface.")))
        logger.warning("Repaired trailing assistant-only message run before model invocation")
        return repaired, True

    def _build_patched_messages(self, messages: list) -> list | None:
        """Return a new message list with patches inserted at the correct positions.

        For each AIMessage with dangling tool_calls (no corresponding ToolMessage),
        a synthetic ToolMessage is inserted immediately after that AIMessage.
        Returns None if no patches are needed.
        """
        normalized_messages, normalized_changed = self._normalize_ai_tool_call_text(messages)

        # Collect IDs of all existing ToolMessages
        existing_tool_msg_ids: set[str] = set()
        for msg in normalized_messages:
            if isinstance(msg, ToolMessage):
                existing_tool_msg_ids.add(msg.tool_call_id)

        # Check if any patching is needed
        needs_patch = False
        for msg in normalized_messages:
            if getattr(msg, "type", None) != "ai":
                continue
            for tc in getattr(msg, "tool_calls", None) or []:
                tc_id = tc.get("id")
                if tc_id and tc_id not in existing_tool_msg_ids:
                    needs_patch = True
                    break
            if needs_patch:
                break

        if not needs_patch:
            repaired_messages, repaired_changed = self._repair_trailing_assistant_run(normalized_messages)
            if normalized_changed or repaired_changed:
                return repaired_messages
            return None

        # Build new list with patches inserted right after each dangling AIMessage
        patched: list = []
        patched_ids: set[str] = set()
        patch_count = 0
        for msg in normalized_messages:
            patched.append(msg)
            if getattr(msg, "type", None) != "ai":
                continue
            for tc in getattr(msg, "tool_calls", None) or []:
                tc_id = tc.get("id")
                if tc_id and tc_id not in existing_tool_msg_ids and tc_id not in patched_ids:
                    patched.append(
                        ToolMessage(
                            content="[Tool call was interrupted and did not return a result.]",
                            tool_call_id=tc_id,
                            name=tc.get("name", "unknown"),
                            status="error",
                        )
                    )
                    patched_ids.add(tc_id)
                    patch_count += 1

        logger.warning(f"Injecting {patch_count} placeholder ToolMessage(s) for dangling tool calls")
        repaired_messages, _ = self._repair_trailing_assistant_run(patched)
        return repaired_messages

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        patched = self._build_patched_messages(request.messages)
        if patched is not None:
            request = request.override(messages=patched)
        return self._normalize_response(handler(request))

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        patched = self._build_patched_messages(request.messages)
        if patched is not None:
            request = request.override(messages=patched)
        return self._normalize_response(await handler(request))
