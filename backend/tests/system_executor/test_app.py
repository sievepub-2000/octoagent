from __future__ import annotations

from fastapi.testclient import TestClient

from src.system_executor import app as executor_app


class _Result:
    returncode = 0
    stdout = "ok"
    stderr = ""


def test_execute_requires_bearer_token_and_accepts_configured_token(monkeypatch) -> None:
    token = "system-executor-test-token-000000000000"
    monkeypatch.setenv("OCTOAGENT_SYSTEM_EXECUTOR_TOKEN", token)
    monkeypatch.setattr(
        executor_app,
        "_execute_on_host",
        lambda request: {
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
            "duration_ms": 0.1,
            "cwd": request.cwd,
        },
    )
    client = TestClient(executor_app.app)
    payload = {"command": "true", "cwd": "/", "timeout_seconds": 5}

    assert client.post("/execute", json=payload).status_code == 401
    response = client.post(
        "/execute",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["stdout"] == "ok"


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
