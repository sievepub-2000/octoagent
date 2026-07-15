"""Filesystem-backed lifecycle for operator-installed tools.

Each managed tool owns exactly one directory under ``runtime/system_tools``.
The manifest is the management seam used by Tools Hub, installers, callers,
and uninstall cleanup; directories without a manifest are never deleted.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.utils.json_atomic import write_json_atomic

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def managed_tools_root() -> Path:
    configured = os.getenv("OCTOAGENT_MANAGED_TOOLS_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "runtime" / "system_tools"


def normalize_tool_name(value: str) -> str:
    name = value.strip()
    if not _SAFE_NAME.fullmatch(name):
        raise ValueError("tool name must match [A-Za-z0-9][A-Za-z0-9._-]{0,79}")
    return name


def tool_root(name: str, *, root: Path | None = None) -> Path:
    base = (root or managed_tools_root()).resolve()
    target = (base / normalize_tool_name(name)).resolve()
    if target.parent != base:
        raise ValueError("managed tool path escapes runtime/system_tools")
    return target


def register_managed_tool(
    name: str,
    *,
    root: Path | None = None,
    source_type: str,
    source: str,
    version: str = "",
    entrypoint: str = "",
    invocation: str = "",
    description: str = "",
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = tool_root(name, root=root)
    target.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "name": normalize_tool_name(name),
        "description": description.strip(),
        "source_type": source_type.strip(),
        "source": source.strip(),
        "version": version.strip(),
        "entrypoint": entrypoint.strip(),
        "invocation": invocation.strip(),
        "install_root": str(target),
        "installed_at": datetime.now(UTC).isoformat(),
        "verification": dict(verification or {}),
    }
    write_json_atomic(target / "manifest.json", manifest)
    (target / "artifacts").mkdir(exist_ok=True)
    (target / "cache").mkdir(exist_ok=True)
    (target / "logs").mkdir(exist_ok=True)
    return manifest


def list_managed_tools(*, root: Path | None = None) -> list[dict[str, Any]]:
    base = (root or managed_tools_root()).resolve()
    if not base.exists():
        return []
    items: list[dict[str, Any]] = []
    for manifest_path in sorted(base.glob("*/manifest.json")):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("name") or "")
        try:
            expected = tool_root(name, root=base) / "manifest.json"
        except ValueError:
            continue
        if expected != manifest_path.resolve():
            continue
        entrypoint = str(payload.get("entrypoint") or "")
        entrypoint_path = (manifest_path.parent / entrypoint).resolve() if entrypoint else None
        payload["installed"] = True
        payload["callable"] = bool(
            entrypoint_path
            and manifest_path.parent.resolve() in entrypoint_path.parents
            and entrypoint_path.exists()
        )
        items.append(payload)
    return items


def uninstall_managed_tool(name: str, *, root: Path | None = None) -> dict[str, Any]:
    target = tool_root(name, root=root)
    manifest_path = target / "manifest.json"
    if not manifest_path.is_file():
        return {"ok": False, "error": "managed_manifest_not_found", "install_root": str(target)}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if str(manifest.get("name") or "") != normalize_tool_name(name):
        return {"ok": False, "error": "managed_manifest_name_mismatch", "install_root": str(target)}
    shutil.rmtree(target)
    return {
        "ok": not target.exists(),
        "name": name,
        "removed_root": str(target),
        "post_delete_visible": target.exists(),
    }
