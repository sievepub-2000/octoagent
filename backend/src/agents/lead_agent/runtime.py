from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.config.agents_config import load_agent_config
from src.config.app_config import get_app_config
from src.config.paths import resolve_configured_default_model_name
from src.models import is_embedded_backup_model_name
from src.ml_intern_defaults import build_ml_intern_runtime_context, resolve_ml_intern_profile_name

logger = logging.getLogger(__name__)


def _runtime_config_layers(config: RunnableConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return configurable and metadata runtime layers as plain dicts."""
    configurable = config.get("configurable", {})
    metadata = config.get("metadata", {})
    configurable_dict = dict(configurable) if isinstance(configurable, dict) else {}
    metadata_dict = dict(metadata) if isinstance(metadata, dict) else {}
    return configurable_dict, metadata_dict


def runtime_config_value(
    config: RunnableConfig,
    key: str,
    default: Any = None,
) -> Any:
    """Read a runtime option from configurable first, then metadata."""
    configurable, metadata = _runtime_config_layers(config)
    for layer in (configurable, metadata):
        value = layer.get(key)
        if value is not None:
            return value
    return default


@dataclass(slots=True)
class LeadAgentRuntimeOptions:
    thinking_enabled: bool
    reasoning_effort: str | None
    requested_model_name: str | None
    is_plan_mode: bool
    subagent_enabled: bool
    max_concurrent_subagents: int
    is_bootstrap: bool
    agent_name: str | None
    conversation_language: str | None
    model_name: str
    agent_tool_groups: list[str] | None
    ml_intern_profile: str
    ml_intern_defaults: dict[str, Any]


def embedded_backup_system_prompt(conversation_language: str | None = None) -> str:
    language_hint = (
        f"Reply in {conversation_language}."
        if conversation_language
        else "Reply in the user's language."
    )
    return (
        "You are OctoAgent's embedded emergency fallback assistant. "
        "A primary model is not configured or is unavailable, so you must keep helping with a compact, plain-text response. "
        f"{language_hint} "
        "Do not call tools. Do not claim that you completed actions you could not actually perform. "
        "If the request depends on unavailable tools or remote models, say so briefly and provide the most useful next step."
    )


def resolve_model_name(
    requested_model_name: str | None = None,
    *,
    app_config_getter=get_app_config,
) -> str:
    app_config = app_config_getter()
    default_model_name = resolve_configured_default_model_name(
        model.name for model in app_config.models
    )
    if default_model_name is None:
        logger.warning(
            "No configured chat model found; embedded bootstrap model will be used as emergency default."
        )
        return "__embedded_bootstrap__"

    if requested_model_name and app_config.get_model_config(requested_model_name):
        return requested_model_name

    if requested_model_name and requested_model_name != default_model_name:
        logger.warning(
            "Model '%s' not found in config; fallback to default model '%s'.",
            requested_model_name,
            default_model_name,
        )
    return default_model_name


class LeadAgentRuntimeResolver:
    def __init__(self, *, app_config_getter=get_app_config, agent_config_loader=load_agent_config):
        self._app_config_getter = app_config_getter
        self._agent_config_loader = agent_config_loader

    def resolve(self, config: RunnableConfig) -> LeadAgentRuntimeOptions:
        thinking_enabled = runtime_config_value(config, "thinking_enabled", True)
        reasoning_effort = runtime_config_value(config, "reasoning_effort")
        requested_model_name: str | None = runtime_config_value(
            config,
            "model_name",
        ) or runtime_config_value(config, "model")
        is_plan_mode = runtime_config_value(config, "is_plan_mode", False)
        subagent_enabled = runtime_config_value(config, "subagent_enabled", False)
        max_concurrent_subagents = runtime_config_value(
            config,
            "max_concurrent_subagents",
            3,
        )
        is_bootstrap = runtime_config_value(config, "is_bootstrap", False)
        agent_name = runtime_config_value(config, "agent_name")
        conversation_language = runtime_config_value(config, "conversation_language")
        permission_mode = runtime_config_value(config, "permission_mode")
        workflow_run_mode = runtime_config_value(config, "workflow_run_mode")
        ml_intern_profile = resolve_ml_intern_profile_name(
            runtime_config_value(config, "ml_intern_profile"),
            permission_mode=permission_mode,
            workflow_run_mode=workflow_run_mode,
            context={"yolo_mode": runtime_config_value(config, "yolo_mode")},
        )
        ml_intern_context = build_ml_intern_runtime_context(ml_intern_profile)

        agent_config = self._agent_config_loader(agent_name) if not is_bootstrap else None
        agent_model_name = (
            agent_config.model
            if agent_config and agent_config.model
            else resolve_model_name(app_config_getter=self._app_config_getter)
        )
        model_name = requested_model_name or agent_model_name
        app_config = self._app_config_getter()
        model_config = app_config.get_model_config(model_name) if model_name else None

        if model_config is None and not is_embedded_backup_model_name(model_name):
            raise ValueError(
                "No chat model could be resolved. Please configure at least one model in config.yaml "
                "or provide a valid 'model_name'/'model' in the request."
            )
        if model_config is not None and thinking_enabled and not model_config.supports_thinking:
            logger.warning(
                "Thinking mode is enabled but model '%s' does not support it; fallback to non-thinking mode.",
                model_name,
            )
            thinking_enabled = False

        return LeadAgentRuntimeOptions(
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
            requested_model_name=requested_model_name,
            is_plan_mode=is_plan_mode,
            subagent_enabled=subagent_enabled,
            max_concurrent_subagents=max_concurrent_subagents,
            is_bootstrap=is_bootstrap,
            agent_name=agent_name,
            conversation_language=conversation_language,
            model_name=model_name,
            agent_tool_groups=agent_config.tool_groups if agent_config else None,
            ml_intern_profile=ml_intern_profile,
            ml_intern_defaults=ml_intern_context["ml_intern_defaults"],
        )

    @staticmethod
    def inject_metadata(config: RunnableConfig, options: LeadAgentRuntimeOptions) -> None:
        metadata = config.setdefault("metadata", {})
        metadata.update(
            {
                "agent_name": options.agent_name or "default",
                "conversation_language": options.conversation_language,
                "is_bootstrap": options.is_bootstrap,
                "model_name": options.model_name or "default",
                "max_concurrent_subagents": options.max_concurrent_subagents,
                "thinking_enabled": options.thinking_enabled,
                "reasoning_effort": options.reasoning_effort,
                "is_plan_mode": options.is_plan_mode,
                "subagent_enabled": options.subagent_enabled,
                "ml_intern_profile": options.ml_intern_profile,
                "ml_intern_defaults": options.ml_intern_defaults,
            }
        )
