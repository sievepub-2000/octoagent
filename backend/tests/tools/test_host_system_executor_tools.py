"""System-scoped host tools must cross the authenticated executor seam."""

from __future__ import annotations

import json

from src.tools.builtins import system_ops_tools


def test_host_file_manage_routes_relative_paths_through_executor(monkeypatch) -> None:
    calls: list[tuple[str, str, int]] = []

    def fake_run(command: str, *, cwd: str, timeout: int = 120) -> dict[str, object]:
        calls.append((command, cwd, timeout))
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setenv("OCTOAGENT_HOST_REPO_ROOT", "/srv/octoagent")
    monkeypatch.setattr(system_ops_tools, "_run_host_shell", fake_run)

    result = json.loads(
        system_ops_tools.host_file_manage_tool.invoke(
            {"operation": "write", "path": "tmp/result.txt", "content": "hello\n"}
        )
    )

    assert result["ok"] is True
    assert result["path"] == "/srv/octoagent/tmp/result.txt"
    assert calls and calls[0][1:] == ("/", 120)
    assert "base64 -d" in calls[0][0]
    assert "/srv/octoagent/tmp/result.txt" in calls[0][0]


def test_host_file_read_returns_executor_stdout(monkeypatch) -> None:
    monkeypatch.setattr(
        system_ops_tools,
        "_run_host_shell",
        lambda command, *, cwd, timeout=120: {"exit_code": 0, "stdout": "host-data", "stderr": ""},
    )

    result = json.loads(
        system_ops_tools.host_file_manage_tool.invoke({"operation": "read", "path": "/etc/hostname"})
    )

    assert result["ok"] is True
    assert result["content"] == "host-data"
    assert result["path"] == "/etc/hostname"
