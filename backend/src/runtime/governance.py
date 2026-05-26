"""Runtime governance helpers for long-running OctoAgent processes."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import threading
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any

from src.runtime.config.paths import get_paths

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class _WorkerPoolState:
    limit: int
    semaphore: threading.BoundedSemaphore
    active: int = 0
    queued: int = 0
    completed: int = 0
    rejected: int = 0
    total_wait_seconds: float = 0.0


@dataclass(slots=True)
class RuntimeWorkerIsolationService:
    """Small in-process limiter for blocking tool/browser/model work."""

    _states: dict[str, _WorkerPoolState] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def __post_init__(self) -> None:
        defaults = {
            "model": _env_int("OCTO_WORKER_LIMIT_MODEL", 4),
            "browser": _env_int("OCTO_WORKER_LIMIT_BROWSER", 2),
            "system": _env_int("OCTO_WORKER_LIMIT_SYSTEM", 2),
            "research": _env_int("OCTO_WORKER_LIMIT_RESEARCH", 2),
            "tool": _env_int("OCTO_WORKER_LIMIT_TOOL", 4),
        }
        for kind, limit in defaults.items():
            self._states[kind] = _WorkerPoolState(
                limit=limit,
                semaphore=threading.BoundedSemaphore(limit),
            )

    def _state(self, kind: str) -> _WorkerPoolState:
        normalized = kind if kind in self._states else "tool"
        return self._states[normalized]

    @contextmanager
    def slot(self, kind: str) -> Iterator[None]:
        state = self._state(kind)
        started = time.monotonic()
        with self._lock:
            state.queued += 1
        state.semaphore.acquire()
        wait_seconds = time.monotonic() - started
        with self._lock:
            state.queued = max(0, state.queued - 1)
            state.active += 1
            state.total_wait_seconds += wait_seconds
        try:
            yield
        finally:
            with self._lock:
                state.active = max(0, state.active - 1)
                state.completed += 1
            state.semaphore.release()

    @asynccontextmanager
    async def async_slot(self, kind: str):
        state = self._state(kind)
        started = time.monotonic()
        with self._lock:
            state.queued += 1
        await asyncio.to_thread(state.semaphore.acquire)
        wait_seconds = time.monotonic() - started
        with self._lock:
            state.queued = max(0, state.queued - 1)
            state.active += 1
            state.total_wait_seconds += wait_seconds
        try:
            yield
        finally:
            with self._lock:
                state.active = max(0, state.active - 1)
                state.completed += 1
            state.semaphore.release()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            pools = {
                kind: {
                    "limit": state.limit,
                    "active": state.active,
                    "queued": state.queued,
                    "completed": state.completed,
                    "rejected": state.rejected,
                    "avg_wait_ms": round(
                        (state.total_wait_seconds / state.completed) * 1000,
                        3,
                    )
                    if state.completed
                    else 0.0,
                }
                for kind, state in self._states.items()
            }
        return {
            "pools": pools,
            "total_active": sum(pool["active"] for pool in pools.values()),
            "total_queued": sum(pool["queued"] for pool in pools.values()),
            "total_completed": sum(pool["completed"] for pool in pools.values()),
        }


_worker_isolation: RuntimeWorkerIsolationService | None = None


def get_runtime_worker_isolation() -> RuntimeWorkerIsolationService:
    global _worker_isolation
    if _worker_isolation is None:
        _worker_isolation = RuntimeWorkerIsolationService()
    return _worker_isolation


def _available_memory_gb() -> float | None:
    try:
        pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError):
        return None
    return round((pages * page_size) / (1024**3), 3)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return default


def _process_count() -> int | None:
    proc = "/proc"
    if not os.path.isdir(proc):
        return None
    try:
        return sum(1 for item in os.listdir(proc) if item.isdigit())
    except OSError:
        return None


def collect_runtime_governance_snapshot(
    *,
    event_loop_latency_ms: float | None = None,
) -> dict[str, Any]:
    paths = get_paths()
    disk = shutil.disk_usage(paths.base_dir)
    checkpoint_snapshot: dict[str, Any]
    try:
        from src.agents.runtime.workflow_contract import get_langgraph_workflow_contract_service

        checkpoint_snapshot = get_langgraph_workflow_contract_service().snapshot()
    except Exception as exc:  # pragma: no cover - diagnostic boundary
        checkpoint_snapshot = {"error": str(exc)}

    snapshot = {
        "memory": {
            "available_gb": _available_memory_gb(),
        },
        "disk": {
            "path": str(paths.base_dir),
            "total_gb": round(disk.total / (1024**3), 3),
            "used_gb": round(disk.used / (1024**3), 3),
            "free_gb": round(disk.free / (1024**3), 3),
            "used_percent": round((disk.used / disk.total) * 100, 2) if disk.total else 0.0,
        },
        "processes": {
            "host_process_count": _process_count(),
        },
        "worker_isolation": get_runtime_worker_isolation().snapshot(),
        "langgraph_contract": checkpoint_snapshot,
        "event_loop": {
            "latency_ms": event_loop_latency_ms,
        },
    }
    snapshot["alerts"] = evaluate_runtime_alerts(snapshot)
    return snapshot


async def collect_runtime_governance_snapshot_async() -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    started = loop.time()
    await asyncio.sleep(0)
    latency_ms = round((loop.time() - started) * 1000, 3)
    return collect_runtime_governance_snapshot(event_loop_latency_ms=latency_ms)


def evaluate_runtime_alerts(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Evaluate long-running runtime thresholds for doctor/WebUI surfaces."""

    thresholds = {
        "min_memory_gb": _env_float("OCTO_ALERT_MIN_MEMORY_GB", 2.0),
        "min_disk_free_gb": _env_float("OCTO_ALERT_MIN_DISK_FREE_GB", 2.0),
        "max_disk_used_percent": _env_float("OCTO_ALERT_MAX_DISK_USED_PERCENT", 92.0),
        "max_event_loop_latency_ms": _env_float("OCTO_ALERT_MAX_EVENT_LOOP_LATENCY_MS", 100.0),
        "max_queue_depth": _env_float("OCTO_ALERT_MAX_QUEUE_DEPTH", 0.0),
        "max_checkpoint_count": _env_float("OCTO_ALERT_MAX_CHECKPOINT_COUNT", 1000.0),
        "max_active_runs": _env_float("OCTO_ALERT_MAX_ACTIVE_RUNS", 20.0),
    }
    alerts: list[dict[str, Any]] = []

    memory = snapshot.get("memory") if isinstance(snapshot.get("memory"), dict) else {}
    disk = snapshot.get("disk") if isinstance(snapshot.get("disk"), dict) else {}
    worker = snapshot.get("worker_isolation") if isinstance(snapshot.get("worker_isolation"), dict) else {}
    contract = snapshot.get("langgraph_contract") if isinstance(snapshot.get("langgraph_contract"), dict) else {}
    event_loop = snapshot.get("event_loop") if isinstance(snapshot.get("event_loop"), dict) else {}

    def add_alert(code: str, severity: str, message: str, value: Any, threshold: Any) -> None:
        alerts.append(
            {
                "code": code,
                "severity": severity,
                "message": message,
                "value": value,
                "threshold": threshold,
            }
        )

    available_gb = memory.get("available_gb")
    if isinstance(available_gb, (int, float)) and available_gb < thresholds["min_memory_gb"]:
        add_alert(
            "memory.low",
            "warning",
            "Available memory is below the long-running task floor.",
            available_gb,
            thresholds["min_memory_gb"],
        )

    free_gb = disk.get("free_gb")
    if isinstance(free_gb, (int, float)) and free_gb < thresholds["min_disk_free_gb"]:
        add_alert("disk.free_low", "critical", "Runtime disk free space is below threshold.", free_gb, thresholds["min_disk_free_gb"])
    used_percent = disk.get("used_percent")
    if isinstance(used_percent, (int, float)) and used_percent > thresholds["max_disk_used_percent"]:
        add_alert("disk.used_high", "warning", "Runtime disk usage is above threshold.", used_percent, thresholds["max_disk_used_percent"])

    queue_depth = worker.get("total_queued")
    if isinstance(queue_depth, (int, float)) and queue_depth > thresholds["max_queue_depth"]:
        add_alert("worker.queue_depth", "warning", "Worker queue depth is above steady-state target.", queue_depth, thresholds["max_queue_depth"])

    checkpoint_count = contract.get("checkpoint_count")
    if isinstance(checkpoint_count, (int, float)) and checkpoint_count > thresholds["max_checkpoint_count"]:
        add_alert("checkpoint.count_high", "warning", "Checkpoint count is above retention target.", checkpoint_count, thresholds["max_checkpoint_count"])
    active_runs = contract.get("active_runs")
    if isinstance(active_runs, (int, float)) and active_runs > thresholds["max_active_runs"]:
        add_alert("langgraph.active_runs_high", "warning", "Active LangGraph runs exceed concurrency target.", active_runs, thresholds["max_active_runs"])

    latency_ms = event_loop.get("latency_ms")
    if isinstance(latency_ms, (int, float)) and latency_ms > thresholds["max_event_loop_latency_ms"]:
        add_alert("event_loop.latency_high", "warning", "Event loop latency is above threshold.", latency_ms, thresholds["max_event_loop_latency_ms"])

    return alerts


