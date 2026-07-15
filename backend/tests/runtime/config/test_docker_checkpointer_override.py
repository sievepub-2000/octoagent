from src.runtime.config.app_config import AppConfigLoader


def test_explicit_docker_checkpointer_dsn_overrides_host_config(monkeypatch):
    monkeypatch.setenv(
        "OCTOAGENT_CHECKPOINTER_DSN",
        "postgresql://octoagent:secret@postgres:5432/octoagent?sslmode=disable",
    )

    resolved = AppConfigLoader().resolve_config_data(
        {
            "models": [],
            "checkpointer": {
                "type": "sqlite",
                "connection_string": "checkpoints.db",
            },
        }
    )

    assert resolved["checkpointer"] == {
        "type": "postgres",
        "connection_string": "postgresql://octoagent:secret@postgres:5432/octoagent?sslmode=disable",
    }


def test_checkpointer_config_is_unchanged_without_override(monkeypatch):
    monkeypatch.delenv("OCTOAGENT_CHECKPOINTER_DSN", raising=False)

    resolved = AppConfigLoader().resolve_config_data(
        {
            "models": [],
            "checkpointer": {
                "type": "sqlite",
                "connection_string": "checkpoints.db",
            },
        }
    )

    assert resolved["checkpointer"]["type"] == "sqlite"
