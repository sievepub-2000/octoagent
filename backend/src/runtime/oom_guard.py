"""Host memory OOM guard for long-running agent work.

This is the one hard execution guard: when host memory reaches the cleanup
threshold we release process memory; when it reaches the stop threshold we stop
currently running task workspaces and cancel busy LangGraph runs.
"""

from __future__ import annotations

import asyncio
import ctypes
import gc
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_CLEANUP_PERCENT = 85.0
DEFAULT_WARN_PERCENT = 70.0
DEFAULT_STOP_PERCENT = 90.0


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class MemoryPressureSnapshot:
    used_percent: float
    available_gb: float | None
    total_gb: float | None
    cpu_percent: float | None
    cleanup_threshold_percent: float = DEFAULT_CLEANUP_PERCENT
    stop_threshold_percent: float = DEFAULT_STOP_PERCENT
    captured_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_memory_pressure_snapshot(
    *,
    cleanup_threshold_percent: float = DEFAULT_CLEANUP_PERCENT,
    stop_threshold_percent: float = DEFAULT_STOP_PERCENT,
) -> MemoryPressureSnapshot:
    try:
        import psutil

        memory = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.0)
        return MemoryPressureSnapshot(
            used_percent=float(memory.percent),
            available_gb=float(memory.available) / (1024**3),
            total_gb=float(memory.total) / (1024**3),
            cpu_percent=float(cpu),
            cleanup_threshold_percent=cleanup_threshold_percent,
            stop_threshold_percent=stop_threshold_percent,
            captured_at=datetime.now(UTC).isoformat(),
        )
    except Exception:
        logger.exception("OOMGuard: failed to read psutil memory snapshot")
        return MemoryPressureSnapshot(
            used_percent=0.0,
            available_gb=None,
            total_gb=None,
            cpu_percent=None,
            cleanup_threshold_percent=cleanup_threshold_percent,
            stop_threshold_percent=stop_threshold_percent,
            captured_at=datetime.now(UTC).isoformat(),
        )


def _malloc_trim() -> bool:
    if os.name != "posix":
        return False
    try:
        libc = ctypes.CDLL("libc.so.6")
        return bool(libc.malloc_trim(0))
    except Exception:
        return False


def cleanup_memory(snapshot: MemoryPressureSnapshot, *, reason: str) -> dict[str, Any]:
    collected = gc.collect()
    malloc_trimmed = _malloc_trim()
    memory_cleanup: dict[str, Any] | None = None
    try:
        from src.agents.memory.cleanup import get_cleanup_scheduler

        scheduler = get_cleanup_scheduler()
        if scheduler is not None and hasattr(scheduler, "_cleanup"):
            memory_cleanup = scheduler._cleanup()  # noqa: SLF001
    except Exception:
        logger.exception("OOMGuard: memory cleanup scheduler run failed")

    report = {
        "reason": reason,
        "snapshot": snapshot.to_dict(),
        "gc_collected": collected,
        "malloc_trimmed": malloc_trimmed,
        "memory_cleanup": memory_cleanup,
        "created_at": datetime.now(UTC).isoformat(),
    }
    logger.warning("OOMGuard cleanup: %s", report)
    return report


def _hardware_status_message(snapshot: MemoryPressureSnapshot) -> str:
    available = "unknown" if snapshot.available_gb is None else f"{snapshot.available_gb:.1f} GiB"
    total = "unknown" if snapshot.total_gb is None else f"{snapshot.total_gb:.1f} GiB"
    cpu = "unknown" if snapshot.cpu_percent is None else f"{snapshot.cpu_percent:.1f}%"
    return (
        "内存 OOM 保护已触发硬停止："
        f"当前内存使用率 {snapshot.used_percent:.1f}%（阈值 {snapshot.stop_threshold_percent:.0f}%），"
        f"可用内存 {available} / 总内存 {total}，CPU {cpu}。"
        "系统已停止当前运行任务以保护主机；请释放内存或扩容后再恢复执行。"
    )


def terminate_running_task_workspaces(snapshot: MemoryPressureSnapshot) -> dict[str, Any]:
    from src.agents.core.service import get_agent_core_service
    from src.storage.task_workspaces.service import get_task_workspace_service

    service = get_task_workspace_service()
    agent_core = get_agent_core_service()
    stopped: list[str] = []
    message = _hardware_status_message(snapshot)
    for workspace in service.list_workspaces():
        if workspace.status not in {"queued", "running", "paused"}:
            continue
        try:
            service.merge_workspace_metadata(
                workspace.task_id,
                oom_guard={
                    "action": "hard_stop",
                    "snapshot": snapshot.to_dict(),
                    "message": message,
                    "stopped_at": datetime.now(UTC).isoformat(),
                },
            )
            agent_core.terminate_workspace_execution(workspace.task_id, task_service=service)
            if hasattr(service, "_append_run_log"):
                service._append_run_log(workspace.task_id, "OOM guard hard stop", message)  # noqa: SLF001
            stopped.append(workspace.task_id)
        except Exception:
            logger.exception("OOMGuard: failed to terminate workspace %s", workspace.task_id)
    return {"stopped_task_ids": stopped, "message": message}


