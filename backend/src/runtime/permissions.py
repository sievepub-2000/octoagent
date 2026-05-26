"""Startup repair for OctoAgent runtime-owned writable paths.

Cross-platform: on Windows, ownership / chmod operations are skipped silently
because NTFS uses ACLs and Python's `os.chown` is not available.
"""

from __future__ import annotations

import logging
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from src.runtime.config.paths import Paths, get_paths
from src.runtime.identity import IS_WINDOWS, get_runtime_identity

logger = logging.getLogger(__name__)


@dataclass
class RuntimePermissionRepairReport:
    checked: list[str] = field(default_factory=list)
    repaired: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped_platform: bool = False


def _target_uid_gid() -> tuple[int, int] | None:
    """Return the target (uid, gid) on POSIX, or None on Windows."""
    if IS_WINDOWS:
        return None
    identity = get_runtime_identity()
    uid = identity.uid if identity.uid is not None else os.getuid()
    gid = identity.gid if identity.gid is not None else os.getgid()
    return uid, gid


def runtime_write_roots(paths: Paths | None = None, backend_state_root: Path | None = None) -> list[Path]:
    resolved_paths = paths or get_paths()
    backend_state = backend_state_root or (Path(__file__).resolve().parents[1] / ".octoagent")
    return [
        backend_state,
        resolved_paths.runtime_root,
        resolved_paths.env_dir,
        resolved_paths.workflow_tasks_state_dir,
    ]


def _repair_mode(path: Path) -> bool:
    if IS_WINDOWS:
        return False
    desired_bits = 0o770 if path.is_dir() else 0o660
    current_mode = stat.S_IMODE(path.stat().st_mode)
    if (current_mode & desired_bits) == desired_bits:
        return False
    path.chmod(current_mode | desired_bits)
    return True


def _repair_owner(path: Path, uid: int, gid: int) -> bool:
    if IS_WINDOWS:
        return False
    current = path.stat()
    if current.st_uid == uid and current.st_gid == gid:
        return False
    if os.geteuid() != 0:  # type: ignore[attr-defined]
        raise PermissionError(
            f"{path} is owned by {current.st_uid}:{current.st_gid}; restart repair as root or chown it to {uid}:{gid}",
        )
    os.chown(path, uid, gid)  # type: ignore[attr-defined]
    return True


def _iter_existing_tree(root: Path) -> list[Path]:
    if not root.exists():
        return [root]
    entries = [root]
    entries.extend(root.rglob("*"))
    return entries


def repair_runtime_write_permissions(
    paths: Paths | None = None,
    backend_state_root: Path | None = None,
) -> RuntimePermissionRepairReport:
    """Create runtime directories.

    On POSIX, also normalise ownership/mode bits.  On Windows, only mkdir is
    performed because ACL inheritance handles access for the current user.
    """

    report = RuntimePermissionRepairReport()
    target = _target_uid_gid()  # None on Windows
    if target is None:
        report.skipped_platform = True

    for root in runtime_write_roots(paths, backend_state_root):
        try:
            root.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            report.warnings.append(f"{root}: mkdir failed: {exc}")
            continue

        if target is None:
            # Windows: skip ownership/mode walk; presence of the dir is enough
            report.checked.append(str(root))
            continue

        uid, gid = target
        for path in _iter_existing_tree(root):
            report.checked.append(str(path))
            try:
                changed_owner = _repair_owner(path, uid, gid)
                changed_mode = _repair_mode(path)
                if changed_owner or changed_mode:
                    report.repaired.append(str(path))
            except Exception as exc:
                report.warnings.append(f"{path}: {exc}")

    if report.warnings:
        logger.warning("Runtime permission repair completed with warnings: %s", report.warnings)
    else:
        logger.info(
            "Runtime permission repair checked %d path(s), repaired %d (platform_skip=%s)",
            len(report.checked),
            len(report.repaired),
            report.skipped_platform,
        )
    return report
