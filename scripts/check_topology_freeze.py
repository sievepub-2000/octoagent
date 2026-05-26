"""Topology freeze enforcement (Phase 0, 2026-05-26).

Validates that backend/src/ top-level directories and files match the frozen
snapshot recorded in project_docs/docs/TOPOLOGY_FREEZE_2026-05-26.md.

Exit codes:
    0 — current layout matches the snapshot
    1 — current layout drifted from the snapshot (printed diff)

Usage:
    python scripts/check_topology_freeze.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "backend" / "src"

FROZEN_DIRS = frozenset({
    "agents",
    "community",
    "gateway",
    "governance",
    "harness",
    "interfaces",
    "models",
    "runtime",
    "storage",
    "tools",
    "utils",
})

FROZEN_FILES = frozenset({
    "__init__.py",
})

IGNORE = frozenset({"__pycache__", "octoagent.egg-info", ".pytest_cache", ".ruff_cache", ".mypy_cache"})


def current_layout(root: Path) -> tuple[set[str], set[str]]:
    dirs: set[str] = set()
    files: set[str] = set()
    if not root.is_dir():
        print(f"error: {root} does not exist", file=sys.stderr)
        sys.exit(2)
    for entry in root.iterdir():
        if entry.name in IGNORE:
            continue
        if entry.is_dir():
            dirs.add(entry.name)
        elif entry.is_file() and entry.suffix == ".py":
            files.add(entry.name)
    return dirs, files


def main() -> int:
    dirs, files = current_layout(SRC_ROOT)

    added_dirs = sorted(dirs - FROZEN_DIRS)
    removed_dirs = sorted(FROZEN_DIRS - dirs)
    added_files = sorted(files - FROZEN_FILES)
    removed_files = sorted(FROZEN_FILES - files)

    drift = added_dirs or added_files
    if not drift and not removed_dirs and not removed_files:
        print("topology freeze: OK (matches 2026-05-26 snapshot)")
        return 0

    print("topology freeze: DRIFT DETECTED", file=sys.stderr)
    if added_dirs:
        print(f"  new top-level dirs   (REJECT): {added_dirs}", file=sys.stderr)
    if added_files:
        print(f"  new top-level files  (REJECT): {added_files}", file=sys.stderr)
    if removed_dirs:
        print(f"  removed top-level dirs       : {removed_dirs}", file=sys.stderr)
    if removed_files:
        print(f"  removed top-level files      : {removed_files}", file=sys.stderr)
    print(
        "\nIf this drift is intentional, register an exception in\n"
        "  project_docs/docs/TOPOLOGY_FREEZE_2026-05-26.md  §2\n"
        "and update FROZEN_DIRS / FROZEN_FILES in this script.",
        file=sys.stderr,
    )
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
