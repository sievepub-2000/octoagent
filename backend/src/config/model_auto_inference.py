"""Auto-infer model capabilities from model name, provider, and base_url.

This module allows users to configure models with minimal fields (name, model,
api_key, base_url) and have OctoAgent automatically detect:
- interface_type / provider_name (from base_url patterns)
- supports_thinking (from model name patterns)
- supports_vision (from model name patterns)
- supports_reasoning_effort (from model name patterns)
- when_thinking_enabled (from provider semantics)
- max_context_tokens (from known model defaults)
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# ── Provider inference from base_url ──────────────────────────────────────────

_URL_PROVIDER_MAP: list[tuple[str, str]] = [
    ("openrouter.ai", "openrouter"),
    ("api.openai.com", "openai"),
    ("api.anthropic.com", "anthropic"),
    ("generativelanguage.googleapis.com", "google"),
    ("api.deepseek.com", "deepseek"),
    ("api.groq.com", "groq"),
    ("api.together.xyz", "together"),
    ("api.fireworks.ai", "fireworks"),
    ("api.mistral.ai", "mistral"),
    ("api.x.ai", "xai"),
    ("api.sambanova.ai", "sambanova"),
    ("api.novita.ai", "novita"),
    ("api.moonshot.cn", "moonshot"),
    ("ark.cn-beijing.volces.com", "volcengine"),
    ("localhost", "llamacpp"),
    ("127.0.0.1", "llamacpp"),
]


def infer_provider_from_url(base_url: str | None) -> str | None:
    """Infer provider_name from base_url domain."""
    if not base_url:
        return None
    try:
        host = urlparse(base_url).hostname or ""
    except Exception:
        return None
    host_lower = host.lower()
    for pattern, provider in _URL_PROVIDER_MAP:
        if pattern in host_lower:
            return provider
    return None


# ── Thinking / reasoning detection from model slug ────────────────────────────

_THINKING_MODEL_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(o[134])\b", re.IGNORECASE),            # o1, o3, o4
    re.compile(r"\b(o[134])[-_]", re.IGNORECASE),          # o1-mini, o3-pro
    re.compile(r"thinking", re.IGNORECASE),                 # *-thinking, *thinking*
    re.compile(r"reasoner", re.IGNORECASE),                 # deepseek-reasoner
    re.compile(r"deepseek[-_]?r1", re.IGNORECASE),          # deepseek-r1
    re.compile(r"qwq", re.IGNORECASE),                      # qwq-32b
]

_REASONING_EFFORT_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(o[134])\b", re.IGNORECASE),
    re.compile(r"\b(o[134])[-_]", re.IGNORECASE),
    re.compile(r"deepseek[-_]?r1", re.IGNORECASE),
    re.compile(r"reasoner", re.IGNORECASE),
]


def infer_supports_thinking(model_slug: str) -> bool | None:
    """Return True if model name indicates thinking/reasoning support, None if unknown."""
    for pattern in _THINKING_MODEL_PATTERNS:
        if pattern.search(model_slug):
            return True
    return None


def infer_supports_reasoning_effort(model_slug: str) -> bool | None:
    """Return True if model supports reasoning_effort parameter."""
    for pattern in _REASONING_EFFORT_PATTERNS:
        if pattern.search(model_slug):
            return True
    return None


# ── Vision detection from model slug ──────────────────────────────────────────

_VISION_MODEL_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bvl\b", re.IGNORECASE),                  # *-vl-*
    re.compile(r"vision", re.IGNORECASE),                   # *-vision
    re.compile(r"\bgpt[-_]?4o\b", re.IGNORECASE),          # gpt-4o
    re.compile(r"\bgpt[-_]?5\b", re.IGNORECASE),           # gpt-5*
    re.compile(r"\bclaude[-_]?3", re.IGNORECASE),           # claude-3*
    re.compile(r"\bgemini", re.IGNORECASE),                 # gemini-*
    re.compile(r"\bgemma[-_]?4", re.IGNORECASE),            # gemma-4*
    re.compile(r"\bpixtral\b", re.IGNORECASE),              # pixtral
]

# Exclude patterns that match vision but shouldn't (text-only variants)
_VISION_EXCLUDE_PATTERNS: list[re.Pattern] = [
    re.compile(r"text[-_]?only", re.IGNORECASE),
    re.compile(r"\bmini\b.*\btext\b", re.IGNORECASE),
]


def infer_supports_vision(model_slug: str) -> bool | None:
    """Return True if model name indicates vision support, None if unknown."""
    for exclude in _VISION_EXCLUDE_PATTERNS:
        if exclude.search(model_slug):
            return None
    for pattern in _VISION_MODEL_PATTERNS:
        if pattern.search(model_slug):
            return True
    return None


# ── Context window defaults ───────────────────────────────────────────────────

_CONTEXT_DEFAULTS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"gpt[-_]?5", re.IGNORECASE), 128000),
    (re.compile(r"gpt[-_]?4o", re.IGNORECASE), 128000),
    (re.compile(r"claude[-_]?3.*sonnet|claude[-_]?3.*opus|claude[-_]?3.*haiku|claude[-_]?4", re.IGNORECASE), 200000),
    (re.compile(r"gemini[-_]?2\.5|gemini[-_]?2\.0", re.IGNORECASE), 1048576),
    (re.compile(r"gemini[-_]?1\.5", re.IGNORECASE), 1048576),
    (re.compile(r"qwen3\.6", re.IGNORECASE), 1000000),
    (re.compile(r"qwen3\.5[-_]?flash|qwen3\.5[-_]?plus|qwen[-_]?plus", re.IGNORECASE), 1000000),
    (re.compile(r"qwen3[-_]?coder[-_]?flash|qwen3[-_]?coder[-_]?plus", re.IGNORECASE), 1000000),
    (re.compile(r"qwen3[-_]?235b|qwen3[-_]?max", re.IGNORECASE), 262144),
    (re.compile(r"deepseek[-_]?v3|deepseek[-_]?r1|deepseek[-_]?chat", re.IGNORECASE), 128000),
    (re.compile(r"llama[-_]?3\.3[-_]?70b", re.IGNORECASE), 131072),
    (re.compile(r"llama[-_]?3\.1[-_]?405b", re.IGNORECASE), 131072),
]


def infer_max_context_tokens(model_slug: str) -> int | None:
    """Return known default context window for a model, or None."""
    for pattern, ctx in _CONTEXT_DEFAULTS:
        if pattern.search(model_slug):
            return ctx
    return None


# ── Thinking config defaults ─────────────────────────────────────────────────

def infer_when_thinking_enabled(model_slug: str, provider_name: str | None) -> dict | None:
    """Infer default when_thinking_enabled config for thinking models."""
    if not infer_supports_thinking(model_slug):
        return None
    provider = (provider_name or "").lower()
    # Anthropic uses direct thinking parameter
    if provider in ("anthropic", "claude"):
        return {"thinking": {"type": "enabled"}}
    # DeepSeek / Volcengine / Moonshot use extra_body
    if provider in ("deepseek", "volcengine", "moonshot", "kimi", "doubao"):
        return {"extra_body": {"thinking": {"type": "enabled"}}}
    # OpenAI-compatible (including OpenRouter) — no extra config needed
    return None


# ── Master auto-inference entry point ─────────────────────────────────────────

def auto_infer_model_fields(config_dict: dict) -> dict:
    """Fill in missing model config fields using auto-inference.

    Only sets fields that are NOT already explicitly provided by the user.
    This preserves any manual overrides while providing sensible defaults.

    Args:
        config_dict: A mutable model config dictionary (single model entry from YAML).

    Returns:
        The same dictionary with inferred fields added where missing.
    """
    model_slug = config_dict.get("model", "")
    base_url = config_dict.get("base_url")

    # Auto-detect provider_name from base_url
    if not config_dict.get("provider_name") and not config_dict.get("interface_type"):
        inferred_provider = infer_provider_from_url(base_url)
        if inferred_provider:
            config_dict["provider_name"] = inferred_provider

    effective_provider = config_dict.get("provider_name") or config_dict.get("interface_type")

    # Auto-detect supports_thinking
    if "supports_thinking" not in config_dict:
        result = infer_supports_thinking(model_slug)
        if result is not None:
            config_dict["supports_thinking"] = result

    # Auto-detect supports_reasoning_effort
    if "supports_reasoning_effort" not in config_dict:
        result = infer_supports_reasoning_effort(model_slug)
        if result is not None:
            config_dict["supports_reasoning_effort"] = result

    # Auto-detect supports_vision
    if "supports_vision" not in config_dict:
        result = infer_supports_vision(model_slug)
        if result is not None:
            config_dict["supports_vision"] = result

    # Auto-detect when_thinking_enabled
    if not config_dict.get("when_thinking_enabled") and not config_dict.get("thinking"):
        result = infer_when_thinking_enabled(model_slug, effective_provider)
        if result is not None:
            config_dict["when_thinking_enabled"] = result

    # Auto-detect max_context_tokens
    if not config_dict.get("max_context_tokens"):
        result = infer_max_context_tokens(model_slug)
        if result is not None:
            config_dict["max_context_tokens"] = result

    return config_dict
