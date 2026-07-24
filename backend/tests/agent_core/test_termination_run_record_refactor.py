"""Smoke tests for the refactor: central detector + run_id plumbing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.core import termination as termination_module
from src.agents.core.run_record_store import append_run_record, list_run_records


def test_public_continuation_detector_is_re_exported():
    assert hasattr(termination_module, "is_continuation_announcement")
    assert callable(termination_module.is_continuation_announcement)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Now let me check the file:", True),
        ("Task completed. Here is the summary of results.", False),
        ("", False),
        ("<tool_call>{}</tool_call>", True),
    ],
)
def test_central_detector_matches_legacy(text: str, expected: bool):
    assert termination_module.is_continuation_announcement(text) is expected


def test_append_run_record_persists_run_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Redirect the store path to a temp file by patching the bound name
    # used by run_record_store at module scope.
    from src.agents.core import run_record_store as rrs

    class _FakePaths:
        runtime_root = tmp_path

    monkeypatch.setattr(rrs, "get_paths", lambda: _FakePaths())

    stored = append_run_record(
        {"final_evaluation": {"status": "completed"}},
        thread_id="thread-x",
        agent_name="lead_agent",
        run_id="run-y",
    )
    assert stored["thread_id"] == "thread-x"
    assert stored["run_id"] == "run-y"
    assert stored["agent_name"] == "lead_agent"

    on_disk = (tmp_path / "run_records.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(on_disk) == 1
    parsed = json.loads(on_disk[0])
    assert parsed["run_id"] == "run-y"
    assert parsed["thread_id"] == "thread-x"

    records = list_run_records(limit=5, thread_id="thread-x")
    assert records and records[0]["run_id"] == "run-y"
