"""Regression tests for the execution-seam tool guard."""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from src.agents.middlewares.tool_budget_middleware import ToolExecutionGuardMiddleware


def _ai_tool_call(call_id: str, *, name: str = "bash", args: dict | None = None) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args or {"command": "pwd"}, "id": call_id}],
    )


def _request(messages: list[object], *, name: str = "bash", args: dict | None = None) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args or {"command": "pwd"}, "id": "call-next"},
        tool=None,
        state={"messages": messages},
        runtime=None,
    )


def test_success_payload_words_do_not_become_errors() -> None:
    middleware = ToolExecutionGuardMiddleware()
    result = middleware.wrap_tool_call(
        _request([]),
        lambda _: ToolMessage(
            content=(
                "Source audit: the phrase 'not found' is documented here; "
                "'permission denied' and 'could not connect' are example log strings."
            ),
            name="read_file",
            tool_call_id="call-next",
            status="success",
        ),
    )

    assert result.status == "success"


def test_explicit_error_payloads_are_normalized() -> None:
    middleware = ToolExecutionGuardMiddleware()

    prefix = middleware.wrap_tool_call(
        _request([]),
        lambda _: ToolMessage(content="Error: command failed", name="bash", tool_call_id="call-next"),
    )
    structured = middleware.wrap_tool_call(
        _request([]),
        lambda _: ToolMessage(content='{"error_code": "EACCES"}', name="bash", tool_call_id="call-next"),
    )

    assert prefix.status == "error"
    assert structured.status == "error"


def test_identical_successful_calls_are_never_blocked() -> None:
    middleware = ToolExecutionGuardMiddleware(max_identical_failures=3)
    messages: list[object] = [HumanMessage(content="inspect repeatedly")]
    for index in range(12):
        call_id = f"call-{index}"
        messages.extend(
            [
                _ai_tool_call(call_id),
                ToolMessage(content="ok", name="bash", tool_call_id=call_id, status="success"),
            ]
        )

    handler_called = False

    def handler(_: ToolCallRequest) -> ToolMessage:
        nonlocal handler_called
        handler_called = True
        return ToolMessage(content="executed", name="bash", tool_call_id="call-next")

    result = middleware.wrap_tool_call(_request(messages), handler)

    assert handler_called is True
    assert result.content == "executed"
    assert result.status == "success"


def test_fourth_identical_failed_call_is_blocked_at_execution_seam() -> None:
    middleware = ToolExecutionGuardMiddleware(max_identical_failures=3)
    messages: list[object] = [HumanMessage(content="run command")]
    for index in range(3):
        call_id = f"call-{index}"
        messages.extend(
            [
                _ai_tool_call(call_id),
                ToolMessage(
                    content="Error: command failed",
                    name="bash",
                    tool_call_id=call_id,
                    status="error",
                ),
            ]
        )

    handler_called = False

    def handler(_: ToolCallRequest) -> ToolMessage:
        nonlocal handler_called
        handler_called = True
        return ToolMessage(content="unexpected", name="bash", tool_call_id="call-next")

    result = middleware.wrap_tool_call(_request(messages), handler)

    assert handler_called is False
    assert result.status == "error"
    assert "failed with identical arguments 3 times" in result.content


def test_changed_arguments_remain_available_after_failures() -> None:
    middleware = ToolExecutionGuardMiddleware(max_identical_failures=1)
    messages = [
        HumanMessage(content="run command"),
        _ai_tool_call("call-1", args={"command": "pwd"}),
        ToolMessage(content="Error: failed", name="bash", tool_call_id="call-1", status="error"),
    ]

    result = middleware.wrap_tool_call(
        _request(messages, args={"command": "whoami"}),
        lambda current: ToolMessage(
            content=current.tool_call["args"]["command"],
            name="bash",
            tool_call_id="call-next",
        ),
    )

    assert result.content == "whoami"
    assert result.status == "success"


def test_async_wrapper_matches_sync_behavior() -> None:
    middleware = ToolExecutionGuardMiddleware()

    async def handler(_: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content='{"error": "failed"}', name="bash", tool_call_id="call-next")

    result = asyncio.run(middleware.awrap_tool_call(_request([]), handler))

    assert result.status == "error"
