"""Catalog and config resolution for builtin subagents."""

from __future__ import annotations

import logging
from dataclasses import replace

from src.config.subagents_config import get_subagents_app_config

from .builtins import BUILTIN_SUBAGENTS
from .config import SubagentConfig

logger = logging.getLogger(__name__)


def get_subagent_config(name: str) -> SubagentConfig | None:
    """Get a resolved subagent config by name with global overrides applied."""
    config = BUILTIN_SUBAGENTS.get(name)
    if config is None:
        return None
    config = replace(config)

    app_config = get_subagents_app_config()
    effective_timeout = app_config.get_timeout_for(name)
    if effective_timeout != config.timeout_seconds:
        logger.debug(
            "Subagent '%s': timeout overridden by config.yaml (%ss -> %ss)",
            name,
            config.timeout_seconds,
            effective_timeout,
        )
        config = replace(config, timeout_seconds=effective_timeout)
    return config


def list_subagents() -> list[SubagentConfig]:
    """List all resolved subagent configs."""
    return [config for config in (get_subagent_config(name) for name in BUILTIN_SUBAGENTS) if config is not None]


def get_subagent_names() -> list[str]:
    """List builtin subagent names."""
    return list(BUILTIN_SUBAGENTS.keys())
