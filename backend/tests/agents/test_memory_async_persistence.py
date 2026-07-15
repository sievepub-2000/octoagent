from __future__ import annotations

import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

from src.agents.memory import updater as updater_module
from src.agents.memory.updater import MemoryUpdater, ensure_memory_schema


def test_memory_update_moves_filesystem_io_off_event_loop() -> None:
    save_threads: list[str] = []

    class FakeModel:
        async def ainvoke(self, _prompt: str):
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "user": {},
                        "history": {},
                        "newFacts": [
                            {
                                "content": "The memory writer must remain non-blocking.",
                                "category": "knowledge",
                                "confidence": 0.9,
                            }
                        ],
                        "factsToRemove": [],
                    }
                )
            )

    def save(_memory, _agent_name=None) -> bool:
        save_threads.append(threading.current_thread().name)
        return True

    with (
        patch.object(
            updater_module,
            "get_memory_config",
            lambda: SimpleNamespace(
                enabled=True,
                model_name="fake",
                fact_confidence_threshold=0.5,
                max_facts=100,
            ),
        ),
        patch.object(updater_module, "get_memory_data", lambda _agent_name=None: ensure_memory_schema({})),
        patch.object(MemoryUpdater, "_get_model", lambda _self: FakeModel()),
        patch.object(updater_module, "_save_memory_to_file", save),
    ):
        assert asyncio.run(
            MemoryUpdater().update_memory(
                [SimpleNamespace(type="human", content="remember this")],
                thread_id="thread-async-io",
            )
        )
    assert save_threads
    assert save_threads[0] != threading.current_thread().name


if __name__ == "__main__":
    test_memory_update_moves_filesystem_io_off_event_loop()
    print("memory-async-persistence-ok")
