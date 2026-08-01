from __future__ import annotations

from src.agents.lead_agent.runtime import (
    FAST_FLASH_MODEL_NAME,
    LeadAgentRuntimeOptions,
    LeadAgentRuntimeResolver,
    resolve_flash_model_name,
)
from src.runtime.config.model_config import ModelConfig
from src.storage.project.service import ProjectExecutionContext


class RuntimeConfigStub:
    def __init__(self, models: list[ModelConfig]) -> None:
        self.models = models

    def get_model_config(self, name: str) -> ModelConfig | None:
        return next((model for model in self.models if model.name == name), None)


def _model(name: str, provider_name: str) -> ModelConfig:
    return ModelConfig(
        name=name,
        model=name,
        provider_name=provider_name,
        interface_type="openai_compatible",
    )


def test_flash_dialogue_keeps_local_default_model() -> None:
    config = RuntimeConfigStub(
        [
            _model("local-qwen", "llamacpp"),
            _model(FAST_FLASH_MODEL_NAME, "openrouter"),
        ]
    )

    resolved = resolve_flash_model_name(
        "local-qwen",
        requested_model_name=None,
        app_config_getter=lambda: config,
    )

    assert resolved == "local-qwen"


def test_compaction_context_window_uses_model_config_not_fixed_default() -> None:
    from src.agents.lead_agent.agent import _resolve_compaction_context_tokens

    selected = ModelConfig(
        name="small-context-model",
        model="small-context-model",
        provider_name="openrouter",
        interface_type="openai_compatible",
        max_context_tokens=13_114,
    )
    larger = ModelConfig(
        name="large-context-model",
        model="large-context-model",
        provider_name="openrouter",
        interface_type="openai_compatible",
        max_context_tokens=262_144,
    )
    config = RuntimeConfigStub([selected, larger])

    assert _resolve_compaction_context_tokens(selected, config) == 13_114


def test_runtime_resolver_defaults_unknown_non_flash_turns_to_tool_action() -> None:
    config = RuntimeConfigStub([_model("local-qwen", "llamacpp")])
    resolver = LeadAgentRuntimeResolver(
        app_config_getter=lambda: config,
        agent_config_loader=lambda _name: None,
    )

    options = resolver.resolve({"configurable": {"model_name": "local-qwen"}})

    assert options.dialogue_route == "tool_action"
    assert options.dialogue_needs_tools is True


def test_runtime_resolver_preserves_explicit_direct_route_without_tools() -> None:
    config = RuntimeConfigStub([_model("local-qwen", "llamacpp")])
    resolver = LeadAgentRuntimeResolver(
        app_config_getter=lambda: config,
        agent_config_loader=lambda _name: None,
    )

    options = resolver.resolve(
        {
            "configurable": {
                "model_name": "local-qwen",
                "dialogue_route": "direct_answer",
            }
        }
    )

    assert options.dialogue_route == "direct_answer"
    assert options.dialogue_needs_tools is False


def test_runtime_resolver_keeps_control_command_lightweight_on_existing_thread() -> None:
    config = RuntimeConfigStub([_model("local-qwen", "llamacpp")])
    resolver = LeadAgentRuntimeResolver(
        app_config_getter=lambda: config,
        agent_config_loader=lambda _name: None,
    )

    options = resolver.resolve(
        {
            "configurable": {
                "model_name": "local-qwen",
                "mode": "flash",
                "dialogue_text": "开启个新对话/new",
                "thread_message_count": 8,
            }
        }
    )

    assert options.dialogue_route == "control_command"
    assert options.dialogue_needs_tools is False


def test_runtime_resolver_plan_only_enables_plan_mode_without_tools() -> None:
    config = RuntimeConfigStub([_model("local-qwen", "llamacpp")])
    resolver = LeadAgentRuntimeResolver(
        app_config_getter=lambda: config,
        agent_config_loader=lambda _name: None,
    )

    options = resolver.resolve(
        {
            "configurable": {
                "model_name": "local-qwen",
                "mode": "flash",
                "dialogue_text": "先给方案，等我确认后再执行",
                "thread_message_count": 4,
            }
        }
    )

    assert options.dialogue_route == "plan_only"
    assert options.dialogue_needs_tools is False
    assert options.is_plan_mode is True


def test_runtime_resolver_keeps_flash_empty_turn_lightweight() -> None:
    config = RuntimeConfigStub([_model("local-qwen", "llamacpp")])
    resolver = LeadAgentRuntimeResolver(
        app_config_getter=lambda: config,
        agent_config_loader=lambda _name: None,
    )

    options = resolver.resolve(
        {
            "configurable": {
                "model_name": "local-qwen",
                "mode": "flash",
            }
        }
    )

    assert options.dialogue_route == "direct_answer"
    assert options.dialogue_needs_tools is False


