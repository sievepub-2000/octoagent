from __future__ import annotations

import asyncio

from src.runtime.oom_guard import MemoryPressureSnapshot, OOMGuard


def _snapshot(percent: float) -> MemoryPressureSnapshot:
    return MemoryPressureSnapshot(
        used_percent=percent,
        available_gb=1.0,
        total_gb=10.0,
        cpu_percent=12.0,
        cleanup_threshold_percent=85.0,
        stop_threshold_percent=90.0,
        captured_at="2026-01-01T00:00:00+00:00",
    )


def test_oom_guard_cleans_at_85_without_stopping(monkeypatch):
    guard = OOMGuard()
    guard.cleanup_threshold_percent = 85.0
    guard.stop_threshold_percent = 90.0
    cleanup_calls: list[str] = []

    monkeypatch.setattr("src.runtime.oom_guard.get_memory_pressure_snapshot", lambda **_: _snapshot(86.0))
    monkeypatch.setattr("src.runtime.oom_guard.cleanup_memory", lambda snapshot, *, reason: cleanup_calls.append(reason) or {"reason": reason})

    async def _unexpected_cancel(snapshot):
        raise AssertionError("85% cleanup must not cancel LangGraph runs")

    monkeypatch.setattr("src.runtime.oom_guard.cancel_busy_langgraph_runs", _unexpected_cancel)
    monkeypatch.setattr("src.runtime.oom_guard.terminate_running_task_workspaces", lambda snapshot: (_ for _ in ()).throw(AssertionError("85% cleanup must not stop tasks")))

    report = asyncio.run(guard.check_once())

    assert report["action"] == "cleanup"
    assert cleanup_calls == ["oom_cleanup_threshold"]


def test_oom_guard_stops_at_90_and_reports_hardware(monkeypatch):
    guard = OOMGuard()
    guard.cleanup_threshold_percent = 85.0
    guard.stop_threshold_percent = 90.0

    monkeypatch.setattr("src.runtime.oom_guard.get_memory_pressure_snapshot", lambda **_: _snapshot(91.0))
    monkeypatch.setattr("src.runtime.oom_guard.cleanup_memory", lambda snapshot, *, reason: {"reason": reason, "snapshot": snapshot.to_dict()})

    async def _cancel(snapshot):
        return {"cancelled_runs": [{"thread_id": "t", "run_id": "r"}]}

    monkeypatch.setattr("src.runtime.oom_guard.cancel_busy_langgraph_runs", _cancel)
    monkeypatch.setattr(
        "src.runtime.oom_guard.terminate_running_task_workspaces",
        lambda snapshot: {"stopped_task_ids": ["task-1"], "message": "内存 OOM 保护已触发硬停止"},
    )

    report = asyncio.run(guard.check_once())

    assert report["action"] == "hard_stop"
    assert report["cleanup"]["reason"] == "oom_stop_threshold"
    assert report["langgraph"]["cancelled_runs"] == [{"thread_id": "t", "run_id": "r"}]
    assert report["tasks"]["stopped_task_ids"] == ["task-1"]
    assert "message" in report["tasks"]
