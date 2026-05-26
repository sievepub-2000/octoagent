"""Observation helpers shared by workflow-facing runtime surfaces."""

from __future__ import annotations

import re

_TIMELINE_HEADER_RE = re.compile(r"^## (?P<timestamp>[^\n]+?) - (?P<title>.+)$")


def parse_run_log_timeline(run_log: str) -> list[dict[str, object]]:
    """Parse workflow run-log sections into a timeline payload."""
    events: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for raw_line in run_log.splitlines():
        line = raw_line.rstrip()
        header_match = _TIMELINE_HEADER_RE.match(line)
        if header_match:
            if current is not None:
                events.append(current)
            current = {
                "created_at": header_match.group("timestamp"),
                "title": header_match.group("title"),
                "details": [],
            }
            continue
        if current is None:
            continue
        if line.startswith("- "):
            current["details"].append(line[2:])
            continue
        if line.strip():
            current["details"].append(line.strip())
    if current is not None:
        events.append(current)
    return list(reversed(events))


__all__ = ["parse_run_log_timeline"]
