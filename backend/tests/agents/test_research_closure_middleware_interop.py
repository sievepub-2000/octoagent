from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agents.middlewares.goal_drift_middleware import GoalDriftMiddleware
from src.agents.middlewares.step_reflection_middleware import StepReflectionMiddleware


def test_step_reflection_suppressed_after_research_closure() -> None:
    middleware = StepReflectionMiddleware(every_n=1)
    messages = [
        HumanMessage(content="research content subscription"),
        AIMessage(content="", tool_calls=[{"name": "web_fetch", "args": {"url": "https://example.com"}, "id": "call-1"}]),
        ToolMessage(content="useful evidence" * 30, name="web_fetch", tool_call_id="call-1"),
    ]

    update = middleware.before_model(
        {"messages": messages, "runtime": {"research_closure": {"status": "must_finalize"}}},
        None,
    )

    assert update is None


def test_goal_drift_suppressed_after_research_closure() -> None:
    middleware = GoalDriftMiddleware(every_n=1)
    messages = [HumanMessage(content="research content subscription")]

    update = middleware.after_model(
        {"messages": messages, "runtime": {"research_closure": {"status": "must_finalize"}}},
        None,
    )

    assert update is None


def test_goal_drift_prefers_active_task_state_goal_over_stale_goal_contract(monkeypatch) -> None:
    class _Embeddings:
        def embed_one(self, text: str) -> list[float]:
            if "ANPZ" in text:
                return [1.0, 0.0]
            return [0.0, 1.0]

    monkeypatch.setattr("src.agents.middlewares.goal_drift_middleware.get_embedding_service", lambda: _Embeddings())
    middleware = GoalDriftMiddleware(every_n=1, drift_threshold=0.9, window=1)
    messages = [
        HumanMessage(content="say what you can do"),
        SystemMessage(content="<goal_contract>\n  summary: say what you can do\n</goal_contract>"),
        HumanMessage(content="Research ANPZ tax debt operations revenue profit exports."),
        SystemMessage(content="[OctoAgent persistent task state]\nGoal: Research ANPZ tax debt operations revenue profit exports.\nStatus: active"),
        AIMessage(content="I summarized newsletter platforms and creator memberships."),
    ]

    update = middleware.after_model({"messages": messages}, None)

    assert update is not None
    alert = update["messages"][0].content
    assert "ANPZ" in alert
    assert "say what you can do" not in alert
