"""Canonical UTC datetime helpers.

Replaces 18 duplicated ``_utc_now`` / ``_utc_now_iso`` definitions scattered
across the backend. All variants encountered in the codebase are preserved
here as distinct callables so behavior is byte-for-byte identical to the
local copies they replace.
"""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = [
    "utc_now",
    "utc_now_iso",
    "utc_now_iso_seconds",
    "utc_now_iso_z",
]


def utc_now() -> datetime:
    """Return the current UTC moment as a tz-aware ``datetime``."""
    return datetime.now(UTC)


def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 with microsecond precision."""
    return datetime.now(UTC).isoformat()


def utc_now_iso_seconds() -> str:
    """Return current UTC time as ISO-8601 truncated to seconds."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def utc_now_iso_z() -> str:
    """Return current UTC time as ISO-8601 with seconds precision and ``Z`` suffix."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
