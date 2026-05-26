"""Helpers for LangGraph remote run payload compatibility."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_REMOTE_RUNTIME_METADATA_KEYS = (
    "agent_name",
    "conversation_language",
    "is_bootstrap",
    "is_plan_mode",
    "max_concurrent_subagents",
    "model",
    "model_name",
    "reasoning_effort",
    "subagent_enabled",
    "thinking_enabled",
)


def _as_dict(value: Any) -> dict[str, Any]:
    """Return a shallow dict copy for mapping-like values."""
    return dict(value) if isinstance(value, Mapping) else {}


def normalize_remote_run_payload(
    run_config: Mapping[str, Any] | None,
    run_context: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize payloads for LangGraph servers that prefer context over configurable."""
    normalized_config = dict(run_config or {})
    normalized_context = _as_dict(run_context)
    metadata = _as_dict(normalized_config.get("metadata"))
    configurable = _as_dict(normalized_config.get("configurable"))
    normalized_config.pop("configurable", None)

    for key, value in configurable.items():
        if value is None:
            continue
        metadata.setdefault(key, value)
        normalized_context.setdefault(key, value)

    for key in _REMOTE_RUNTIME_METADATA_KEYS:
        value = normalized_context.get(key)
        if value is None:
            continue
        metadata.setdefault(key, value)

    if metadata:
        normalized_config["metadata"] = metadata

    return normalized_config, normalized_context
