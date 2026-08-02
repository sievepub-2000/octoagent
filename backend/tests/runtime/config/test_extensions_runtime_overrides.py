import json

from src.runtime.config.extensions_config import ExtensionsConfig


def test_environment_placeholders_are_resolved_without_server_specific_overrides(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "custom": {
                        "command": "$CUSTOM_MCP_BIN",
                        "args": ["$CUSTOM_MCP_ROOT"],
                        "permissionScope": "directory",
                        "env": {"TOKEN": "$CUSTOM_MCP_TOKEN"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CUSTOM_MCP_BIN", "/app/custom-mcp")
    monkeypatch.setenv("CUSTOM_MCP_ROOT", "/app/workspace")
    monkeypatch.setenv("CUSTOM_MCP_TOKEN", "secret")

    config = ExtensionsConfig.from_file(str(config_path))

    assert config.mcp_servers["custom"].command == "/app/custom-mcp"
    assert config.mcp_servers["custom"].args == ["/app/workspace"]
    assert config.mcp_servers["custom"].env == {"TOKEN": "secret"}
    assert config.mcp_servers["custom"].permission_scope == "directory"


def test_literal_commands_are_preserved(tmp_path) -> None:
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"filesystem": {"command": "/host/server", "args": ["/host/root"]}}}),
        encoding="utf-8",
    )
    config = ExtensionsConfig.from_file(str(config_path))

    assert config.mcp_servers["filesystem"].command == "/host/server"
    assert config.mcp_servers["filesystem"].args == ["/host/root"]
