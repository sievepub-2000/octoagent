from __future__ import annotations

import json

from src.tools.builtins import system_extra_tools


def test_docker_tools_use_the_system_executor(monkeypatch) -> None:
    calls: list[tuple[str, str, int]] = []

    def run_host_shell(command: str, *, cwd: str, timeout: int) -> dict[str, object]:
        calls.append((command, cwd, timeout))
        return {"exit_code": 0, "stdout": "ok", "stderr": ""}

    monkeypatch.setenv("OCTOAGENT_HOST_REPO_ROOT", "/srv/octoagent")
    monkeypatch.setattr(system_extra_tools, "_run_host_shell", run_host_shell)

    result = json.loads(system_extra_tools.docker_ps_tool.invoke({"all_containers": True}))

    assert result["result"]["exit_code"] == 0
    assert calls == [("docker ps --all --format json", "/srv/octoagent", 20)]


def test_docker_compose_paths_are_translated_to_the_host(monkeypatch) -> None:
    calls: list[tuple[str, str, int]] = []

    def run_host_shell(command: str, *, cwd: str, timeout: int) -> dict[str, object]:
        calls.append((command, cwd, timeout))
        return {"exit_code": 0, "stdout": "valid", "stderr": ""}

    monkeypatch.setenv("OCTOAGENT_HOST_REPO_ROOT", "/srv/octoagent")
    monkeypatch.setattr(system_extra_tools, "_run_host_shell", run_host_shell)

    result = json.loads(
        system_extra_tools.docker_compose_plan_tool.invoke(
            {"compose_file": "compose.yaml", "project_name": "audit"}
        )
    )

    assert result["result"]["exit_code"] == 0
    assert calls == [
        (
            "docker compose -p audit -f /srv/octoagent/compose.yaml config",
            "/srv/octoagent",
            60,
        )
    ]
