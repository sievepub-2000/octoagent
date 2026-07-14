"""Shared persistence and prompt rendering for operator-managed global memory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.runtime.config.paths import get_paths


def global_memory_path() -> Path:
    configured = get_paths().env_dir / "global_memory.json"
    legacy = Path(".octoagent/global_memory.json")
    if not configured.exists() and legacy.exists():
        return legacy
    return configured


def load_global_memory() -> dict[str, Any]:
    path = global_memory_path()
    if not path.exists():
        return {"entries": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"entries": []}
    return payload if isinstance(payload, dict) else {"entries": []}


def save_global_memory(payload: dict[str, Any]) -> None:
    path = global_memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def build_global_memory_prompt(*, max_chars: int = 8000) -> str | None:
    lines: list[str] = []
    for item in load_global_memory().get("entries", []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"- {title}: {content}" if title else f"- {content}")
    if not lines:
        return None
    body = "\n".join(lines)[:max_chars]
    return "<global_memory>\nOperator-managed durable context. Apply when relevant; latest user instructions still win.\n" + body + "\n</global_memory>"


__all__ = ["build_global_memory_prompt", "global_memory_path", "load_global_memory", "save_global_memory"]
