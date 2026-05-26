from __future__ import annotations

from src.agents.memory.letta_memory import LettaMemoryService
from src.agents.memory.prompt import format_memory_for_injection
from src.agents.memory.system_rag_store import validate_system_memory_namespace


def test_memory_blocks_are_saved_and_injected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OCTO_AGENT_HOME", str(tmp_path))
    service = LettaMemoryService()

    block = service.upsert_block("task_state", "Current task: repair streaming.", description="Track active task state.")

    assert block.label == "task_state"
    assert "task_state" in service.format_blocks_context()
    injected = format_memory_for_injection({"memory_blocks": {"task_state": block.__dict__}})
    assert "<memory_blocks>" in injected
    assert "repair streaming" in injected


def test_read_only_memory_block_requires_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OCTO_AGENT_HOME", str(tmp_path))
    service = LettaMemoryService()

    service.upsert_block("policy", "Do not overwrite.", read_only=True)

    try:
        service.upsert_block("policy", "Overwrite")
    except PermissionError:
        pass
    else:
        raise AssertionError("read-only block update should fail")


def test_archival_namespace_is_valid() -> None:
    assert validate_system_memory_namespace("archival_memory") == "archival_memory"
