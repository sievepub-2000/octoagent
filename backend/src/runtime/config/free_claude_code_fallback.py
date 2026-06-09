"""Auto-register a free fallback model pool inspired by the ``free-claude-code``
community project.

The upstream project proxies NVIDIA's free NIM inference tier as an OpenAI /
Anthropic compatible endpoint so that developers without a paid API key can
still drive Claude-Code-style agents.  We adopt the same idea defensively:

- When ``NVIDIA_API_KEY`` (or ``FREE_CLAUDE_CODE_API_KEY``) is present in the
  environment *and* the operator has not already configured NVIDIA models in
  ``config.yaml``, we append a curated list of free-tier NIM models to the
  resolved model list.
- When it is not set, this module is a no-op; no network calls are made.
- The primary model selection in ``create_chat_model`` is unchanged — these
  entries simply become reachable as explicit or fallback targets for the
  existing model-pool-v2 resolver.

This adapter intentionally stays shallow: it does not rewrite or reorder the
user's configured models, and the observation-only policy from the repository
memory applies (no automatic primary promotion).
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ``base_url`` is the public OpenAI-compatible NIM endpoint.  Swap it via
# ``NVIDIA_BASE_URL`` if the operator runs a proxy (e.g. free-claude-code's
# self-hosted gateway).
_DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Curated free-tier NIM catalogue. Keep the list small; operators who want
# more can copy the shape into ``config.yaml``.
_FREE_POOL: list[dict[str, Any]] = [
    {
        "name": "nvidia-llama-3.3-70b",
        "display_name": "NVIDIA · Llama 3.3 70B (free)",
        "interface_type": "openai_compatible",
        "provider_name": "nvidia",
        "model": "meta/llama-3.3-70b-instruct",
        "max_tokens": 4096,
        "max_context_tokens": 131072,
        "supports_vision": False,
    },
    {
        "name": "nvidia-deepseek-r1",
        "display_name": "NVIDIA · DeepSeek R1 (free)",
        "interface_type": "openai_compatible",
        "provider_name": "nvidia",
        "model": "deepseek-ai/deepseek-r1",
        "max_tokens": 8192,
        "supports_thinking": True,
    },
    {
        "name": "nvidia-qwen2.5-coder-32b",
        "display_name": "NVIDIA · Qwen2.5 Coder 32B (free)",
        "interface_type": "openai_compatible",
        "provider_name": "nvidia",
        "model": "qwen/qwen2.5-coder-32b-instruct",
        "max_tokens": 4096,
    },
]


def _resolve_api_key() -> str | None:
    for env_name in ("NVIDIA_API_KEY", "FREE_CLAUDE_CODE_API_KEY"):
        value = os.environ.get(env_name)
        if value:
            return value
    return None


def auto_inject_free_fallback_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return ``models`` possibly extended with NVIDIA free-tier entries.

    Safe to call on every config reload.  Mutation of the original list is
    avoided so caller ordering is preserved when no injection happens.
    """

    if os.environ.get("OCTOAGENT_DISABLE_FREE_MODEL_POOL", "").strip().lower() in {"1", "true", "yes", "on"}:
        return models
    api_key = _resolve_api_key()
    if not api_key:
        return models

    # Respect operator-provided NVIDIA entries (identified by name prefix or
    # provider_name).  If the operator has configured anything, we don't touch
    # their setup.
    for entry in models:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").lower()
        provider = str(entry.get("provider_name") or "").lower()
        if name.startswith("nvidia-") or provider == "nvidia":
            return models

    base_url = os.environ.get("NVIDIA_BASE_URL", _DEFAULT_BASE_URL)
    extended = list(models)
    for template in _FREE_POOL:
        extended.append(
            {
                **template,
                "api_key": api_key,
                "base_url": base_url,
                "auto_injected_free_pool": True,
            }
        )
    logger.info(
        "free-claude-code fallback: injected %d NVIDIA NIM models from %s",
        len(_FREE_POOL),
        base_url,
    )
    return extended


__all__ = ["auto_inject_free_fallback_models"]
