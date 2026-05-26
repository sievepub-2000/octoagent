from __future__ import annotations

import pytest

from src.runtime.config.subagents_config import load_subagents_config_from_dict
from src.agents.subagents import policy


@pytest.fixture(autouse=True)
def reset_subagents_config():
    load_subagents_config_from_dict({})
    yield
    load_subagents_config_from_dict({})


def test_memory_guard_allows_soft_threshold_pressure(monkeypatch: pytest.MonkeyPatch) -> None:
    load_subagents_config_from_dict(
        {
            "enable_system_memory_guard": True,
            "min_available_memory_gb": 8.0,
            "estimated_memory_per_subagent_gb": 2.0,
            "oom_critical_available_memory_gb": 1.0,
        }
    )
    monkeypatch.setattr(policy, "estimate_available_memory_gb", lambda: 5.0)

    assert policy.check_admission([], thread_id=None) is None


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
