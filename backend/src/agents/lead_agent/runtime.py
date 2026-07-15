from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.dialogue_routing import FAST_ROUTES, ROUTE_CONTROL_COMMAND, ROUTE_PLAN_ONLY, classify_dialogue_route
from src.models import is_embedded_backup_model_name
from src.runtime.config.agents_config import load_agent_config
from src.runtime.config.app_config import get_app_config
from src.runtime.config.ml_intern_defaults import build_ml_intern_runtime_context, resolve_ml_intern_profile_name
from src.runtime.config.paths import resolve_configured_default_model_name
from src.storage.project.service import get_project_service
from src.tools.permissions import normalize_runtime_permission_mode

logger = logging.getLogger(__name__)

FAST_FLASH_MODEL_NAME = "openrouter-free-openai-gpt-oss-20b"
SLOW_FLASH_MODEL_NAMES = {
    "nemotron-3-super-free",
    "gpt-oss-120b-free",
    "qwen3-next-free",
}


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
    permission_mode: str
    dialogue_route: str
    dialogue_route_reason: str
    dialogue_needs_tools: bool
    dialogue_needs_memory: bool
    dialogue_text: str
    project_id: str | None
    project_root_path: str | None
    project_prompt: str


def embedded_backup_system_prompt(conversation_language: str | None = None) -> str:
    language_hint = f"Reply in {conversation_language}." if conversation_language else "Reply in the user's language."
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
    default_model_name = resolve_configured_default_model_name(model.name for model in app_config.models)
    if default_model_name is None:
        logger.warning("No configured chat model found; embedded bootstrap model will be used as emergency default.")
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


def resolve_flash_model_name(
    model_name: str,
    *,
    requested_model_name: str | None,
    app_config_getter=get_app_config,
) -> str:
    """Keep lightweight dialogue off slow/free large models.

    The WebUI can persist a model override in browser storage. In flash mode
    that override must not turn a one-sentence question into a 25-30s run.
    """

    app_config = app_config_getter()
    current_model = app_config.get_model_config(model_name)
    current_provider = (current_model.provider_name or "").lower() if current_model is not None else ""
    if current_provider in {"llamacpp", "llama.cpp", "ollama", "local"}:
        return model_name

    fast_model = app_config.get_model_config(FAST_FLASH_MODEL_NAME)
    if fast_model is None:
        return model_name

    requested = (requested_model_name or "").strip()
    if not requested or requested in SLOW_FLASH_MODEL_NAMES:
        if model_name != FAST_FLASH_MODEL_NAME:
            logger.info(
                "Flash dialogue using fast model '%s' instead of '%s'.",
                FAST_FLASH_MODEL_NAME,
                model_name,
            )
        return FAST_FLASH_MODEL_NAME
    return model_name


