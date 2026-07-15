from __future__ import annotations

from src.gateway.routers import module_status


def test_system_overview_reuses_short_lived_snapshot(monkeypatch) -> None:
    snapshot = {"overall": "ok"}
    calls = 0

    def build():
        nonlocal calls
        calls += 1
        return snapshot

    monkeypatch.setattr(module_status, "_build_system_overview", build)
    monkeypatch.setattr(module_status, "_overview_cache", (0.0, None))

    assert module_status.system_overview() is snapshot
    assert module_status.system_overview() is snapshot
    assert calls == 1


def test_system_overview_cpu_sampling_is_nonblocking(monkeypatch) -> None:
    class Usage:
        percent = 10.0
        used = 1
        total = 2

    intervals: list[float | None] = []
    monkeypatch.setattr(module_status.psutil, "virtual_memory", Usage)
    monkeypatch.setattr(module_status.psutil, "disk_usage", lambda _: Usage)
    monkeypatch.setattr(module_status.psutil, "cpu_percent", lambda interval: intervals.append(interval) or 3.0)
    monkeypatch.setattr(module_status.os, "getloadavg", lambda: (0.1, 0.2, 0.3), raising=False)
    monkeypatch.setattr(module_status, "_service_status", lambda name: {"name": name, "status": "active"})
    monkeypatch.setattr(module_status, "_thermal_sensors", lambda: [])
    monkeypatch.setattr(module_status, "_gpu_status", lambda: None)
    monkeypatch.setattr(module_status, "_command_output", lambda _: "")

    result = module_status._build_system_overview()

    assert result["cpu"]["percent"] == 3.0
    assert intervals == [None]