async def cancel_busy_langgraph_runs(snapshot: MemoryPressureSnapshot) -> dict[str, Any]:
    base_url = os.getenv("OCTO_LANGGRAPH_BASE_URL", "http://localhost:19804").rstrip("/")
    cancelled: list[dict[str, str]] = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.post(f"{base_url}/threads/search", json={"status": "busy", "limit": 100})
            response.raise_for_status()
            threads = response.json() if isinstance(response.json(), list) else []
        except Exception:
            logger.exception("OOMGuard: failed to list busy LangGraph threads")
            return {"cancelled_runs": cancelled, "error": "list_busy_threads_failed"}
        for thread in threads:
            thread_id = thread.get("thread_id") or thread.get("id")
            if not thread_id:
                continue
            try:
                runs_response = await client.get(f"{base_url}/threads/{thread_id}/runs")
                runs_response.raise_for_status()
                runs = runs_response.json() if isinstance(runs_response.json(), list) else []
            except Exception:
                logger.exception("OOMGuard: failed to list runs for thread %s", thread_id)
                continue
            for run in runs:
                status = str(run.get("status") or "").lower()
                if status not in {"pending", "running"}:
                    continue
                run_id = run.get("run_id") or run.get("id")
                if not run_id:
                    continue
                try:
                    await client.post(
                        f"{base_url}/threads/{thread_id}/runs/{run_id}/cancel",
                        params={"wait": "false", "action": "interrupt"},
                    )
                    cancelled.append({"thread_id": str(thread_id), "run_id": str(run_id)})
                except Exception:
                    logger.exception("OOMGuard: failed to cancel run %s/%s", thread_id, run_id)
    logger.warning("OOMGuard cancelled LangGraph runs due to memory %.1f%%: %s", snapshot.used_percent, cancelled)
    return {"cancelled_runs": cancelled}


class OOMGuard:
    def __init__(self) -> None:
        self.warn_threshold_percent = _env_float("OCTO_OOM_WARN_MEM_PERCENT", DEFAULT_WARN_PERCENT)
        self.cleanup_threshold_percent = _env_float("OCTO_OOM_CLEANUP_MEM_PERCENT", DEFAULT_CLEANUP_PERCENT)
        self.stop_threshold_percent = _env_float("OCTO_OOM_STOP_MEM_PERCENT", DEFAULT_STOP_PERCENT)
        self.interval_seconds = _env_int("OCTO_OOM_GUARD_INTERVAL_SEC", 10)
        self.cleanup_cooldown_seconds = _env_int("OCTO_OOM_CLEANUP_COOLDOWN_SEC", 30)
        self.stop_cooldown_seconds = _env_int("OCTO_OOM_STOP_COOLDOWN_SEC", 30)
        self._last_cleanup_at = 0.0
        self._last_stop_at = 0.0

    async def check_once(self) -> dict[str, Any]:
        snapshot = get_memory_pressure_snapshot(
            cleanup_threshold_percent=self.cleanup_threshold_percent,
            stop_threshold_percent=self.stop_threshold_percent,
        )
        report: dict[str, Any] = {"snapshot": snapshot.to_dict(), "action": "none"}
        now = time.monotonic()
        if snapshot.used_percent >= self.stop_threshold_percent:
            if now - self._last_stop_at < self.stop_cooldown_seconds:
                report["action"] = "hard_stop_cooldown"
                return report
            self._last_stop_at = now
            report["action"] = "hard_stop"
            report["cleanup"] = cleanup_memory(snapshot, reason="oom_stop_threshold")
            report["langgraph"] = await cancel_busy_langgraph_runs(snapshot)
            report["tasks"] = terminate_running_task_workspaces(snapshot)
            logger.critical("OOMGuard hard stop report: %s", report)
            return report
        if snapshot.used_percent >= self.cleanup_threshold_percent:
            if now - self._last_cleanup_at < self.cleanup_cooldown_seconds:
                report["action"] = "cleanup_cooldown"
                return report
            self._last_cleanup_at = now
            report["action"] = "cleanup"
            report["cleanup"] = cleanup_memory(snapshot, reason="oom_cleanup_threshold")
            return report
        if hasattr(self, "warn_threshold_percent") and snapshot.used_percent >= self.warn_threshold_percent:
            report["action"] = "warn"
            report["warning"] = {
                "message": f"Memory at {snapshot.used_percent:.1f}% (warning threshold {self.warn_threshold_percent:.0f}%)",
                "snapshot": snapshot.to_dict(),
            }
            logger.info("OOMGuard warning: memory at %.1f%% (>= %.0f%% warn threshold)",
                        snapshot.used_percent, self.warn_threshold_percent)
        return report

    async def run_forever(self) -> None:
        logger.info(
            "OOMGuard started (cleanup>=%.0f%%, stop>=%.0f%%, interval=%ss)",
            self.cleanup_threshold_percent,
            self.stop_threshold_percent,
            self.interval_seconds,
        )
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("OOMGuard loop crashed")
            await asyncio.sleep(self.interval_seconds)


def start_oom_guard_task(app) -> None:
    guard = OOMGuard()
    app.state.oom_guard = guard
    app.state.oom_guard_task = asyncio.create_task(guard.run_forever(), name="octoagent-oom-guard")


async def stop_oom_guard_task(app) -> None:
    task = getattr(app.state, "oom_guard_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    app.state.oom_guard_task = None
    app.state.oom_guard = None


__all__ = [
    "DEFAULT_CLEANUP_PERCENT",
    "DEFAULT_STOP_PERCENT",
    "MemoryPressureSnapshot",
    "OOMGuard",
    "cancel_busy_langgraph_runs",
    "cleanup_memory",
    "get_memory_pressure_snapshot",
    "start_oom_guard_task",
    "stop_oom_guard_task",
    "terminate_running_task_workspaces",
]