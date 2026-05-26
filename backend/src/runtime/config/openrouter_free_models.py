"""Auto-register OpenRouter free models from the server-side model cache.

OctoAgent installations often already maintain an OpenRouter model cache through
operator tools.  This module folds every cached ``:free`` model into the runtime
model pool when ``OPENROUTER_API_KEY`` is available, while preserving explicit
operator entries from ``config.yaml``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path(str(Path.home() / ".config" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "cache" / "openrouter_models.json"))
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_OPENROUTER_CATALOG_TIMEOUT_SECONDS = 8.0


def _cache_path() -> Path:
    configured = os.environ.get("OPENROUTER_MODELS_CACHE", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_CACHE_PATH


def _slug_to_config_name(slug: str) -> str:
    base = slug.removesuffix(":free")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return f"openrouter-free-{normalized}"


def _compact_description(value: Any, slug: str) -> str:
    description = str(value or "").strip()
    if not description:
        return f"OpenRouter free model imported from the server-side OpenRouter cache: {slug}."
    description = re.sub(r"\s+", " ", description)
    if len(description) > 360:
        return description[:357].rstrip() + "..."
    return description


def _supports_thinking(slug: str, meta: dict[str, Any]) -> bool:
    lowered = slug.lower()
    return bool(meta.get("thinkingConfig") or "thinking" in lowered or "reason" in lowered or "r1" in lowered)


def _build_entry(slug: str, meta: dict[str, Any]) -> dict[str, Any]:
    max_tokens = meta.get("maxTokens") or 4096
    try:
        max_tokens = int(max_tokens)
    except (TypeError, ValueError):
        max_tokens = 4096
    max_tokens = min(max(max_tokens, 256), 8192)

    entry: dict[str, Any] = {
        "name": _slug_to_config_name(slug),
        "display_name": str(meta.get("name") or slug),
        "description": _compact_description(meta.get("description"), slug),
        "interface_type": "openai_compatible",
        "provider_name": "openrouter",
        "model": slug,
        "api_key": "$OPENROUTER_API_KEY",
        "base_url": OPENROUTER_BASE_URL,
        "max_tokens": max_tokens,
        "temperature": 0,
        "request_timeout": 90,
        "supports_thinking": _supports_thinking(slug, meta),
        "supports_reasoning_effort": _supports_thinking(slug, meta),
        "supports_vision": bool(meta.get("supportsImages")),
        "fallback_models": [],
    }
    context_window = meta.get("contextWindow")
    if context_window:
        try:
            entry["max_context_tokens"] = int(context_window)
        except (TypeError, ValueError):
            pass
    return entry


def _load_free_entries(cache_path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.info("OpenRouter free model cache not found: %s", cache_path)
        return []
    except Exception:
        logger.warning("Failed to read OpenRouter free model cache: %s", cache_path, exc_info=True)
        return []

    if not isinstance(data, dict):
        logger.warning("OpenRouter free model cache root is not an object: %s", cache_path)
        return []

    entries = [_build_entry(str(slug), meta) for slug, meta in data.items() if str(slug).endswith(":free") and isinstance(meta, dict)]
    entries.sort(key=lambda item: str(item.get("model")))
    return entries


def _load_live_openrouter_model_ids() -> set[str] | None:
    """Fetch the public OpenRouter model catalogue for stale-cache filtering.

    Failure is non-fatal: when offline, keep using the local cache so startup
    still works. Operators can disable the network freshness check with
    ``OPENROUTER_VALIDATE_FREE_CACHE=0``.
    """
    if os.environ.get("OPENROUTER_VALIDATE_FREE_CACHE", "1").strip() == "0":
        return None
    try:
        request = urllib.request.Request(
            f"{OPENROUTER_BASE_URL}/models",
            headers={"User-Agent": "OctoAgent model-cache-validator"},
        )
        with urllib.request.urlopen(
            request,
            timeout=_OPENROUTER_CATALOG_TIMEOUT_SECONDS,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        logger.info("OpenRouter free model cache freshness check failed; using local cache", exc_info=True)
        return None
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return None
    return {str(item.get("id")) for item in items if isinstance(item, dict) and item.get("id")}


def auto_inject_openrouter_free_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return ``models`` extended with cached OpenRouter free models.

    No network calls are made.  The injection only runs when ``OPENROUTER_API_KEY``
    is present so generated entries can resolve through the normal config loader.
    """

    if not os.environ.get("OPENROUTER_API_KEY"):
        return models

    free_entries = _load_free_entries(_cache_path())
    if not free_entries:
        return models
    live_model_ids = _load_live_openrouter_model_ids()
    if live_model_ids is not None:
        before_count = len(free_entries)
        free_entries = [entry for entry in free_entries if str(entry.get("model")) in live_model_ids]
        removed_count = before_count - len(free_entries)
        if removed_count:
            logger.info("OpenRouter free model cache: skipped %d stale model(s)", removed_count)
        if not free_entries:
            return models

    extended = [dict(model) if isinstance(model, dict) else model for model in models]
    index_by_name = {str(model.get("name")): i for i, model in enumerate(extended) if isinstance(model, dict)}
    index_by_slug = {str(model.get("model")): i for i, model in enumerate(extended) if isinstance(model, dict)}

    added = 0
    refreshed = 0
    for entry in free_entries:
        slug = str(entry["model"])
        existing_index = index_by_slug.get(slug)
        if existing_index is None:
            existing_index = index_by_name.get(str(entry["name"]))
        if existing_index is None:
            extended.append(entry)
            index_by_name[str(entry["name"])] = len(extended) - 1
            index_by_slug[slug] = len(extended) - 1
            added += 1
            continue

        current = dict(extended[existing_index])
        for key in (
            "display_name",
            "description",
            "interface_type",
            "provider_name",
            "max_tokens",
            "request_timeout",
            "supports_thinking",
            "supports_reasoning_effort",
            "supports_vision",
            "max_context_tokens",
        ):
            if key in entry:
                current[key] = entry[key]
        current.setdefault("api_key", "$OPENROUTER_API_KEY")
        current.setdefault("base_url", OPENROUTER_BASE_URL)
        current.setdefault("temperature", 0)
        extended[existing_index] = current
        refreshed += 1

    logger.info(
        "OpenRouter free model cache: %d cached, %d added, %d refreshed",
        len(free_entries),
        added,
        refreshed,
    )
    return extended


__all__ = ["auto_inject_openrouter_free_models"]
