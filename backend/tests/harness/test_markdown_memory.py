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
    extracted = tmp_path / "thread-1" / f"{result['run_id']}.memory.md"
    assert "deployments require real tests" in raw.read_text(encoding="utf-8")
    assert "run lifecycle and permission tests" in extracted.read_text(encoding="utf-8")


def test_compaction_keeps_goal_and_outcome_without_keywords() -> None:
    summary = HarnessMemory._compact(
        [
            ("User", "Build a small calendar."),
            ("Assistant", "The calendar was created and its tests pass."),
        ]
    )

    assert "user goal: Build a small calendar." in summary
    assert "outcome: The calendar was created and its tests pass." in summary
