from __future__ import annotations

import asyncio

from src.gateway.routers import harness


def test_harness_snapshot_builds_outside_event_loop(monkeypatch) -> None:
    built_on_worker = False

    def fake_snapshot() -> dict:
        nonlocal built_on_worker
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            built_on_worker = True
        return {"module": "harness", "architecture": "agent-runtime+harness"}

    monkeypatch.setattr(harness, "_snapshot", fake_snapshot)
    result = asyncio.run(harness.get_harness_snapshot())

    assert result["module"] == "harness"
    assert built_on_worker is True