def test_runtime_resolver_uses_dialogue_text_even_in_flash_mode() -> None:
    config = RuntimeConfigStub([_model("local-qwen", "llamacpp")])
    resolver = LeadAgentRuntimeResolver(
        app_config_getter=lambda: config,
        agent_config_loader=lambda _name: None,
    )

    options = resolver.resolve(
        {
            "configurable": {
                "model_name": "local-qwen",
                "mode": "flash",
                "dialogue_text": "search https://www.anpz.kz and analyze recent company tax and operating data",
            }
        }
    )

    assert options.dialogue_route in {"current_research", "tool_action", "deep_agent"}
    assert options.dialogue_needs_tools is True


def test_runtime_resolver_applies_project_context_and_caps_permission() -> None:
    config = RuntimeConfigStub([_model("project-model", "llamacpp")])

    class ProjectServiceStub:
        @staticmethod
        def resolve_execution_context(project_id: str, **_kwargs) -> ProjectExecutionContext:
            return ProjectExecutionContext(
                project_id=project_id,
                name="OctoAgent",
                root_path="/home/octoagent",
                instructions="Run project checks",
                model_name="project-model",
                permission_mode="directory",
                memory_summary="Known-good baseline",
                pinned_files=["README.md"],
            )

    resolver = LeadAgentRuntimeResolver(
        app_config_getter=lambda: config,
        agent_config_loader=lambda _name: None,
        project_service_getter=lambda: ProjectServiceStub(),
    )

    options = resolver.resolve(
        {
            "configurable": {
                "project_id": "proj-1",
                "permission_mode": "system",
                "dialogue_text": "check the repository",
            }
        }
    )

    assert options.project_id == "proj-1"
    assert options.project_root_path == "/home/octoagent"
    assert options.model_name == "project-model"
    assert options.permission_mode == "directory"
    assert "Run project checks" in options.project_prompt


def test_pro_mode_enables_native_thinking_and_high_effort() -> None:
    model = _model("local-qwen", "llamacpp")
    model.supports_thinking = True
    config = RuntimeConfigStub([model])
    resolver = LeadAgentRuntimeResolver(
        app_config_getter=lambda: config,
        agent_config_loader=lambda _name: None,
    )

    options = resolver.resolve(
        {"configurable": {"model_name": "local-qwen", "mode": "pro"}}
    )

    assert options.thinking_enabled is True
    assert options.reasoning_effort == "high"


def test_resume_always_keeps_tools_attached() -> None:
    config = RuntimeConfigStub([_model("local-qwen", "llamacpp")])
    resolver = LeadAgentRuntimeResolver(
        app_config_getter=lambda: config,
        agent_config_loader=lambda _name: None,
    )

    options = resolver.resolve(
        {
            "configurable": {
                "model_name": "local-qwen",
                "mode": "flash",
                "dialogue_text": "继续",
                "dialogue_route": "direct_answer",
                "continue_trigger": "continue",
            }
        }
    )

    assert options.dialogue_route == "tool_action"
    assert options.dialogue_needs_tools is True


def test_fast_tool_route_keeps_enabled_mcp_tools_attached() -> None:
    from src.agents.lead_agent.builder import LeadAgentBuilder

    calls: list[dict] = []

    def available_tools(**kwargs):
        calls.append(kwargs)
        return []

    builder = LeadAgentBuilder(
        create_agent_fn=lambda **kwargs: kwargs,
        create_chat_model_fn=lambda **_kwargs: object(),
        get_available_tools_fn=available_tools,
        build_middlewares_fn=lambda *_args, **_kwargs: [],
        apply_prompt_template_fn=lambda **_kwargs: "system",
        state_schema=dict,
        setup_agent_tool=object(),
    )
    options = LeadAgentRuntimeOptions(
        thinking_enabled=False,
        reasoning_effort=None,
        requested_model_name=None,
        is_plan_mode=False,
        subagent_enabled=False,
        max_concurrent_subagents=1,
        is_bootstrap=False,
        agent_name=None,
        conversation_language="zh",
        model_name="local-model",
        agent_tool_groups=None,
        ml_intern_profile="default",
        ml_intern_defaults={},
        permission_mode="system",
        dialogue_route="tool_action",
        dialogue_route_reason="test",
        dialogue_needs_tools=True,
        dialogue_needs_memory=True,
        dialogue_text="检查系统工具",
        project_id=None,
        project_root_path=None,
        project_prompt="",
    )

    builder.build({}, options)

    assert calls[0]["include_mcp"] is True
