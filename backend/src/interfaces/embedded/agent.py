"""Agent assembly helpers for the embedded OctoAgent client."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)


class ClientAgentBuilder:
    """Build embedded agents from injected runtime dependencies."""

    def __init__(
        self,
        *,
        create_chat_model_fn,
        get_tools_fn,
        build_middlewares_fn,
        apply_prompt_template_fn,
        create_agent_fn,
        get_checkpointer_fn,
        thread_state_cls=ThreadState,
    ):
        self._create_chat_model = create_chat_model_fn
        self._get_tools = get_tools_fn
        self._build_middlewares = build_middlewares_fn
        self._apply_prompt_template = apply_prompt_template_fn
        self._create_agent = create_agent_fn
        self._get_checkpointer = get_checkpointer_fn
        self._thread_state_cls = thread_state_cls

    def build(self, config: RunnableConfig, *, checkpointer=None):
        cfg = config.get("configurable", {})
        thinking_enabled = cfg.get("thinking_enabled", False)
        model_name = cfg.get("model_name")
        subagent_enabled = cfg.get("subagent_enabled", False)
        max_concurrent_subagents = cfg.get("max_concurrent_subagents", 3)

        kwargs: dict[str, Any] = {
            "model": self._create_chat_model(name=model_name, thinking_enabled=thinking_enabled),
            "tools": self._get_tools(model_name=model_name, subagent_enabled=subagent_enabled),
            "middleware": self._build_middlewares(config, model_name=model_name),
            "system_prompt": self._apply_prompt_template(
                subagent_enabled=subagent_enabled,
                max_concurrent_subagents=max_concurrent_subagents,
            ),
            "state_schema": self._thread_state_cls,
        }
        resolved_checkpointer = checkpointer if checkpointer is not None else self._get_checkpointer()
        if resolved_checkpointer is not None:
            kwargs["checkpointer"] = resolved_checkpointer

        agent = self._create_agent(**kwargs)
        logger.info("Agent created: model=%s, thinking=%s", model_name, thinking_enabled)
        return agent
