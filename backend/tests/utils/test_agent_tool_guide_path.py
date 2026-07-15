from src.utils.agent_tool_guide import get_agent_tool_guide_path


def test_tool_guide_path_can_use_writable_runtime_directory(monkeypatch, tmp_path) -> None:
    path = tmp_path / "runtime" / "system_tools" / "copilot-instructions.md"
    monkeypatch.setenv("OCTOAGENT_TOOL_GUIDE_PATH", str(path))

    assert get_agent_tool_guide_path() == path.resolve()
