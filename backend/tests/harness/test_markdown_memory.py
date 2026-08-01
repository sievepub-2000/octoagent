from __future__ import annotations

from types import SimpleNamespace

from src.harness.memory import HarnessMemory


def test_markdown_is_durable_when_vector_index_is_pending(tmp_path, monkeypatch) -> None:
    memory = HarnessMemory(root=tmp_path)
    monkeypatch.setattr(memory, "_index_source", lambda _path: False)

    result = memory.capture(
        thread_id="thread-1",
        messages=[
            SimpleNamespace(type="human", content="Remember that deployments require real tests."),
            SimpleNamespace(type="ai", content="Decision: run lifecycle and permission tests before push."),
        ],
        agent_name="lead_agent",
    )

    assert result["status"] == "pending_index"
    raw = tmp_path / "thread-1" / f"{result['run_id']}.raw.md"
    extracted = tmp_path / "thread-1" / "current.memory.md"
    assert "deployments require real tests" in raw.read_text(encoding="utf-8")
    assert "run lifecycle and permission tests" in extracted.read_text(encoding="utf-8")


def test_capture_keeps_one_vector_source_per_thread(tmp_path, monkeypatch) -> None:
    memory = HarnessMemory(root=tmp_path)
    monkeypatch.setattr(memory, "_index_source", lambda _path: True)
    messages = [
        SimpleNamespace(type="human", content="Remember the production permission contract."),
        SimpleNamespace(type="ai", content="Decision: permissions are enforced on the server."),
    ]

    first = memory.capture(thread_id="thread-1", messages=messages)
    second = memory.capture(thread_id="thread-1", messages=messages)

    assert first["memory_path"] == second["memory_path"]
    assert len(list((tmp_path / "thread-1").glob("*.memory.md"))) == 1
    assert len(list((tmp_path / "thread-1").glob("*.raw.md"))) == 2


def test_initialize_prunes_vector_rows_without_markdown_sources(tmp_path, monkeypatch) -> None:
    memory = HarnessMemory(root=tmp_path)
    source = tmp_path / "thread-1" / "current.memory.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Extracted memory\n\n- durable fact\n", encoding="utf-8")
    seen: dict[str, object] = {}
    monkeypatch.setattr(memory, "_ensure_schema", lambda: None)
    monkeypatch.setattr(memory, "_index_sources", lambda sources: seen.setdefault("indexed", sources) and 1)
    monkeypatch.setattr(memory, "_prune_missing_sources", lambda sources: seen.setdefault("pruned", sources) and 2)
    monkeypatch.setattr(memory, "stats", lambda: {"healthy": True})

    report = memory.initialize()

    assert report["indexed_on_startup"] == 1
    assert report["pruned_on_startup"] == 2
    assert seen["indexed"] == [source]
    assert seen["pruned"] == [source]


def test_compaction_keeps_goal_and_outcome_without_keywords() -> None:
    summary = HarnessMemory._compact(
        [
            ("User", "Build a small calendar."),
            ("Assistant", "The calendar was created and its tests pass."),
        ]
    )

    assert "user goal: Build a small calendar." in summary
    assert "outcome: The calendar was created and its tests pass." in summary
