"""Observation routes backed by existing task workspace run logs."""

from __future__ import annotations

import json
from collections import deque
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from src.runtime.config.paths import get_paths

router = APIRouter(prefix="/api/observation", tags=["observation"])


class ToolTraceEntry(BaseModel):
    ts: str | None = None
    event: str
    tool: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolTraceResponse(BaseModel):
    path: str
    entries: list[ToolTraceEntry] = Field(default_factory=list)
    count: int = 0
    limit: int
    truncated: bool = False


def _tool_trace_path():
    return get_paths().runtime_root / "observability" / "tool-trace.jsonl"


def _load_tool_trace_tail(*, limit: int, event: str | None) -> tuple[list[ToolTraceEntry], bool]:
    path = _tool_trace_path()
    if not path.exists():
        return [], False

    retained: deque[ToolTraceEntry] = deque(maxlen=limit)
    matched_count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            event_name = str(payload.get("event") or "unknown")
            if event and event_name != event:
                continue
            matched_count += 1
            retained.append(
                ToolTraceEntry(
                    ts=str(payload.get("ts")) if payload.get("ts") is not None else None,
                    event=event_name,
                    tool=str(payload.get("tool")) if payload.get("tool") is not None else None,
                    payload={str(key): value for key, value in payload.items() if key not in {"ts", "event", "tool"}},
                )
            )
    return list(retained), matched_count > len(retained)


@router.get("/tool-trace", response_model=ToolTraceResponse)
async def get_tool_trace_tail(
    limit: int = Query(default=80, ge=1, le=500),
    event: str | None = Query(default=None, min_length=1, max_length=80),
) -> ToolTraceResponse:
    trace_path = _tool_trace_path()
    entries, truncated = _load_tool_trace_tail(limit=limit, event=event)
    return ToolTraceResponse(
        path=str(trace_path),
        entries=entries,
        count=len(entries),
        limit=limit,
        truncated=truncated,
    )
