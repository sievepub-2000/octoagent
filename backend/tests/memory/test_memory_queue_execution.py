from __future__ import annotations

from types import SimpleNamespace

from src.agents.memory.queue import MemoryUpdateQueue
from src.agents.memory.updater import MemoryUpdater


def test_queue_executes_async_memory_update(monkeypatch) -> None:
    calls: list[str] = []

    async def _update(self, messages, thread_id=None, agent_name=None, metadata=None):
        calls.append(str(thread_id))
        return True

    monkeypatch.setattr(MemoryUpdater, "update_memory", _update)
    queue = MemoryUpdateQueue()
    queue.add("thread-1", [SimpleNamespace(type="human", content="remember this")])
    queue.flush()

    assert calls == ["thread-1"]
    assert queue.pending_count == 0
    assert queue.is_processing is False
