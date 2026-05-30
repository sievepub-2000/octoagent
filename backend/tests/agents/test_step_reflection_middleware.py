from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agents.middlewares.step_reflection_middleware import StepReflectionMiddleware


def _messages() -> list:
    return [
        HumanMessage(content="complete the task"),
        AIMessage(content="", tool_calls=[{"id": "call-1", "name": "web_fetch", "args": {"url": "https://example.com"}}]),
        ToolMessage(content="403 Forbidden", tool_call_id="call-1", name="web_fetch"),
    ]


def test_step_reflection_uses_goal_autopilot_branching_rules() -> None:
    middleware = StepReflectionMiddleware(every_n=1)

    update = middleware._maybe_inject({"messages": _messages(), "runtime": {"execution_mode": "goal_autopilot"}})

    assert update is not None
    content = update["messages"][0].content
    assert 'execution_mode="goal_autopilot"' in content
    assert "至少尝试两种不同策略" in content
    assert update["runtime"]["step_review"]["execution_mode"] == "goal_autopilot"


def test_step_reflection_uses_assisted_user_question_branching_rules() -> None:
    middleware = StepReflectionMiddleware(every_n=1)

    update = middleware._maybe_inject({"messages": _messages(), "runtime": {"execution_mode": "assisted"}})

    assert update is not None
    content = update["messages"][0].content
    assert 'execution_mode="assisted"' in content
    assert "问一个清晰问题" in content
