"""Catalog and config resolution for builtin subagents."""

from __future__ import annotations

import logging
from dataclasses import replace

from src.runtime.config.app_config import get_app_config
from src.runtime.config.paths import resolve_configured_default_model_name
from src.runtime.config.subagents_config import get_subagents_app_config

from .builtins import BUILTIN_SUBAGENTS
from .config import SubagentConfig

logger = logging.getLogger(__name__)


def _resolve_default_model_name() -> str | None:
    app_config = get_app_config()
    return resolve_configured_default_model_name(model.name for model in app_config.models)


def _all_subagents() -> dict[str, SubagentConfig]:
    return BUILTIN_SUBAGENTS


def get_subagent_config(name: str) -> SubagentConfig | None:
    """Get a resolved subagent config by name with global overrides applied."""
    config = _all_subagents().get(name)
    if config is None:
        return None
    config = replace(config)
    default_model_name = _resolve_default_model_name()
    app_config = get_subagents_app_config()
    override = app_config.get_override_for(name)
    effective_timeout = app_config.get_timeout_for(name)
    if effective_timeout != config.timeout_seconds:
        logger.debug(
            "Subagent '%s': timeout overridden by config.yaml (%ss -> %ss)",
            name,
            config.timeout_seconds,
            effective_timeout,
        )
        config = replace(config, timeout_seconds=effective_timeout)
    if override is not None:
        replace_kwargs: dict[str, object] = {}
        if override.model is not None and override.model.strip():
            replace_kwargs["model"] = override.model.strip()
        if override.max_turns is not None:
            replace_kwargs["max_turns"] = override.max_turns
        if override.tools is not None:
            replace_kwargs["tools"] = list(override.tools)
        if override.disallowed_tools is not None:
            replace_kwargs["disallowed_tools"] = list(override.disallowed_tools)
        if replace_kwargs:
            logger.debug("Subagent '%s': applied config.yaml overrides: %s", name, sorted(replace_kwargs))
            config = replace(config, **replace_kwargs)
    if default_model_name:
        config = replace(config, fallback_models=[default_model_name])
    return config


def list_subagents() -> list[SubagentConfig]:
    """List all resolved subagent configs."""
    return [config for config in (get_subagent_config(name) for name in _all_subagents()) if config is not None]


def get_subagent_names() -> list[str]:
    """List builtin subagent names."""
    return sorted(_all_subagents().keys())
