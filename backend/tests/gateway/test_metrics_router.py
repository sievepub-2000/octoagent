from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from src.gateway.routers import metrics


def test_memory_health_offloads_blocking_store_scan(monkeypatch) -> None:
    calls: list[object] = []

    async def fake_to_thread(function):
        calls.append(function)
        return {"documents": 2, "pending": 1}

    fake_memory = SimpleNamespace(stats=lambda: {})
    monkeypatch.setitem(
        sys.modules,
        "src.harness.memory",
        SimpleNamespace(get_harness_memory=lambda: fake_memory),
    )
    monkeypatch.setattr(metrics.asyncio, "to_thread", fake_to_thread)

    response = asyncio.run(metrics.memory_health())

    assert len(calls) == 1
    assert response.store_stats == {"documents": 2, "pending": 1}
    assert response.queue_stats == {"pending_index": 1}
