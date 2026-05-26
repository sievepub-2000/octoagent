from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from src.agents.middlewares import subagent_limit_middleware as limit_module
from src.agents.middlewares.subagent_limit_middleware import SubagentLimitMiddleware


@pytest.fixture(autouse=True)
def reset_memory_guard(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(limit_module, "is_host_memory_oom_critical", lambda: False)


def _task_call(index: int) -> dict:
    return {
        "name": "task",
        "args": {"task": f"branch {index}"},
        "id": f"call-{index}",
        "type": "tool_call",
    }


def test_healthy_host_does_not_rewrite_parallel_task_tool_calls() -> None:
    middleware = SubagentLimitMiddleware(max_concurrent=2)
    message = AIMessage(content="", tool_calls=[_task_call(1), _task_call(2), _task_call(3)])

    update = middleware.after_model({"messages": [message]}, None)

    assert update is None
    assert len(message.tool_calls) == 3


def test_oom_critical_host_trims_excess_task_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limit_module, "is_host_memory_oom_critical", lambda: True)
    middleware = SubagentLimitMiddleware(max_concurrent=2)
    message = AIMessage(content="", tool_calls=[_task_call(1), _task_call(2), _task_call(3)])

    update = middleware.after_model({"messages": [message]}, None)

    assert update is not None
    next_message = update["messages"][0]
    assert len(next_message.tool_calls) == 2
