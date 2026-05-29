from __future__ import annotations

import pytest

from src.agents.subagents import policy
from src.agents.subagents.contracts import SubagentResult, SubagentStatus
from src.runtime.config.subagents_config import load_subagents_config_from_dict


@pytest.fixture(autouse=True)
def reset_subagents_config():
    load_subagents_config_from_dict({})
    yield
    load_subagents_config_from_dict({})


def _active(task_id: str, *, thread_id: str | None = None) -> SubagentResult:
    return SubagentResult(task_id=task_id, trace_id=f"trace-{task_id}", status=SubagentStatus.RUNNING, thread_id=thread_id)


def test_memory_guard_applies_soft_threshold_pressure(monkeypatch: pytest.MonkeyPatch) -> None:
    load_subagents_config_from_dict(
        {
            "enable_system_memory_guard": True,
            "min_available_memory_gb": 8.0,
            "estimated_memory_per_subagent_gb": 2.0,
            "oom_critical_available_memory_gb": 1.0,
        }
    )
    monkeypatch.setattr(policy, "estimate_available_memory_gb", lambda: 5.0)

    limit, reason, available = policy.resolve_memory_aware_subagent_limit(configured_limit=3)

    assert limit == 1
    assert reason == "soft_limit"
    assert available == 5.0
    assert policy.check_admission([_active("one")], thread_id=None) is not None


def test_memory_guard_blocks_only_below_oom_critical(monkeypatch: pytest.MonkeyPatch) -> None:
    load_subagents_config_from_dict(
        {
            "enable_system_memory_guard": True,
            "min_available_memory_gb": 8.0,
            "estimated_memory_per_subagent_gb": 2.0,
            "oom_critical_available_memory_gb": 1.0,
        }
    )
    monkeypatch.setattr(policy, "estimate_available_memory_gb", lambda: 0.5)

    rejection = policy.check_admission([], thread_id=None)

    assert rejection is not None
    assert "oom_critical<1.0 GiB" in rejection


def test_memory_guard_keeps_configured_limit_when_budget_allows(monkeypatch: pytest.MonkeyPatch) -> None:
    load_subagents_config_from_dict(
        {
            "enable_system_memory_guard": True,
            "min_available_memory_gb": 8.0,
            "estimated_memory_per_subagent_gb": 2.0,
            "oom_critical_available_memory_gb": 1.0,
        }
    )
    monkeypatch.setattr(policy, "estimate_available_memory_gb", lambda: 16.0)

    limit, reason, available = policy.resolve_memory_aware_subagent_limit(configured_limit=3)

    assert limit == 3
    assert reason == "ok"
    assert available == 16.0
