from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from src.runtime.config.paths import Paths

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_MAX_FIELD_CHARS = 8_000


def _trace_path() -> Path:
    return Paths().runtime_root / "observability" / "tool-trace.jsonl"


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= _MAX_FIELD_CHARS else value[:_MAX_FIELD_CHARS] + "...[truncated]"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value[:80]]
    return str(value)


def record_tool_trace(event: str, **payload: Any) -> None:
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        **{key: _safe_value(value) for key, value in payload.items()},
    }
    try:
        path = _trace_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with _lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except Exception:
        logger.debug("Failed to persist tool trace event", exc_info=True)


def record_exception_trace(component: str, exc: BaseException, **payload: Any) -> None:
    record_tool_trace(
        "exception",
        component=component,
        error_type=type(exc).__name__,
        error=str(exc),
        **payload,
    )
