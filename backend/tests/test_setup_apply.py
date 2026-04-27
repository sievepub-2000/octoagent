import asyncio
import json

from src.gateway.routers import setup as setup_router
from src.gateway.routers.setup import ApplySetupRequest, apply_setup


def test_apply_setup_uses_persisted_workspace_when_workspace_path_is_blank(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    setup_state = tmp_path / "setup.json"
    setup_state.write_text(
        json.dumps({"workspace_path": str(workspace), "default_model": "old-model"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("OCTO_AGENT_SETUP_STATE_FILE", str(setup_state))
    monkeypatch.delenv("OCTO_AGENT_HOME", raising=False)

    response = asyncio.run(
        apply_setup(
            ApplySetupRequest(
                workspace_path="",
                default_model="gpt-oss-120b-free",
                sandbox_mode="local",
            )
        )
    )

    assert response.success is True
    assert response.workspace_path == str(workspace.resolve())
    assert (workspace / "runtime").is_dir()


def test_apply_setup_preserves_existing_workspace_after_stale_path_error(monkeypatch, tmp_path):
    stale_workspace = tmp_path / "stale-workspace"
    persisted_workspace = tmp_path / "persisted-workspace"
    setup_state = tmp_path / "setup.json"
    setup_state.write_text(
        json.dumps({"workspace_path": str(persisted_workspace), "default_model": "old-model"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("OCTO_AGENT_SETUP_STATE_FILE", str(setup_state))

    original_create = setup_router._create_workspace_dirs

    def create_workspace_dirs(path):
        if path == stale_workspace.resolve():
            raise PermissionError("stale path is not writable")
        return original_create(path)

    monkeypatch.setattr(setup_router, "_create_workspace_dirs", create_workspace_dirs)

    response = asyncio.run(
        apply_setup(
            ApplySetupRequest(
                workspace_path=str(stale_workspace),
                default_model="gpt-oss-120b-free",
                sandbox_mode="local",
                preserve_existing_workspace=True,
            )
        )
    )

    assert response.success is True
    assert response.workspace_path == str(persisted_workspace.resolve())
    assert (persisted_workspace / "runtime").is_dir()
