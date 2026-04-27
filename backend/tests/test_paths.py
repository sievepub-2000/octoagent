import json
from pathlib import Path

from src.agents.checkpointer.provider import _resolve_sqlite_conn_str
from src.config.paths import Paths
from src.gateway.routers.setup import _save_workspace_env_state


def test_paths_ignore_missing_configured_workspace(monkeypatch, tmp_path):
    missing_workspace = tmp_path / "missing-workspace"
    setup_state = tmp_path / "setup.json"
    setup_state.write_text(
        json.dumps({"workspace_path": str(missing_workspace)}),
        encoding="utf-8",
    )

    monkeypatch.setenv("OCTO_AGENT_SETUP_STATE_FILE", str(setup_state))
    monkeypatch.delenv("OCTO_AGENT_HOME", raising=False)

    repo_root = Path(__file__).resolve().parents[2]

    assert Paths().base_dir == repo_root / "workspace"


def test_checkpointer_relative_path_resolves_inside_workspace(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "default").mkdir(parents=True)
    (workspace / "env").mkdir()
    (workspace / "runtime").mkdir()
    (workspace / "workflow").mkdir()
    setup_state = tmp_path / "setup.json"
    setup_state.write_text(
        json.dumps({"workspace_path": str(workspace)}),
        encoding="utf-8",
    )

    monkeypatch.setenv("OCTO_AGENT_SETUP_STATE_FILE", str(setup_state))
    monkeypatch.delenv("OCTO_AGENT_HOME", raising=False)

    assert _resolve_sqlite_conn_str("runtime/checkpoints.db") == str(workspace / "runtime" / "checkpoints.db")


def test_setup_workspace_snapshot_records_runtime_paths(tmp_path):
    workspace = tmp_path / "workspace"

    _save_workspace_env_state(
        workspace,
        default_model="test-model",
        sandbox_mode="local",
        directories_created=[],
    )

    payload = json.loads((workspace / "env" / "setup.json").read_text(encoding="utf-8"))

    assert payload["layout"]["runtime_dir"] == str(workspace / "runtime")
    assert payload["layout"]["checkpoints_path"] == str(workspace / "runtime" / "checkpoints.db")
    assert payload["layout"]["system_memory_path"] == str(workspace / "runtime" / "system_memory.duckdb")
    assert payload["layout"]["global_memory_path"] == str(workspace / "default" / "global_memory.json")
