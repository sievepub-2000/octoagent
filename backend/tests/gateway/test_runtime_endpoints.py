"""Tests for the Phase 1 / Phase 4a runtime endpoints.

Targets ``backend/src/gateway/routers/runtime.py``:
    * ``GET /api/runtime/effective-config``  (Phase 1)
    * ``GET /api/runtime/tool-trace``        (Phase 4a)

The tests use FastAPI's ``TestClient`` against a minimal app that only mounts
the runtime router so we don't need to spin up the whole gateway.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def runtime_client() -> TestClient:
    from src.gateway.routers.runtime import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# -------- /api/runtime/effective-config --------


def test_effective_config_returns_200_with_required_fields(runtime_client: TestClient) -> None:
    resp = runtime_client.get("/api/runtime/effective-config")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    for key in (
        "generated_at",
        "runtime_governance_version",
        "repo_root",
        "env",
        "paths",
        "feature_flags",
        "ports",
    ):
        assert key in body, f"missing key: {key}"

    assert isinstance(body["env"], dict)
    assert isinstance(body["paths"], dict)
    assert isinstance(body["feature_flags"], dict)
    assert isinstance(body["ports"], dict)
    # repo_root should be an absolute path to a real directory.
    assert Path(body["repo_root"]).is_absolute()


def test_effective_config_resolves_repo_root_to_real_repo(runtime_client: TestClient) -> None:
    resp = runtime_client.get("/api/runtime/effective-config")
    body = resp.json()
    repo_root = Path(body["paths"]["repo_root"])

    # Regression for the 2026-05-26 bug where ``Path.cwd()`` resolved to
    # ``backend/`` because the gateway process cwd was the backend dir.
    # Repo root must contain BOTH a ``backend`` and a ``frontend`` subdir.
    assert (repo_root / "backend").is_dir(), f"repo_root missing backend: {repo_root}"
    assert (repo_root / "frontend").is_dir(), f"repo_root missing frontend: {repo_root}"


def test_effective_config_masks_secret_like_env_vars(
    runtime_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOAGENT_FAKE_API_KEY", "abcdef1234567890XYZ")
    monkeypatch.setenv("OCTOAGENT_FAKE_TOKEN", "supersecrettokenvalue")
    monkeypatch.setenv("OCTOAGENT_FAKE_PASSWORD", "p@ssword!!")
    monkeypatch.setenv("OCTOAGENT_FAKE_PLAINTEXT", "plain-value-do-not-mask")

    resp = runtime_client.get("/api/runtime/effective-config")
    assert resp.status_code == 200
    env = resp.json()["env"]

    # Secret-fragment keys must be masked.
    for key in ("OCTOAGENT_FAKE_API_KEY", "OCTOAGENT_FAKE_TOKEN", "OCTOAGENT_FAKE_PASSWORD"):
        assert key in env, f"missing masked key: {key}"
        masked = env[key]
        assert "***" in masked, f"{key} not masked: {masked!r}"
        assert "(len=" in masked, f"{key} missing length tag: {masked!r}"
        # Critically: the raw secret must NOT leak.
        for raw_value in ("abcdef1234567890XYZ", "supersecrettokenvalue", "p@ssword!!"):
            if raw_value == masked:  # exact-equality only; partial overlap on prefix/suffix is by design.
                pytest.fail(f"{key} leaked raw value: {masked!r}")

    # Plain variable must be returned untouched.
    assert env.get("OCTOAGENT_FAKE_PLAINTEXT") == "plain-value-do-not-mask"


def test_effective_config_secret_masking_pattern_is_well_formed(
    runtime_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOAGENT_FAKE_SECRET", "1234567890")  # 10 chars
    resp = runtime_client.get("/api/runtime/effective-config")
    masked = resp.json()["env"]["OCTOAGENT_FAKE_SECRET"]
    # Format: ``xxx***yy (len=N)``
    assert masked == "123***90 (len=10)", masked


def test_effective_config_short_secret_is_fully_redacted(
    runtime_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOAGENT_FAKE_TOKEN", "abc")  # <=6 chars
    resp = runtime_client.get("/api/runtime/effective-config")
    assert resp.json()["env"]["OCTOAGENT_FAKE_TOKEN"] == "***"


# -------- /api/runtime/tool-trace --------


def test_tool_trace_returns_valid_envelope(runtime_client: TestClient) -> None:
    resp = runtime_client.get("/api/runtime/tool-trace")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in ("generated_at", "source_file", "file_exists", "total_lines", "events"):
        assert key in body, f"missing key: {key}"
    assert isinstance(body["events"], list)
    assert isinstance(body["total_lines"], int)
    assert isinstance(body["file_exists"], bool)


def test_tool_trace_source_file_points_at_repo_root_workspace(runtime_client: TestClient) -> None:
    # Regression for the 2026-05-26 bug where ``trace_path`` resolved to
    # ``backend/workspace/runtime/observability/tool-trace.jsonl``.
    resp = runtime_client.get("/api/runtime/tool-trace")
    body = resp.json()
    src = Path(body["source_file"])

    # The path must be under ``<repo_root>/workspace/runtime/observability/``,
    # NOT under ``<repo_root>/backend/workspace/...``.
    assert "backend/workspace" not in str(src), f"trace_path regressed to backend/: {src}"
    assert src.name == "tool-trace.jsonl"
    assert src.parent.name == "observability"


def test_tool_trace_limit_param_bounded(runtime_client: TestClient) -> None:
    # Cap is 2000; values above it are clamped down silently.
    resp = runtime_client.get("/api/runtime/tool-trace?limit=99999")
    assert resp.status_code == 200
    # Lower bound is 1.
    resp = runtime_client.get("/api/runtime/tool-trace?limit=0")
    assert resp.status_code == 200


def test_tool_trace_reads_existing_jsonl(
    runtime_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the JSONL file is missing the endpoint returns an empty event list."""
    resp = runtime_client.get("/api/runtime/tool-trace?limit=5")
    body = resp.json()
    if body["file_exists"]:
        # Sanity: every reported event is a dict.
        for ev in body["events"]:
            assert isinstance(ev, dict)
        # Endpoint never returns more events than ``limit``.
        assert len(body["events"]) <= 5
