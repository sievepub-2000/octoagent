from __future__ import annotations

from src.system_executor import app as executor_app


class _Result:
    returncode = 0
    stdout = "ok"
    stderr = ""


def test_host_helper_inherits_proxy_environment(monkeypatch) -> None:
    captured: list[str] = []

    def fake_run(command, **_kwargs):
        captured.extend(command)
        return _Result()

    monkeypatch.setenv("HTTPS_PROXY", "http://host.docker.internal:7897")
    monkeypatch.setenv("NO_PROXY", "localhost,system-executor")
    monkeypatch.setattr(executor_app.socket, "gethostbyname", lambda _host: "172.17.0.1")
    monkeypatch.setattr(executor_app.subprocess, "run", fake_run)

    result = executor_app._execute_on_host(executor_app.ExecuteRequest(command="true", cwd="/"))

    assert result["exit_code"] == 0
    assert "--add-host=host.docker.internal:host-gateway" in captured
    assert "HTTPS_PROXY=http://172.17.0.1:7897" in captured
    assert "NO_PROXY=localhost,system-executor" in captured
    assert captured.index("--env") < captured.index("octoagent/backend:local")
