from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers import system_update


def _client(monkeypatch):
    monkeypatch.setenv("OCTO_OPERATOR_TOKEN", "test-token")
    app = FastAPI()
    app.include_router(system_update.router)
    return TestClient(app)


def test_update_check_requires_operator_token(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/system/update/check")

    assert response.status_code == 403


def test_update_apply_requires_admin_token_before_side_effects(monkeypatch):
    client = _client(monkeypatch)

    response = client.post("/api/system/update/apply")

    assert response.status_code == 403


def test_update_auto_config_requires_admin_token(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/system/update/auto-config")

    assert response.status_code == 403


def test_update_check_accepts_operator_token(monkeypatch):
    client = _client(monkeypatch)

    async def fake_fetch_remote_version_info():
        return {"version": "2026.7.4", "sha": "deadbeef", "date": "", "message": ""}

    monkeypatch.setattr(system_update, "_fetch_remote_version_info", fake_fetch_remote_version_info)
    monkeypatch.setattr(system_update, "_read_current_version", lambda: "2026.7.4")

    response = client.get(
        "/api/system/update/check",
        headers={"X-OctoAgent-Operator-Token": "test-token", "X-OctoAgent-Operator-Role": "operator"},
    )

    assert response.status_code == 200
    assert response.json()["has_update"] is False