class RuntimeMaintenanceScheduler:
    """Periodic maintenance for query cache and LangGraph contract retention."""

    def __init__(
        self,
        *,
        interval_seconds: int | None = None,
        max_checkpoints_per_thread: int | None = None,
        max_runs_per_thread: int | None = None,
    ) -> None:
        self.interval_seconds = max(
            60,
            interval_seconds or _env_int("OCTO_RUNTIME_MAINTENANCE_INTERVAL_SECONDS", 900),
        )
        self.max_checkpoints_per_thread = max_checkpoints_per_thread or _env_int(
            "OCTO_RUNTIME_MAX_CHECKPOINTS_PER_THREAD",
            20,
        )
        self.max_runs_per_thread = max_runs_per_thread or _env_int(
            "OCTO_RUNTIME_MAX_RUNS_PER_THREAD",
            100,
        )
        self.max_running_run_age_seconds = _env_int(
            "OCTO_RUNTIME_MAX_RUNNING_RUN_AGE_SECONDS",
            3600,
        )
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._last_run: dict[str, Any] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def last_run(self) -> dict[str, Any] | None:
        return self._last_run

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "interval_seconds": self.interval_seconds,
            "max_checkpoints_per_thread": self.max_checkpoints_per_thread,
            "max_runs_per_thread": self.max_runs_per_thread,
            "max_running_run_age_seconds": self.max_running_run_age_seconds,
            "last_run": self._last_run,
        }

    def start(self) -> None:
        if self.running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._loop(), name="runtime-maintenance-scheduler")

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            await asyncio.wait([self._task], timeout=10)
        self._task = None
        self._stop_event = None

    async def _loop(self) -> None:
        if self._stop_event is None:
            return
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                logger.warning("Runtime maintenance pass failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                continue

    def run_once(self) -> dict[str, Any]:
        from src.agents.runtime import get_langgraph_workflow_contract_service
        from src.runtime.artifact_lifecycle import run_artifact_lifecycle
        from src.storage.query import get_query_engine_service
        from src.storage.workflow import utc_now

        query = get_query_engine_service().run_maintenance(created_at=utc_now())
        contract_service = get_langgraph_workflow_contract_service()
        stale_runs = contract_service.recover_stale_running_runs(
            max_age_seconds=self.max_running_run_age_seconds,
        )
        contract = contract_service.prune(
            max_checkpoints_per_thread=self.max_checkpoints_per_thread,
            max_runs_per_thread=self.max_runs_per_thread,
        )
        artifact_lifecycle = run_artifact_lifecycle()
        self._last_run = {
            "ran_at": utc_now(),
            "query_engine": query,
            "langgraph_contract": contract,
            "langgraph_stale_runs": stale_runs,
            "artifact_lifecycle": artifact_lifecycle,
        }
        return self._last_run


_maintenance_scheduler: RuntimeMaintenanceScheduler | None = None


def get_runtime_maintenance_scheduler() -> RuntimeMaintenanceScheduler:
    global _maintenance_scheduler
    if _maintenance_scheduler is None:
        _maintenance_scheduler = RuntimeMaintenanceScheduler()
    return _maintenance_scheduler
