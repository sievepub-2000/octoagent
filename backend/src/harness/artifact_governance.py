"""Conservative retention policy for OctoAgent-owned generated artifacts.

The policy deliberately excludes source, configuration, secrets, memories,
managed-tool manifests, virtual environments, and user thread outputs.  Only
explicit disposable roots are eligible for automatic cleanup.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RetentionRoot:
    name: str
    path: Path
    retention_days: int
    description: str


def app_root() -> Path:
    configured = os.getenv("OCTOAGENT_APP_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def retention_roots(*, root: Path | None = None) -> tuple[RetentionRoot, ...]:
    base = (root or app_root()).resolve()
    return (
        RetentionRoot("temporary", base / "tmp", int(os.getenv("OCTO_ARTIFACT_TMP_DAYS", "1")), "ephemeral process files"),
        RetentionRoot("tool_artifacts", base / "runtime" / "system_tools", int(os.getenv("OCTO_ARTIFACT_TOOL_DAYS", "30")), "per-tool artifacts subdirectories only"),
        RetentionRoot("runtime_logs", base / "runtime" / "logs", int(os.getenv("OCTO_ARTIFACT_LOG_DAYS", "14")), "rotatable runtime logs"),
    )


def ensure_layout(*, root: Path | None = None) -> dict[str, str]:
    base = (root or app_root()).resolve()
    paths = {
        "temporary": base / "tmp",
        "runtime_logs": base / "runtime" / "logs",
        "managed_tools": base / "runtime" / "system_tools",
        "workspace": base / "workspace",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return {name: str(path) for name, path in paths.items()}


def policy_snapshot(*, root: Path | None = None) -> dict[str, Any]:
    base = (root or app_root()).resolve()
    return {
        "app_root": str(base),
        "retention_roots": [{**asdict(item), "path": str(item.path)} for item in retention_roots(root=base)],
        "protected": [
            "source and repository metadata",
            "runtime/config and runtime/secrets",
            "workspace memory, checkpoints, databases, and user thread outputs",
            "managed-tool manifest, source, entrypoint, cache, logs, and virtual environments",
        ],
    }


def _eligible_roots(base: Path) -> list[RetentionRoot]:
    eligible: list[RetentionRoot] = []
    for item in retention_roots(root=base):
        if item.name != "tool_artifacts":
            eligible.append(item)
            continue
        if item.path.exists():
            for tool_dir in item.path.iterdir():
                artifacts = tool_dir / "artifacts"
                if tool_dir.is_dir() and artifacts.is_dir():
                    eligible.append(RetentionRoot(f"tool:{tool_dir.name}", artifacts, item.retention_days, item.description))
    return eligible


def cleanup_artifacts(*, root: Path | None = None, dry_run: bool = True, now: float | None = None) -> dict[str, Any]:
    base = (root or app_root()).resolve()
    ensure_layout(root=base)
    current = time.time() if now is None else now
    candidates: list[dict[str, Any]] = []
    removed: list[str] = []
    errors: list[dict[str, str]] = []
    reclaimed_bytes = 0

    for policy in _eligible_roots(base):
        directory = policy.path.resolve()
        if base not in directory.parents or directory == base or not directory.is_dir():
            continue
        cutoff = current - max(0, policy.retention_days) * 86400
        for item in directory.iterdir():
            try:
                stat = item.lstat()
                if stat.st_mtime > cutoff:
                    continue
                size = stat.st_size if not item.is_dir() else sum(p.stat().st_size for p in item.rglob("*") if p.is_file())
                candidates.append({"path": str(item), "policy": policy.name, "bytes": size})
                reclaimed_bytes += size
                if not dry_run:
                    if item.is_dir() and not item.is_symlink():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    removed.append(str(item))
            except OSError as exc:
                errors.append({"path": str(item), "error": str(exc)})

    return {
        "dry_run": dry_run,
        "candidate_count": len(candidates),
        "removed_count": len(removed),
        "reclaimed_bytes": reclaimed_bytes,
        "candidates": candidates,
        "removed": removed,
        "errors": errors,
    }
