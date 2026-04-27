"""Low-privilege silent maintenance agent for release hardening.

The generic agent intentionally does not call external models or mutate operator
configuration. It runs bounded maintenance jobs that already exist in OctoAgent:
runtime ledger cleanup and query-session compaction/recovery.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class GenericAgentStatus:
    running: bool = False
    enabled: bool = True
    interval_seconds: int = 1800
    last_run_at: str | None = None
    last_result: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None
    run_count: int = 0


class GenericMaintenanceAgent:
    def __init__(self, *, interval_seconds: int = 1800, startup_delay_seconds: int = 120) -> None:
        self.interval_seconds = max(60, interval_seconds)
        self.startup_delay_seconds = max(0, startup_delay_seconds)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._status = GenericAgentStatus(interval_seconds=self.interval_seconds)

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._status.running = True
            self._thread = threading.Thread(target=self._loop, name="generic-maintenance-agent", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        with self._lock:
            self._status.running = False

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._status.running,
                "enabled": self._status.enabled,
                "interval_seconds": self._status.interval_seconds,
                "last_run_at": self._status.last_run_at,
                "last_result": dict(self._status.last_result),
                "last_error": self._status.last_error,
                "run_count": self._status.run_count,
            }

    def run_once(self) -> dict[str, Any]:
        result: dict[str, Any] = {"created_at": _utc_now(), "jobs": {}}
        try:
            from src.query_engine.service import get_query_engine_service
            from src.runtime_governance import get_runtime_maintenance_scheduler

            runtime = get_runtime_maintenance_scheduler().run_once()
            query = get_query_engine_service().run_maintenance(created_at=_utc_now())
            result["jobs"] = {"runtime_maintenance": runtime, "query_maintenance": query}
            with self._lock:
                self._status.last_run_at = result["created_at"]
                self._status.last_result = result
                self._status.last_error = None
                self._status.run_count += 1
            return result
        except Exception as exc:  # pragma: no cover - defensive background guard
            logger.exception("Generic maintenance agent run failed")
            with self._lock:
                self._status.last_run_at = result["created_at"]
                self._status.last_error = str(exc)
                self._status.run_count += 1
            return {**result, "error": str(exc)}

    def _loop(self) -> None:
        if self.startup_delay_seconds and self._stop_event.wait(self.startup_delay_seconds):
            return
        while not self._stop_event.is_set():
            self.run_once()
            if self._stop_event.wait(self.interval_seconds):
                break


_agent: GenericMaintenanceAgent | None = None


def generic_agent_enabled() -> bool:
    return os.getenv("OCTO_GENERIC_AGENT_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def get_generic_agent() -> GenericMaintenanceAgent | None:
    return _agent


def start_generic_agent() -> GenericMaintenanceAgent | None:
    global _agent
    if not generic_agent_enabled():
        logger.info("Generic maintenance agent disabled by OCTO_GENERIC_AGENT_ENABLED")
        return None
    interval = int(os.getenv("OCTO_GENERIC_AGENT_INTERVAL_SECONDS", "1800"))
    startup_delay = int(os.getenv("OCTO_GENERIC_AGENT_STARTUP_DELAY_SECONDS", "120"))
    if _agent is None:
        _agent = GenericMaintenanceAgent(interval_seconds=interval, startup_delay_seconds=startup_delay)
    _agent.start()
    return _agent


def stop_generic_agent() -> None:
    global _agent
    if _agent is not None:
        _agent.stop()
        _agent = None
