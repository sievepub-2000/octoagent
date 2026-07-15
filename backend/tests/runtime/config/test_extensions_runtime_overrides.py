import json

from src.runtime.config.extensions_config import ExtensionsConfig


def test_container_runtime_overrides_preserve_mcp_metadata(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "filesystem": {
                        "command": "/host/mcp-server-filesystem",
                        "args": ["/host/workspace"],
                        "permissionScope": "directory",
                    },
                    "postgres": {
                        "command": "/host/mcp-server-postgres",
                        "args": ["postgresql://host-db"],
                        "permissionScope": "system",
                    },
                    "redis": {"command": "/host/mcp-server-redis", "args": ["redis://localhost:6379"]},
                    "openapi": {"command": "/host/openapi-mcp-server", "args": []},
                    "docker-compose": {"command": "/host/python", "args": ["-m", "src.tools.mcp.local_servers.compose"]},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OCTOAGENT_MCP_FILESYSTEM_BIN", "/app/mcp-server-filesystem")
    monkeypatch.setenv("OCTOAGENT_MCP_POSTGRES_BIN", "/app/mcp-server-postgres")
    monkeypatch.setenv("OCTOAGENT_MCP_REDIS_BIN", "/app/mcp-server-redis")
    monkeypatch.setenv("OCTOAGENT_MCP_OPENAPI_BIN", "/app/openapi-mcp-server")
    monkeypatch.setenv("OCTOAGENT_FILESYSTEM_ROOT", "/app")
    monkeypatch.setenv("OCTOAGENT_POSTGRES_SUPERUSER_DSN", "postgresql://container-db")
    monkeypatch.setenv("OCTOAGENT_REDIS_URL", "redis://redis:6379")
    monkeypatch.setenv("OCTOAGENT_PYTHON_BIN", "/app/backend/.venv/bin/python")
    monkeypatch.setenv("OCTOAGENT_GATEWAY_INTERNAL_URL", "http://gateway:19802")
    monkeypatch.setenv("OCTOAGENT_OPENAPI_SPEC_URL", "http://gateway:19802/openapi.json")

    config = ExtensionsConfig.from_file(str(config_path))

    assert config.mcp_servers["filesystem"].command == "/app/mcp-server-filesystem"
    assert config.mcp_servers["filesystem"].args == ["/app"]
    assert config.mcp_servers["filesystem"].permission_scope == "directory"
    assert config.mcp_servers["postgres"].args == ["postgresql://container-db"]
    assert config.mcp_servers["postgres"].permission_scope == "system"
    assert config.mcp_servers["redis"].args == ["redis://redis:6379"]
    assert config.mcp_servers["docker-compose"].command == "/app/backend/.venv/bin/python"
    assert config.mcp_servers["openapi"].args == [
        "--transport",
        "stdio",
        "--api-base-url",
        "http://gateway:19802",
        "--openapi-spec",
        "http://gateway:19802/openapi.json",
    ]


def test_runtime_overrides_are_opt_in(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"filesystem": {"command": "/host/server", "args": ["/host/root"]}}}),
        encoding="utf-8",
    )
    for env_name in (
        "OCTOAGENT_MCP_FILESYSTEM_BIN",
        "OCTOAGENT_FILESYSTEM_ROOT",
    ):
        monkeypatch.delenv(env_name, raising=False)

    config = ExtensionsConfig.from_file(str(config_path))

    assert config.mcp_servers["filesystem"].command == "/host/server"
    assert config.mcp_servers["filesystem"].args == ["/host/root"]
