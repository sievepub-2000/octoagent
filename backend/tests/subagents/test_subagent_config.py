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
        assert config.fallback_models is not None
        assert len(config.fallback_models) == 1
    finally:
        load_subagents_config_from_dict({})


def test_subagent_names_include_dynamic_catalog_entries() -> None:
    names = get_subagent_names()

    assert "general-purpose" in names
    assert "bash" in names
    assert names == sorted(names)


def test_agency_subagents_resolve_to_system_models_with_default_fallback() -> None:
    config = get_subagent_config("agency-ui-designer")
    builtin_config = get_subagent_config("general-purpose")

    assert config is not None
    assert builtin_config is not None
    assert config.model != "inherit"
    assert config.model != "auto"
    assert config.fallback_models == builtin_config.fallback_models
    assert config.fallback_models is not None
    assert len(config.fallback_models) == 1
