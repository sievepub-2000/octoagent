from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypedDict

from pydantic import ConfigDict

from langchain_core.runnables import RunnableConfig

from src.models import is_embedded_backup_model_name

from ..dialogue_routing import FAST_ROUTES
from .runtime import LeadAgentRuntimeOptions

logger = logging.getLogger(__name__)

# The API accepts a deliberately open per-run context (mode, sandbox_id,
# routing hints, continuation data, and plugin-specific keys).  An empty
# TypedDict with ``extra='allow'`` gives LangGraph a real object schema while
# preserving the existing dict-shaped, extensible runtime context.
class LeadAgentContext(TypedDict, total=False):
    pass


LeadAgentContext.__pydantic_config__ = ConfigDict(extra="allow")


class LeadAgentBuilder:
    def __init__(
        self,
        *,
        create_agent_fn: Callable[..., object],
        create_chat_model_fn: Callable[..., object],
        get_available_tools_fn: Callable[..., list[object]],
        build_middlewares_fn: Callable[..., list[object]],
        apply_prompt_template_fn: Callable[..., str],
        state_schema,
        setup_agent_tool,
        embedded_backup_prompt_fn: Callable[[str | None], str],
    ):
        self._create_agent_fn = create_agent_fn
        self._create_chat_model_fn = create_chat_model_fn
        self._get_available_tools_fn = get_available_tools_fn
        self._build_middlewares_fn = build_middlewares_fn
        self._apply_prompt_template_fn = apply_prompt_template_fn
        self._state_schema = state_schema
        self._setup_agent_tool = setup_agent_tool
        self._embedded_backup_prompt_fn = embedded_backup_prompt_fn

    def build(self, config: RunnableConfig, options: LeadAgentRuntimeOptions):
        project_prompt = f"\n{options.project_prompt}" if options.project_prompt else ""
        logger.info(
            "Create Agent(%s) -> thinking_enabled: %s, reasoning_effort: %s, model_name: %s, is_plan_mode: %s, subagent_enabled: %s, max_concurrent_subagents: %s",
            options.agent_name or "default",
            options.thinking_enabled,
            options.reasoning_effort,
            options.model_name,
            options.is_plan_mode,
            options.subagent_enabled,
            options.max_concurrent_subagents,
        )

        if is_embedded_backup_model_name(options.model_name):
            return self._create_agent_fn(
                model=self._create_chat_model_fn(
                    name=options.model_name,
                    thinking_enabled=False,
                ),
                tools=[],
                middleware=self._build_middlewares_fn(
                    config,
                    model_name=options.model_name,
                    agent_name=options.agent_name,
                    dialogue_route=options.dialogue_route,
                ),
                system_prompt=self._embedded_backup_prompt_fn(options.conversation_language) + project_prompt,
                state_schema=self._state_schema,
                context_schema=LeadAgentContext,
            )

        if options.is_bootstrap:
            return self._create_agent_fn(
                model=self._create_chat_model_fn(
                    name=options.model_name,
                    thinking_enabled=options.thinking_enabled,
                ),
                tools=self._get_available_tools_fn(
                    model_name=options.model_name,
                    permission_mode=options.permission_mode,
                    subagent_enabled=options.subagent_enabled,
                )
                + [self._setup_agent_tool],
                middleware=self._build_middlewares_fn(
                    config,
                    model_name=options.model_name,
                    dialogue_route=options.dialogue_route,
                ),
                system_prompt=self._apply_prompt_template_fn(
                    subagent_enabled=options.subagent_enabled,
                    max_concurrent_subagents=options.max_concurrent_subagents,
                    available_skills={"bootstrap"},
                    conversation_language=options.conversation_language,
                    ml_intern_profile=options.ml_intern_profile,
                )
                + project_prompt,
                state_schema=self._state_schema,
                context_schema=LeadAgentContext,
            )

        lightweight_dialogue_mode = not options.thinking_enabled and not options.is_plan_mode and not options.subagent_enabled and options.dialogue_route in FAST_ROUTES
        compact_tool_mode = not options.thinking_enabled and not options.is_plan_mode and not options.subagent_enabled and options.dialogue_needs_tools

        tools = []
        if options.dialogue_needs_tools:
            tools = self._get_available_tools_fn(
                model_name=options.model_name,
                groups=options.agent_tool_groups,
                include_mcp=not compact_tool_mode,
                permission_mode=options.permission_mode,
                subagent_enabled=options.subagent_enabled,
            )
            from src.agents.core.tool_loader import load_tools_for_intent
            from src.tools.permissions import dedupe_tools_by_name

            tools = dedupe_tools_by_name(
                tools
                + load_tools_for_intent(
                    options.dialogue_text,
                    permission_mode=options.permission_mode,
                )
            )

        return self._create_agent_fn(
            model=self._create_chat_model_fn(
                name=options.model_name,
                thinking_enabled=options.thinking_enabled,
                reasoning_effort=options.reasoning_effort,
            ),
            tools=tools,
            middleware=self._build_middlewares_fn(
                config,
                model_name=options.model_name,
                agent_name=options.agent_name,
                dialogue_route=options.dialogue_route,
            ),
            system_prompt=self._apply_prompt_template_fn(
                subagent_enabled=options.subagent_enabled,
                max_concurrent_subagents=options.max_concurrent_subagents,
                agent_name=options.agent_name,
                conversation_language=options.conversation_language,
                ml_intern_profile=options.ml_intern_profile,
                compact_prompt=lightweight_dialogue_mode or compact_tool_mode,
                dialogue_route=options.dialogue_route,
            )
            + project_prompt,
            state_schema=self._state_schema,
            context_schema=LeadAgentContext,
        )
