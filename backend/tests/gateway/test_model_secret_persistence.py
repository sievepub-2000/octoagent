import asyncio
import os
import threading

import pytest
from fastapi import HTTPException

from src.gateway.routers import models


def test_model_mutation_runs_outside_event_loop(monkeypatch) -> None:
    caller_thread = threading.get_ident()
    worker_thread: int | None = None
    expected = object()

    def fake_create(_request):
        nonlocal worker_thread
        worker_thread = threading.get_ident()
        return expected

    monkeypatch.setattr(models, "_create_model_in_config", fake_create)
    request = models.ModelCreateRequest(name="audit-model", model="audit/model")
    result = asyncio.run(models.create_model(request))

    assert result is expected
    assert worker_thread is not None
    assert worker_thread != caller_thread


def test_managed_secret_path_can_be_explicitly_configured(monkeypatch, tmp_path):
    managed_path = tmp_path / "runtime" / "secrets" / "models.env"
    monkeypatch.setenv("OCTOAGENT_MANAGED_SECRETS_FILE", str(managed_path))

    assert models._project_dotenv_path() == managed_path.resolve()


def test_raw_model_key_is_stored_in_dotenv_and_referenced(monkeypatch, tmp_path):
    dotenv_path = tmp_path / ".env"
    monkeypatch.setattr(models, "_project_dotenv_path", lambda: dotenv_path)

    payload = models._normalize_model_payload(
        {
            "name": "commercial-model",
            "model": "provider/model",
            "api_key": "secret-value",
        },
        existing_model_names=set(),
    )

    env_name = "OCTOAGENT_MODEL_COMMERCIAL_MODEL_API_KEY"
    assert payload["api_key"] == "$" + env_name
    assert dotenv_path.read_text(encoding="utf-8").strip() == f"{env_name}=secret-value"
    assert os.environ[env_name] == "secret-value"
    monkeypatch.delenv(env_name)


def test_existing_env_reference_and_local_no_auth_sentinel_are_preserved():
    referenced = models._normalize_model_payload(
        {"name": "cloud", "model": "provider/model", "api_key": "$EXISTING_KEY"},
        existing_model_names=set(),
    )
    local = models._normalize_model_payload(
        {"name": "local", "model": "local-model", "api_key": "none"},
        existing_model_names=set(),
    )

    assert referenced["api_key"] == "$EXISTING_KEY"
    assert local["api_key"] == "none"


def test_google_api_key_is_normalized_to_provider_parameter(monkeypatch, tmp_path):
    monkeypatch.setattr(models, "_project_dotenv_path", lambda: tmp_path / ".env")

    payload = models._normalize_model_payload(
        {
            "name": "gemini",
            "model": "gemini-model",
            "interface_type": "google_genai",
            "api_key": "google-secret",
        },
        existing_model_names=set(),
    )

    assert "api_key" not in payload
    assert payload["google_api_key"] == "$OCTOAGENT_MODEL_GEMINI_API_KEY"
    monkeypatch.delenv("OCTOAGENT_MODEL_GEMINI_API_KEY")


def test_raw_model_key_rejects_line_breaks():
    with pytest.raises(HTTPException, match="cannot contain line breaks"):
        models._normalize_model_payload(
            {"name": "unsafe", "model": "provider/model", "api_key": "first\nSECOND=value"},
            existing_model_names=set(),
        )
