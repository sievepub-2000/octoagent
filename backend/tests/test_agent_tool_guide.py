import re

from src.utils import agent_tool_guide


def test_agent_tool_guide_has_stable_header(monkeypatch, tmp_path):
    guide_path = tmp_path / "copilot-instructions.md"
    monkeypatch.setattr(agent_tool_guide, "_guide_path", lambda: guide_path)

    agent_tool_guide.generate_agent_tool_guide()

    text = guide_path.read_text(encoding="utf-8")
    assert "- Generated from: current runtime capability snapshot" in text
    assert not re.search(r"Generated at: \\d{4}-\\d{2}-\\d{2}T", text)
