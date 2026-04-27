#!/usr/bin/env python3
"""Fail if source-controlled files contain legacy OctoAgent runtime paths."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


BLOCKED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"/home/sieve-pub/codex(?:/|$)"),
    re.compile(r"/Users/henry/Desktop/octoagent/backend/\.octoagent(?:/|$)"),
    re.compile(r"/app/backend/\.octoagent(?:/|$)"),
    re.compile(r"backend/\.octoagent/threads(?:/|$)"),
    re.compile(r"\.octoagent/(?:memory|global_memory|system_memory|checkpoints)(?:\.|/|$)"),
)

BLOCKED_TRACKED_PATHS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^workspace/default/agents/[^/]+/memory\.json$"),
    re.compile(r"^workspace/default/memory(?:\..*)?\.json$"),
)

ALLOWLIST: tuple[re.Pattern[str], ...] = (
    re.compile(r"^Makefile$"),
    re.compile(r"^scripts/check_legacy_paths\.py$"),
)


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [Path(item.decode()) for item in result.stdout.split(b"\0") if item]


def _is_allowlisted(path: Path) -> bool:
    normalized = path.as_posix()
    return any(pattern.search(normalized) for pattern in ALLOWLIST)


def main() -> int:
    failures: list[str] = []
    for path in _tracked_files():
        if any(pattern.search(path.as_posix()) for pattern in BLOCKED_TRACKED_PATHS):
            failures.append(f"{path}: runtime memory files must not be tracked")
            continue
        if _is_allowlisted(path) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in BLOCKED_PATTERNS):
                failures.append(f"{path}:{lineno}: {line.strip()}")

    if failures:
        print("Legacy OctoAgent runtime paths are not allowed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print("No legacy OctoAgent runtime paths found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