class LeadAgentRuntimeResolver:
    def __init__(
        self,
        *,
        app_config_getter=get_app_config,
        agent_config_loader=load_agent_config,
        project_service_getter=get_project_service,
    ):
        self._app_config_getter = app_config_getter
        self._agent_config_loader = agent_config_loader
        self._project_service_getter = project_service_getter

    def resolve(self, config: RunnableConfig) -> LeadAgentRuntimeOptions:
        thinking_enabled = runtime_config_value(config, "thinking_enabled", False)
        reasoning_effort = runtime_config_value(config, "reasoning_effort")
        requested_model_name: str | None = runtime_config_value(
            config,
            "model_name",
        ) or runtime_config_value(config, "model")
        project_id = str(runtime_config_value(config, "project_id") or "").strip() or None
        project_root_path: str | None = None
        project_prompt = ""
        requested_permission = runtime_config_value(config, "permission_mode")
        if project_id:
            project_context = self._project_service_getter().resolve_execution_context(
                project_id,
                requested_model=requested_model_name,
                requested_permission=requested_permission,
            )
            requested_model_name = project_context.model_name or None
            requested_permission = project_context.permission_mode
            project_root_path = project_context.root_path
            project_prompt = project_context.prompt_section()
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
        permission_mode = normalize_runtime_permission_mode(requested_permission)
        workflow_run_mode = runtime_config_value(config, "workflow_run_mode")
        runtime_mode = runtime_config_value(config, "mode")
        dialogue_route_payload = runtime_config_value(config, "dialogue_route")
        explicit_dialogue_route = None
        if isinstance(dialogue_route_payload, dict):
            explicit_dialogue_route = dialogue_route_payload.get("kind")
        elif isinstance(dialogue_route_payload, str):
            explicit_dialogue_route = dialogue_route_payload
        dialogue_text = runtime_config_value(config, "dialogue_text") or runtime_config_value(config, "last_user_message") or ""
        route = classify_dialogue_route(
            str(dialogue_text),
            mode=runtime_mode,
            explicit_route=explicit_dialogue_route,
        )
        # LangGraph SDK and automation clients often build the agent before the
        # user message is available to this resolver. OctoAgent is positioned as
        # an execution-first OA assistant, so unknown non-flash turns must keep
        # the tool node attached unless the client explicitly selected a cheap
        # direct-answer route.
        if not explicit_dialogue_route and not str(dialogue_text).strip() and runtime_mode != "flash":
            route = classify_dialogue_route(
                "",
                mode=runtime_mode,
                explicit_route="tool_action",
            )
        # Historical thread continuation guard: if the client signals a continuation
        # (manual or auto) or there is pending in-flight work (todos / task_state),
        # never downgrade to FAST_ROUTES — otherwise the agent loses its tools and
        # can only "think" and reply with text instead of executing follow-up actions.
        continue_trigger = runtime_config_value(config, "continue_trigger")
        system_continue_reason = runtime_config_value(config, "system_continue_reason")
        continue_message_count = runtime_config_value(config, "continue_message_count")
        thread_message_count = runtime_config_value(config, "thread_message_count")
        if (
            route.kind in FAST_ROUTES
            and route.kind not in {ROUTE_CONTROL_COMMAND, ROUTE_PLAN_ONLY}
            and (
                continue_trigger == "continue"
                or bool(system_continue_reason)
                or (isinstance(continue_message_count, (int, float)) and int(continue_message_count) >= 1)
                or (isinstance(thread_message_count, (int, float)) and int(thread_message_count) >= 2)
            )
        ):
            route = classify_dialogue_route(
                "",
                mode=runtime_mode,
                explicit_route="tool_action",
            )
            logger.info(
                "Dialogue route upgraded to tool_action: continue_trigger=%s system_continue_reason=%s continue_message_count=%s",
                continue_trigger,
                system_continue_reason,
                continue_message_count,
            )
        if route.kind == ROUTE_PLAN_ONLY:
            is_plan_mode = True
            subagent_enabled = False
        ml_intern_profile = resolve_ml_intern_profile_name(
            runtime_config_value(config, "ml_intern_profile"),
            permission_mode=permission_mode,
            workflow_run_mode=workflow_run_mode,
            context={"yolo_mode": runtime_config_value(config, "yolo_mode")},
        )
        ml_intern_context = build_ml_intern_runtime_context(ml_intern_profile)

        agent_config = self._agent_config_loader(agent_name) if not is_bootstrap else None
        agent_model_name = agent_config.model if agent_config and agent_config.model else resolve_model_name(app_config_getter=self._app_config_getter)
        model_name = requested_model_name or agent_model_name
        if runtime_mode == "flash" and not thinking_enabled and not is_plan_mode and not subagent_enabled and route.kind in FAST_ROUTES:
            model_name = resolve_flash_model_name(
                model_name,
                requested_model_name=requested_model_name,
                app_config_getter=self._app_config_getter,
            )
        app_config = self._app_config_getter()
        model_config = app_config.get_model_config(model_name) if model_name else None

        if model_config is None and not is_embedded_backup_model_name(model_name):
            raise ValueError("No chat model could be resolved. Please configure at least one model in config.yaml or provide a valid 'model_name'/'model' in the request.")
        if model_config is not None and thinking_enabled and not model_config.supports_thinking:
            logger.warning(
                "Thinking mode is enabled but model '%s' does not support it; fallback to non-thinking mode.",
                model_name,
            )
            thinking_enabled = False

        if explicit_dialogue_route and explicit_dialogue_route != route.kind:
            logger.info(
                "Route drift: ts=%s py=%s reason=%s thread_msgs=%s",
                explicit_dialogue_route,
                route.kind,
                route.reason,
                thread_message_count,
            )
        logger.info(
            "Routing decision: route=%s reason=%s mode=%s thinking=%s plan=%s subagent=%s continue_trigger=%s thread_msgs=%s",
            route.kind,
            route.reason,
            runtime_mode,
            thinking_enabled,
            is_plan_mode,
            subagent_enabled,
            continue_trigger,
            thread_message_count,
        )
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
            permission_mode=permission_mode,
            dialogue_route=route.kind,
            dialogue_route_reason=route.reason,
            dialogue_needs_tools=route.needs_tools,
            dialogue_needs_memory=route.needs_memory,
            dialogue_text=str(dialogue_text),
            project_id=project_id,
            project_root_path=project_root_path,
            project_prompt=project_prompt,
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
                "permission_mode": options.permission_mode,
                "dialogue_route": options.dialogue_route,
                "dialogue_route_reason": options.dialogue_route_reason,
                "dialogue_needs_tools": options.dialogue_needs_tools,
                "dialogue_needs_memory": options.dialogue_needs_memory,
                "project_id": options.project_id,
                "project_root_path": options.project_root_path,
            }
        )
