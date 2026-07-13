"""Current contract tests for advisory tool recovery.

The middleware no longer owns research closure, RAG lesson persistence, or
mandatory tool switching. It marks real tool errors, gives the model concise
recovery guidance, and uses a bounded duplicate-call guard without turning a
soft budget into task termination.
"""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from src.agents.middlewares.tool_budget_middleware import ToolBudgetMiddleware


class _Runtime:
    def __init__(self, context: dict) -> None:
        self.context = context


def _ai_tool_call(call_id: str, *, name: str = "bash", args: dict | None = None) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args or {"command": "pwd"}, "id": call_id}],
    )


def _tool_error(call_id: str, *, name: str = "bash", content: str = "Error: failed") -> ToolMessage:
    return ToolMessage(content=content, name=name, tool_call_id=call_id, status="error")


def _request(messages: list[object], *, name: str = "bash", args: dict | None = None) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args or {"command": "pwd"}, "id": "call-next"},
        tool=None,
        state={"messages": messages},
        runtime=None,
    )


def test_successful_tool_history_does_not_trigger_finalization() -> None:
    middleware = ToolBudgetMiddleware()
    messages: list[object] = [HumanMessage(content="inspect")]
    for index in range(20):
        call_id = f"call-{index}"
        messages.extend([_ai_tool_call(call_id), ToolMessage(content="ok", name="bash", tool_call_id=call_id)])
    messages.append(_ai_tool_call("call-final"))

    assert middleware.after_model({"messages": messages}, None) is None


def test_first_tool_error_injects_repair_guidance() -> None:
    middleware = ToolBudgetMiddleware()
    state = {
        "messages": [
            HumanMessage(content="run a command"),
            _ai_tool_call("call-1"),
            _tool_error("call-1", content="Error invoking tool 'bash': description: Field required"),
        ]
    }

    update = middleware.before_model(state, None)

    assert update is not None
    assert "Inspect its schema and arguments" in update["messages"][0].content
    assert update["runtime"]["tool_recovery"]["stage"] == "first_error"


def test_repeated_failures_escalate_to_advisory_self_constraint() -> None:
    middleware = ToolBudgetMiddleware(final_failure_errors=5)
    messages: list[object] = [HumanMessage(content="complete task")]
    for index in range(5):
        call_id = f"call-{index}"
        messages.extend([_ai_tool_call(call_id), _tool_error(call_id)])

    update = middleware.before_model({"messages": messages}, None)

    assert update is not None
    assert '<self_constraint kind="tool_failure_loop">' in update["messages"][0].content
    recovery = update["runtime"]["tool_recovery"]
    assert recovery["stage"] == "final_soft_constraint"
    assert recovery["hard_stop"] is False


def test_existing_self_constraint_is_not_injected_twice() -> None:
    middleware = ToolBudgetMiddleware(final_failure_errors=2)
    messages: list[object] = [HumanMessage(content="complete task")]
    for index in range(2):
        call_id = f"call-{index}"
        messages.extend([_ai_tool_call(call_id), _tool_error(call_id)])
    messages.append(SystemMessage(content='<self_constraint kind="tool_failure_loop">already</self_constraint>'))

    assert middleware.before_model({"messages": messages}, None) is None


def test_duplicate_call_guard_returns_a_nonfatal_strategy_note() -> None:
    middleware = ToolBudgetMiddleware()
    messages: list[object] = [HumanMessage(content="run command")]
    for index in range(3):
        call_id = f"call-{index}"
        messages.extend([_ai_tool_call(call_id), ToolMessage(content="ok", name="bash", tool_call_id=call_id)])

    handler_called = False

    def handler(_: ToolCallRequest) -> ToolMessage:
        nonlocal handler_called
        handler_called = True
        return ToolMessage(content="executed", name="bash", tool_call_id="call-next")

    result = middleware.wrap_tool_call(_request(messages), handler)

    assert handler_called is False
    assert result.status == "success"
    assert "same arguments" in result.content
    assert "switch strategy" in result.content


def test_tool_call_arguments_are_not_mutated() -> None:
    middleware = ToolBudgetMiddleware()
    request = _request([], args={"command": "pwd"})

    result = middleware.wrap_tool_call(
        request,
        lambda current: ToolMessage(
            content=current.tool_call["args"]["command"],
            name="bash",
            tool_call_id="call-next",
        ),
    )

    assert result.content == "pwd"
    assert request.tool_call["args"] == {"command": "pwd"}


def test_error_payloads_are_normalized_to_error_status() -> None:
    middleware = ToolBudgetMiddleware()

    plain = middleware.wrap_tool_call(
        _request([]),
        lambda _: ToolMessage(content="HTTP error 502", name="bash", tool_call_id="call-next"),
    )
    structured = middleware.wrap_tool_call(
        _request([]),
        lambda _: ToolMessage(content='{"error": "command failed"}', name="bash", tool_call_id="call-next"),
    )

    assert plain.status == "error"
    assert structured.status == "error"


def test_runtime_soft_budget_is_advisory() -> None:
    middleware = ToolBudgetMiddleware()
    messages = [HumanMessage(content="inspect"), ToolMessage(content="ok", name="bash", tool_call_id="call-1")]

    update = middleware.before_model({"messages": messages}, _Runtime({"soft_tool_budget": 1}))

    assert update is not None
    assert "<tool_soft_budget_policy>" in update["messages"][0].content
    assert update["runtime"]["tool_soft_budget"]["status"] == "advisory"


def test_soft_budget_counts_only_latest_human_turn() -> None:
    middleware = ToolBudgetMiddleware(max_tool_messages=2)
    messages = [
        HumanMessage(content="old"),
        ToolMessage(content="old-1", name="bash", tool_call_id="old-1"),
        ToolMessage(content="old-2", name="bash", tool_call_id="old-2"),
        HumanMessage(content="new"),
        ToolMessage(content="new-1", name="bash", tool_call_id="new-1"),
    ]

    assert middleware.before_model({"messages": messages}, None) is None


def test_after_model_records_soft_review_without_replacing_tool_calls() -> None:
    middleware = ToolBudgetMiddleware(final_failure_errors=2)
    messages: list[object] = [HumanMessage(content="complete")]
    for index in range(2):
        call_id = f"call-{index}"
        messages.extend([_ai_tool_call(call_id), _tool_error(call_id)])
    final_call = _ai_tool_call("call-final")
    messages.append(final_call)

    update = middleware.after_model({"messages": messages}, None)

    assert update is not None
    assert "messages" not in update
    assert final_call.tool_calls
    assert update["runtime"]["tool_recovery"]["hard_stop"] is False


def test_async_tool_wrapper_matches_sync_error_normalization() -> None:
    middleware = ToolBudgetMiddleware()

    async def handler(_: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content='{"error": "failed"}', name="bash", tool_call_id="call-next")

    result = asyncio.run(middleware.awrap_tool_call(_request([]), handler))

    assert result.status == "error"
