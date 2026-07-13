"""Regression tests for the progress-stall circuit breaker."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agents.middlewares import progress_stall_middleware as mod
from src.agents.middlewares.progress_stall_middleware import ProgressStallMiddleware


def test_progress_stall_hooks_do_not_declare_end_jump() -> None:
    assert getattr(ProgressStallMiddleware.before_model, "__can_jump_to__", None) is None
    assert getattr(ProgressStallMiddleware.abefore_model, "__can_jump_to__", None) is None


def test_progress_stall_hard_ends_a_runaway_identical_tool_loop() -> None:
    messages = [HumanMessage(content="run it")]
    for index in range(mod._HARD_END_DUP):
        call_id = f"call-{index}"
        messages.extend(
            [
                AIMessage(content="", tool_calls=[{"name": "bash", "args": {"command": "false"}, "id": call_id}]),
                ToolMessage(content="failed", name="bash", tool_call_id=call_id, status="error"),
            ]
        )

    update = ProgressStallMiddleware().before_model({"messages": messages, "runtime": {}}, None)

    assert update is not None
    assert update["jump_to"] == "END"
    assert update["runtime"]["progress_stall"]["hard_stop"] is True
