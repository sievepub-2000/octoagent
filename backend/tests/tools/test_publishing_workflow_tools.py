from __future__ import annotations

import json

from src.tools.builtins.publishing_workflow_tools import (
    PUBLISHING_WORKFLOW_TOOLS,
    human_approval_gate_tool,
    novel_project_store_tool,
    writestory_tool,
)


def _payload(result: str) -> dict:
    return json.loads(result)


def test_requested_tool_names_are_registered() -> None:
    names = {tool.name for tool in PUBLISHING_WORKFLOW_TOOLS}
    assert "browser_publisher" in names
    assert "publication_auditor" in names
    assert "human_approval_gate" in names
    assert "novel_project_store" in names
    assert "writestory" in names
    assert "chapter_writer" in names
    assert "chapter-drafter" in names
    assert "webnovel-write" in names


def test_human_approval_gate_requires_confirmation() -> None:
    payload = _payload(human_approval_gate_tool.invoke({"action": "publish", "risk_summary": "public post"}))
    assert payload["approved"] is False
    assert payload["error"] == "human_approval_required"


def test_writestory_creates_managed_assets(tmp_path, monkeypatch) -> None:
    import src.tools.builtins.publishing_workflow_tools as tools

    monkeypatch.setattr(tools, "_WRITING_ROOT", tmp_path / "writing-suite")
    init_payload = _payload(novel_project_store_tool.invoke({"operation": "init", "project_slug": "demo", "title": "Demo"}))
    assert init_payload["manifest"]["project_slug"] == "demo"

    story_payload = _payload(
        writestory_tool.invoke(
            {
                "project_slug": "demo",
                "brief": "A serialized story about an agent writing responsibly.",
                "genre": "web serial",
                "target_chapters": 2,
            }
        )
    )
    assert story_payload["next_tool"] == "chapter_drafter"
    assert (tmp_path / "writing-suite" / "projects" / "demo" / "story_bible.md").exists()
    assert (tmp_path / "writing-suite" / "projects" / "demo" / "outline.md").exists()
