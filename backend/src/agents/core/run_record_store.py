"""Persistent append-only store for agent execution run records."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from src.runtime.config.paths import get_paths

_LOCK = RLock()


def _store_path() -> Path:
    return get_paths().runtime_root / "run_records.jsonl"


def append_run_record(
    record: dict[str, Any],
    *,
    thread_id: str | None = None,
    agent_name: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Persist a normalized run record and return the stored copy."""

    stored = {
        "record_id": uuid4().hex,
        "stored_at": datetime.now(UTC).isoformat(),
        "thread_id": thread_id,
        "run_id": run_id,
        "agent_name": agent_name,
        **record,
    }
    path = _store_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(stored, ensure_ascii=False, sort_keys=True) + "\n")
    return stored


def list_run_records(
    *,
    limit: int = 50,
    thread_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent stored run records, newest first."""

    path = _store_path()
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with _LOCK:
        lines = path.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if thread_id and item.get("thread_id") != thread_id:
            continue
        records.append(item)
        if len(records) >= max(1, limit):
            break
    return records


def build_run_record_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build compact counters for runtime observability surfaces."""

    total = len(records)
    failed = 0
    approval_blocked = 0
    fallback_used = 0
    tool_failures = 0
    for record in records:
        final = record.get("final_evaluation") or {}
        if final.get("status") == "failed":
            failed += 1
        contract = record.get("instruction_contract") or {}
        if contract.get("requires_confirmation") and final.get("status") == "blocked":
            approval_blocked += 1
        fallback = record.get("fallback") or {}
        if fallback.get("used"):
            fallback_used += 1
        tools = record.get("tools") or {}
        tool_failures += len(tools.get("failed") or [])
    return {
        "total": total,
        "failed": failed,
        "approval_blocked": approval_blocked,
        "fallback_used": fallback_used,
        "tool_failures": tool_failures,
    }


__all__ = [
    "append_run_record",
    "build_run_record_summary",
    "list_run_records",
]
