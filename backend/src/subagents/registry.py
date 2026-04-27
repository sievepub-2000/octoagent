"""Compatibility registry facade for subagent catalog access."""

from .catalog import get_subagent_config, get_subagent_names, list_subagents

__all__ = [
    "get_subagent_config",
    "get_subagent_names",
    "list_subagents",
]
