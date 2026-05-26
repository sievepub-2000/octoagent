#!/usr/bin/env python3
"""Import OpenRouter free model metadata into OctoAgent config.yaml.

The script reads the local OpenRouter model cache used by the operator's
server-side tools and merges every ``:free`` model into ``config.yaml``. Existing
operator model entries are preserved; if an existing entry already references the
same OpenRouter model slug, the script refreshes non-secret metadata only.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CACHE = Path(
    "/home/sieve-pub/.config/Code/User/globalStorage/saoudrizwan.claude-dev/cache/openrouter_models.json"
)
DEFAULT_CONFIG = Path("config.yaml")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def slug_to_config_name(slug: str) -> str:
    base = slug.removesuffix(":free")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return f"openrouter-free-{normalized}"


def compact_description(value: Any, slug: str) -> str:
    description = str(value or "").strip()
    if not description:
        return f"OpenRouter free model imported from the server-side OpenRouter cache: {slug}."
    description = re.sub(r"\s+", " ", description)
    if len(description) > 360:
        description = description[:357].rstrip() + "..."
    return description


def supports_thinking(slug: str, meta: dict[str, Any]) -> bool:
    lowered = slug.lower()
    return bool(
        meta.get("thinkingConfig")
        or "thinking" in lowered
        or "reason" in lowered
        or "r1" in lowered
    )


def build_entry(slug: str, meta: dict[str, Any]) -> dict[str, Any]:
    context_window = meta.get("contextWindow")
    max_tokens = meta.get("maxTokens") or 4096
    try:
        max_tokens = int(max_tokens)
    except (TypeError, ValueError):
        max_tokens = 4096
    max_tokens = min(max(max_tokens, 256), 8192)

    entry: dict[str, Any] = {
        "name": slug_to_config_name(slug),
        "display_name": str(meta.get("name") or slug),
        "description": compact_description(meta.get("description"), slug),
        "interface_type": "openai_compatible",
        "provider_name": "openrouter",
        "model": slug,
        "api_key": "$OPENROUTER_API_KEY",
        "base_url": OPENROUTER_BASE_URL,
        "max_tokens": max_tokens,
        "temperature": 0,
        "request_timeout": 90,
        "supports_thinking": supports_thinking(slug, meta),
        "supports_reasoning_effort": supports_thinking(slug, meta),
        "supports_vision": bool(meta.get("supportsImages")),
        "fallback_models": [],
    }
    if context_window:
        try:
            entry["max_context_tokens"] = int(context_window)
        except (TypeError, ValueError):
            pass
    return entry


def load_free_models(cache_path: Path) -> list[dict[str, Any]]:
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected {cache_path} to contain an object keyed by model slug")

    entries: list[dict[str, Any]] = []
    for slug, meta in data.items():
        if not str(slug).endswith(":free") or not isinstance(meta, dict):
            continue
        entries.append(build_entry(str(slug), meta))
    entries.sort(key=lambda item: str(item.get("model")))
    return entries


def merge_models(config_data: dict[str, Any], free_entries: list[dict[str, Any]]) -> tuple[int, int]:
    models = list(config_data.get("models") or [])
    index_by_name = {str(model.get("name")): i for i, model in enumerate(models) if isinstance(model, dict)}
    index_by_slug = {str(model.get("model")): i for i, model in enumerate(models) if isinstance(model, dict)}

    added = 0
    refreshed = 0
    for entry in free_entries:
        slug = str(entry["model"])
        existing_index = index_by_slug.get(slug)
        if existing_index is None:
            existing_index = index_by_name.get(str(entry["name"]))
        if existing_index is None:
            models.append(entry)
            index_by_name[str(entry["name"])] = len(models) - 1
            index_by_slug[slug] = len(models) - 1
            added += 1
            continue

        current = dict(models[existing_index])
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
        models[existing_index] = current
        refreshed += 1

    deduped: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for model in models:
        if not isinstance(model, dict):
            deduped.append(model)
            continue
        slug = str(model.get("model") or "")
        if slug and slug in seen_slugs:
            continue
        if slug:
            seen_slugs.add(slug)
        deduped.append(model)

    config_data["models"] = deduped
    return added, refreshed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    free_entries = load_free_models(args.cache)
    config_data = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    added, refreshed = merge_models(config_data, free_entries)
    args.config.write_text(
        yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"free_models={len(free_entries)} added={added} refreshed={refreshed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
