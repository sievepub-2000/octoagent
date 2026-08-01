import inspect
import json

from src.gateway.routers.mcp import (
    _mcp_server_response,
    _restore_redacted,
    delete_mcp_server,
    run_mcp_smoke_results,
    update_mcp_configuration,
    upsert_mcp_server,
)
from src.runtime.config.extensions_config import McpOAuthConfig, McpServerConfig


def test_mcp_file_mutations_run_in_fastapi_worker_pool() -> None:
    assert not inspect.iscoroutinefunction(update_mcp_configuration)
    assert not inspect.iscoroutinefunction(upsert_mcp_server)
    assert not inspect.iscoroutinefunction(delete_mcp_server)


def test_mcp_smoke_test_remains_async() -> None:
    assert inspect.iscoroutinefunction(run_mcp_smoke_results)


def test_mcp_responses_redact_secrets_and_keep_permission_scope() -> None:
    server = McpServerConfig(
        command="mcp-server",
        args=["postgresql://agent:database-secret@postgres:5432/agent"],
        env={"API_TOKEN": "token-secret", "PUBLIC_MODE": "safe"},
        headers={"Authorization": "Bearer header-secret"},
        url="https://user:url-secret@example.test/mcp?api_key=query-secret",
        permissionScope="system",
        oauth=McpOAuthConfig(
            token_url="https://example.test/token",
            client_secret="oauth-secret",
            refresh_token="refresh-secret",
        ),
    )

    payload = _mcp_server_response(server).model_dump(by_alias=True)
    serialized = json.dumps(payload)

    for secret in (
        "database-secret",
        "token-secret",
        "header-secret",
        "url-secret",
        "query-secret",
        "oauth-secret",
        "refresh-secret",
    ):
        assert secret not in serialized
    assert payload["permissionScope"] == "system"
    assert payload["env"]["PUBLIC_MODE"] == "safe"


def test_redacted_values_restore_from_unresolved_raw_config() -> None:
    existing = {
        "args": ["postgresql://agent:real-secret@postgres/agent"],
        "env": {"API_TOKEN": "$API_TOKEN", "PUBLIC_MODE": "safe"},
        "permissionScope": "system",
    }
    incoming = {
        "args": ["postgresql://agent:********@postgres/agent"],
        "env": {"API_TOKEN": "********", "PUBLIC_MODE": "updated"},
        "permissionScope": "system",
    }

    restored = _restore_redacted(incoming, existing)

    assert restored["args"] == ["postgresql://agent:real-secret@postgres/agent"]
    assert restored["env"] == {"API_TOKEN": "$API_TOKEN", "PUBLIC_MODE": "updated"}
