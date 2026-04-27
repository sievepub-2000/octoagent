import json

from src.agents.memory.system_rag_store import default_system_memory_db_path
from src.agents.memory.updater import _get_memory_file_path
from src.config.memory_config import MemoryConfig, set_memory_config


def test_default_system_memory_db_path_uses_runtime_root(monkeypatch, tmp_path):
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

    assert default_system_memory_db_path() == workspace / "runtime" / "system_memory.duckdb"


def test_memory_file_defaults_to_workspace_default(monkeypatch, tmp_path):
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
    set_memory_config(MemoryConfig(storage_path=""))

    try:
        assert _get_memory_file_path() == workspace / "default" / "memory.json"
        assert _get_memory_file_path("ExampleAgent") == workspace / "default" / "agents" / "exampleagent" / "memory.json"
    finally:
        set_memory_config(MemoryConfig())
