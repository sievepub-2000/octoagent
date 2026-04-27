from __future__ import annotations

import logging
import os

from langchain.tools import BaseTool

from src.config import get_app_config
from src.reflection import resolve_variable
from src.tools.builtins import (
    BYTEBOT_COMPAT_TOOLS,
    OPENHARNESS_COMPAT_TOOLS,
    ask_clarification_tool,
    codex_cli_tool,
    convert_document_tool,
    present_file_tool,
    process_image_tool,
    read_webpage_tool,
    task_tool,
    view_image_tool,
)

logger = logging.getLogger(__name__)


def _bytebot_compat_enabled() -> bool:
    """Return True when BYTEBOT_COMPAT_ENABLED env flag is truthy.

    Default is disabled to keep the default sandbox profile unchanged; the
    adapter is observation-only (returns ``not_implemented`` JSON payloads) so
    enabling it is safe, but we still opt-in explicitly per the
    self-optimization policy (observe/suggest/shadow only).
    """
    value = os.environ.get("BYTEBOT_COMPAT_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


BUILTIN_TOOLS: list[BaseTool] = [
    present_file_tool,
    ask_clarification_tool,
    codex_cli_tool,
    process_image_tool,
    read_webpage_tool,
    convert_document_tool,
] + OPENHARNESS_COMPAT_TOOLS

SUBAGENT_TOOLS: list[BaseTool] = [task_tool]


class ToolCatalog:
    def __init__(self, *, app_config_getter=get_app_config, resolver=resolve_variable):
        self._app_config_getter = app_config_getter
        self._resolver = resolver

    def load_configured_tools(self, groups: list[str] | None = None) -> list[BaseTool]:
        config = self._app_config_getter()
        return [
            self._resolver(tool.use, BaseTool)
            for tool in config.tools
            if groups is None or tool.group in groups
        ]

    def load_builtin_tools(
        self,
        *,
        model_name: str | None = None,
        subagent_enabled: bool = False,
    ) -> list[BaseTool]:
        config = self._app_config_getter()
        resolved_model_name = model_name
        builtin_tools = BUILTIN_TOOLS.copy()

        if subagent_enabled:
            builtin_tools.extend(SUBAGENT_TOOLS)
            logger.info("Including subagent tools (task)")

        if _bytebot_compat_enabled():
            builtin_tools.extend(BYTEBOT_COMPAT_TOOLS)
            logger.info(
                "Including bytebot_compat tools (observation-only, %d entries)",
                len(BYTEBOT_COMPAT_TOOLS),
            )

        if resolved_model_name is None and config.models:
            resolved_model_name = config.models[0].name

        model_config = (
            config.get_model_config(resolved_model_name)
            if resolved_model_name
            else None
        )
        if model_config is not None and model_config.supports_vision:
            builtin_tools.append(view_image_tool)
            logger.info(
                "Including view_image_tool for model '%s' (supports_vision=True)",
                resolved_model_name,
            )

        return builtin_tools
