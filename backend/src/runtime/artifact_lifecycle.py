from __future__ import annotations

import gc
import logging
import os
import time
from pathlib import Path
from typing import Any

from src.gateway.observability import record_tool_trace
from src.runtime.config.paths import get_paths

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return default


def _safe_unlink(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.debug("Artifact lifecycle failed to remove %s: %s", path, exc)
        return False


def _prune_old_files(root: Path, *, older_than_seconds: int) -> dict[str, Any]:
    if not root.exists():
        return {"root": str(root), "removed_files": 0, "removed_bytes": 0}
    cutoff = time.time() - older_than_seconds
    removed_files = 0
    removed_bytes = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime >= cutoff:
            continue
        if _safe_unlink(path):
            removed_files += 1
            removed_bytes += stat.st_size
    for path in sorted((item for item in root.rglob("*") if item.is_dir()), key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass
    return {"root": str(root), "removed_files": removed_files, "removed_bytes": removed_bytes}


def _cap_trace_file(path: Path, *, max_bytes: int) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "rotated": False}
    try:
        size = path.stat().st_size
    except OSError:
        return {"path": str(path), "rotated": False}
    if size <= max_bytes:
        return {"path": str(path), "rotated": False, "size": size}
    rotated = path.with_suffix(path.suffix + ".1")
    try:
        if rotated.exists():
            rotated.unlink()
        path.replace(rotated)
    except OSError as exc:
        logger.debug("Trace rotation failed for %s: %s", path, exc)
        return {"path": str(path), "rotated": False, "size": size}
    return {"path": str(path), "rotated": True, "size": size, "rotated_to": str(rotated)}


def run_artifact_lifecycle() -> dict[str, Any]:
    paths = get_paths()
    artifact_retention_days = _env_int("OCTO_ARTIFACT_RETENTION_DAYS", 14)
    transient_retention_days = _env_int("OCTO_TRANSIENT_RETENTION_DAYS", 3)
    trace_max_bytes = _env_int("OCTO_TRACE_MAX_BYTES", 25 * 1024 * 1024)

    artifact_roots = [
        paths.default_workspace_dir / "threads",
        paths.workflow_tasks_dir,
        paths.runtime_root / "artifacts",
    ]
    transient_roots = [
        paths.runtime_root / "tmp",
        paths.runtime_root / "uploads",
        paths.runtime_root / "cache",
    ]

    artifact_results = [
        _prune_old_files(root, older_than_seconds=artifact_retention_days * 86400)
        for root in artifact_roots
    ]
    transient_results = [
        _prune_old_files(root, older_than_seconds=transient_retention_days * 86400)
        for root in transient_roots
    ]
    trace_rotation = _cap_trace_file(paths.runtime_root / "observability" / "tool-trace.jsonl", max_bytes=trace_max_bytes)
    collected = gc.collect()
    result = {
        "artifact_retention_days": artifact_retention_days,
        "transient_retention_days": transient_retention_days,
        "artifact_roots": artifact_results,
        "transient_roots": transient_results,
        "trace_rotation": trace_rotation,
        "gc_collected": collected,
    }
    record_tool_trace("artifact_lifecycle", **result)
    return result
