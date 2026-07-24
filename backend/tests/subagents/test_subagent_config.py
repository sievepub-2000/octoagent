from __future__ import annotations

from src.agents.subagents.catalog import get_subagent_config, get_subagent_names
from src.agents.subagents.config import SubagentConfig
from src.agents.subagents.policy import resolve_subagent_config
from src.runtime.config.subagents_config import load_subagents_config_from_dict


def test_resolve_subagent_config_honors_small_max_turns() -> None:
    base_config = SubagentConfig(
        name="unit-test-agent",
        description="test",
        system_prompt="test",
        max_turns=50,
        timeout_seconds=900,
    )

    resolved, budget = resolve_subagent_config(base_config, max_turns=5, model_name="parent-model")

    assert resolved.max_turns == 5
    assert budget.max_turns == 5
    assert budget.timeout_seconds == 900
    assert budget.model == "parent-model"


def test_resolve_subagent_config_does_not_clamp_large_max_turns() -> None:
    base_config = SubagentConfig(
        name="unit-test-agent",
        description="test",
        system_prompt="test",
        max_turns=50,
        timeout_seconds=900,
    )

    resolved, budget = resolve_subagent_config(base_config, max_turns=750, model_name="parent-model")

    assert resolved.max_turns == 750
    assert budget.max_turns == 750
    assert budget.timeout_seconds == 7500


def test_resolve_subagent_config_uses_host_long_task_default_when_unset() -> None:
    base_config = SubagentConfig(
        name="unit-test-agent",
        description="test",
        system_prompt="test",
        max_turns=None,
        timeout_seconds=900,
    )

    resolved, budget = resolve_subagent_config(base_config, model_name="parent-model")

    assert resolved.max_turns is not None
    assert resolved.max_turns >= 200
    assert budget.max_turns == resolved.max_turns
    assert budget.timeout_seconds >= 900


def test_subagent_config_overrides_runtime_fields() -> None:
    try:
        load_subagents_config_from_dict(
            {
                "timeout_seconds": 900,
                "agents": {
                    "general_purpose": {
                        "model": "custom-model",
                        "max_turns": 7,
                        "timeout_seconds": 123,
                        "tools": ["read_file"],
                        "disallowed_tools": ["task", "delete_file"],
                    }
                },
            }
        )

        config = get_subagent_config("general-purpose")

        assert config is not None
        assert config.model == "custom-model"
        assert config.max_turns == 7
        assert config.timeout_seconds == 123
        assert config.tools == ["read_file"]
        assert config.disallowed_tools == ["task", "delete_file"]
        # A fallback is derived only when the application has at least one
        # configured model; the clean example config intentionally has none.
        assert config.fallback_models is None or len(config.fallback_models) == 1
    finally:
        load_subagents_config_from_dict({})


def test_subagent_catalog_only_contains_minimal_builtin_roles() -> None:
    names = get_subagent_names()

    assert names == ["bash", "general-purpose"]


def test_removed_agency_role_is_not_implicitly_injected() -> None:
    assert get_subagent_config("agency-ui-designer") is None
