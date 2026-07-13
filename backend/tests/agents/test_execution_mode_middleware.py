from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.middlewares.execution_middleware import ExecutionMiddleware, resolve_execution_mode


class _Runtime:
    def __init__(self, context: dict[str, object] | None = None) -> None:
        self.context = context or {}


def test_assisted_mode_is_default_for_regular_tool_action() -> None:
    assert resolve_execution_mode({"dialogue_route": "tool_action"}, "修复这个问题") == "assisted"


def test_goal_autopilot_mode_uses_runtime_goal_signal() -> None:
    assert resolve_execution_mode({"mode": "goal", "dialogue_route": "tool_action"}, "完成这个任务") == "goal_autopilot"
    assert resolve_execution_mode({"thinking_enabled": True, "dialogue_route": "deep_agent"}, "深度分析并修复") == "goal_autopilot"


def test_plan_only_forces_assisted_even_when_thinking_enabled() -> None:
    assert resolve_execution_mode({"thinking_enabled": True, "dialogue_route": "plan_only"}, "先给方案，等我确认") == "assisted"


def test_execution_mode_contract_is_injected_before_latest_user_turn() -> None:
    middleware = ExecutionMiddleware()
    user = HumanMessage(content="深度分析并修复")

    update = middleware.before_agent({"messages": [user], "runtime": {}}, _Runtime({"mode": "goal", "dialogue_route": "deep_agent"}))

    assert update is not None
    assert isinstance(update["messages"][0], SystemMessage)
    assert update["messages"][1] is user
    content = str(update["messages"][0].content)
    assert '<execution_mode_contract origin="execution_middleware" mode="goal_autopilot"' in content
    assert "Try at least two different strategies" in content
    assert update["runtime"]["execution_mode"] == "goal_autopilot"
