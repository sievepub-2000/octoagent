"""Catalog and config resolution for builtin subagents."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from src.runtime.config.app_config import get_app_config
from src.runtime.config.model_config import ModelConfig
from src.runtime.config.paths import resolve_configured_default_model_name
from src.runtime.config.subagents_config import get_subagents_app_config

from .builtins import BUILTIN_SUBAGENTS
from .config import SubagentConfig

logger = logging.getLogger(__name__)

_AGENCY_AUTO_MODEL = "auto"
_FALLBACK_AGENCY_TEMPLATES = (
    {
        "template_id": "ui-designer",
        "name": "UI Designer",
        "description": "Designs clear, usable interface flows and visual structure for product work.",
        "source_category": "agency-agents",
        "soul": ("You specialize in user interface and experience design. Focus on practical layouts, interaction states, visual hierarchy, accessibility, and implementation-ready guidance."),
    },
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _agency_templates_path() -> Path:
    return _repo_root() / "skills" / "custom" / "agency-agents" / "agent-templates.json"


def _iter_agency_templates() -> Iterable[dict]:
    path = _agency_templates_path()
    if not path.exists():
        return _FALLBACK_AGENCY_TEMPLATES
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to read Agency Agents templates from %s", path, exc_info=True)
        return _FALLBACK_AGENCY_TEMPLATES
    templates = payload.get("templates") if isinstance(payload, dict) else None
    if not isinstance(templates, list):
        return _FALLBACK_AGENCY_TEMPLATES
    parsed = tuple(template for template in templates if isinstance(template, dict))
    return parsed or _FALLBACK_AGENCY_TEMPLATES


def _is_local_model(model: ModelConfig) -> bool:
    provider_name = (model.provider_name or "").lower()
    return provider_name in {"llamacpp", "llama.cpp", "ollama", "local"}


def _score_agency_model(model: ModelConfig, template_text: str, default_model_name: str | None) -> int:
    score = 0
    if model.name == default_model_name:
        score += 60
    if _is_local_model(model):
        score += 40
    if model.supports_thinking:
        score += 8
    if model.supports_reasoning_effort:
        score += 4
    if model.max_context_tokens:
        score += min(model.max_context_tokens // 32768, 8)

    if any(token in template_text for token in ("image", "visual", "design", "ui", "ux", "brand", "video")):
        score += 20 if model.supports_vision else -10
    if any(token in template_text for token in ("engineering", "architect", "security", "devops", "backend", "frontend", "code", "ai", "data")):
        score += 16 if model.supports_thinking else 0
    if any(token in template_text for token in ("research", "analysis", "strategy", "planning", "optimization")):
        score += 10 if model.supports_reasoning_effort else 0
    return score


def _resolve_default_model_name() -> str | None:
    app_config = get_app_config()
    return resolve_configured_default_model_name(model.name for model in app_config.models)


def _select_agency_model(template_text: str) -> str:
    app_config = get_app_config()
    default_model_name = resolve_configured_default_model_name(model.name for model in app_config.models)
    if not app_config.models:
        return default_model_name or "inherit"
    best = max(
        app_config.models,
        key=lambda model: _score_agency_model(model, template_text, default_model_name),
    )
    return best.name or default_model_name or "inherit"


@lru_cache(maxsize=1)
def _load_agency_subagents() -> dict[str, SubagentConfig]:
    configs: dict[str, SubagentConfig] = {}
    for template in _iter_agency_templates():
        template_id = str(template.get("template_id") or "").strip()
        name = str(template.get("name") or "").strip()
        description = str(template.get("description") or "").strip()
        soul = str(template.get("soul") or "").strip()
        if not template_id or not name or not soul:
            continue
        subagent_name = f"agency-{template_id}"
        configs[subagent_name] = SubagentConfig(
            name=subagent_name,
            description=f"Agency Agents role: {name}. {description}",
            system_prompt=(
                f"You are {name}, an Agency Agents role imported as an OctoAgent default subagent.\n\n"
                f"Source category: {template.get('source_category') or 'agency-agents'}\n\n"
                f"{soul}\n\n"
                "Complete delegated work autonomously, return concrete findings, and keep the parent agent's instructions authoritative."
            ),
            tools=None,
            disallowed_tools=["task", "ask_clarification", "present_files"],
            model=_AGENCY_AUTO_MODEL,
            fallback_models=[],
            max_turns=50,
            timeout_seconds=900,
        )
    return configs


def _all_subagents() -> dict[str, SubagentConfig]:
    return {**BUILTIN_SUBAGENTS, **_load_agency_subagents()}


def get_subagent_config(name: str) -> SubagentConfig | None:
    """Get a resolved subagent config by name with global overrides applied."""
    config = _all_subagents().get(name)
    if config is None:
        return None
    config = replace(config)
    default_model_name = _resolve_default_model_name()
    if name.startswith("agency-") and config.model == _AGENCY_AUTO_MODEL:
        template_text = f"{config.name} {config.description} {config.system_prompt}".lower()
        config = replace(
            config,
            model=_select_agency_model(template_text),
        )

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
