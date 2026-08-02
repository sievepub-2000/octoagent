import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.runtime.config.extensions_config import ExtensionsConfig, McpServerConfig, get_extensions_config, reload_extensions_config
from src.runtime.config.tool_config import ToolPermissionScope
from src.tools.mcp.smoke import load_mcp_smoke_snapshot, run_mcp_smoke_tests
from src.utils.agent_tool_guide import generate_agent_tool_guide
from src.utils.json_atomic import write_json_atomic

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["mcp"])

_MCP_RESPONSE_ONLY_FIELDS = {"status", "status_reason", "missing_env"}
_REDACTED = "********"
_SECRET_KEY = re.compile(r"token|secret|password|passwd|credential|authorization|api.?key", re.IGNORECASE)
_URI_PASSWORD = re.compile(r"([a-z][a-z0-9+.-]*://[^:/@\s]+:)([^@/\s]+)(@)", re.IGNORECASE)
_QUERY_SECRET = re.compile(r"(?i)([?&](?:token|secret|password|passwd|api_?key)=)([^&\s]+)")


def _redact_value(value: str, *, key: str = "") -> str:
    if not value:
        return value
    if _SECRET_KEY.search(key):
        return _REDACTED
    redacted = _URI_PASSWORD.sub(rf"\1{_REDACTED}\3", value)
    return _QUERY_SECRET.sub(rf"\1{_REDACTED}", redacted)


def _restore_redacted(incoming: Any, existing: Any) -> Any:
    """Restore masked response values from the raw, unresolved config."""
    if isinstance(incoming, str) and _REDACTED in incoming:
        return existing
    if isinstance(incoming, dict):
        previous = existing if isinstance(existing, dict) else {}
        return {key: _restore_redacted(value, previous.get(key)) for key, value in incoming.items()}
    if isinstance(incoming, list):
        previous = existing if isinstance(existing, list) else []
        return [
            _restore_redacted(value, previous[index] if index < len(previous) else None)
            for index, value in enumerate(incoming)
        ]
    return incoming


def _read_raw_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _raw_mcp_servers(config_data: dict[str, Any]) -> dict[str, Any]:
    servers = config_data.get("mcpServers", config_data.get("mcp_servers", {}))
    return dict(servers) if isinstance(servers, dict) else {}


class McpOAuthConfigResponse(BaseModel):
    """OAuth configuration for an MCP server."""

    enabled: bool = Field(default=True, description="Whether OAuth token injection is enabled")
    token_url: str = Field(default="", description="OAuth token endpoint URL")
    grant_type: Literal["client_credentials", "refresh_token"] = Field(default="client_credentials", description="OAuth grant type")
    client_id: str | None = Field(default=None, description="OAuth client ID")
    client_secret: str | None = Field(default=None, description="OAuth client secret")
    refresh_token: str | None = Field(default=None, description="OAuth refresh token")
    scope: str | None = Field(default=None, description="OAuth scope")
    audience: str | None = Field(default=None, description="OAuth audience")
    token_field: str = Field(default="access_token", description="Token response field containing access token")
    token_type_field: str = Field(default="token_type", description="Token response field containing token type")
    expires_in_field: str = Field(default="expires_in", description="Token response field containing expires-in seconds")
    default_token_type: str = Field(default="Bearer", description="Default token type when response omits token_type")
    refresh_skew_seconds: int = Field(default=60, description="Refresh this many seconds before expiry")
    extra_token_params: dict[str, str] = Field(default_factory=dict, description="Additional form params sent to token endpoint")


class McpSmokeTestConfigResponse(BaseModel):
    enabled: bool = True
    tool: str = ""
    args: dict = Field(default_factory=dict)
    expected: dict = Field(default_factory=dict)


class McpServerConfigResponse(BaseModel):
    """Response model for MCP server configuration."""

    enabled: bool = Field(default=True, description="Whether this MCP server is enabled")
    type: str = Field(default="stdio", description="Transport type: 'stdio', 'sse', or 'http'")
    command: str | None = Field(default=None, description="Command to execute to start the MCP server (for stdio type)")
    args: list[str] = Field(default_factory=list, description="Arguments to pass to the command (for stdio type)")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables for the MCP server")
    url: str | None = Field(default=None, description="URL of the MCP server (for sse or http type)")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers to send (for sse or http type)")
    oauth: McpOAuthConfigResponse | None = Field(default=None, description="OAuth configuration for MCP HTTP/SSE servers")
    description: str = Field(default="", description="Human-readable description of what this MCP server provides")
    permission_scope: ToolPermissionScope = Field(
        default="sandbox",
        alias="permissionScope",
        description="Server-enforced permission scope for every tool from this server.",
    )
    status: Literal["ready", "disabled", "configuration_error"] = Field(default="ready", description="Resolved runtime readiness")
    status_reason: str = Field(default="", description="Human-readable readiness reason")
    missing_env: list[str] = Field(default_factory=list, description="Environment variables configured but unresolved")
    smokeTest: McpSmokeTestConfigResponse | None = Field(default=None, description="Minimal smoke test configuration")


def _mcp_server_response(server: McpServerConfig) -> McpServerConfigResponse:
    payload = server.model_dump(by_alias=True)
    payload["args"] = [_redact_value(str(value)) for value in server.args]
    payload["env"] = {key: _redact_value(str(value), key=key) for key, value in server.env.items()}
    payload["headers"] = {key: _redact_value(str(value), key=key) for key, value in server.headers.items()}
    payload["url"] = _redact_value(str(server.url)) if server.url else None
    if server.oauth is not None:
        oauth = server.oauth.model_dump()
        oauth["client_secret"] = _redact_value(str(oauth.get("client_secret") or ""), key="client_secret") or None
        oauth["refresh_token"] = _redact_value(str(oauth.get("refresh_token") or ""), key="refresh_token") or None
        payload["oauth"] = oauth
    missing_env = [key for key, value in server.env.items() if not str(value or "").strip()]
    if not server.enabled:
        status: Literal["ready", "disabled", "configuration_error"] = "disabled"
        status_reason = "Server is disabled."
        if missing_env:
            status_reason += f" Missing environment variable(s): {', '.join(missing_env)}."
    elif missing_env:
        status = "configuration_error"
        status_reason = f"Missing environment variable(s): {', '.join(missing_env)}"
    else:
        status = "ready"
        status_reason = "Server configuration is ready."
    payload.update(
        {
            "status": status,
            "status_reason": status_reason,
            "missing_env": missing_env,
        }
    )
    return McpServerConfigResponse(**payload)


class McpConfigResponse(BaseModel):
    """Response model for MCP configuration."""

    mcp_servers: dict[str, McpServerConfigResponse] = Field(
        default_factory=dict,
        description="Map of MCP server name to configuration",
    )


class McpConfigUpdateRequest(BaseModel):
    """Request model for updating MCP configuration."""

    mcp_servers: dict[str, McpServerConfigResponse] = Field(
        ...,
        description="Map of MCP server name to configuration",
    )


@router.get(
    "/mcp/config",
    response_model=McpConfigResponse,
    summary="Get MCP Configuration",
    description="Retrieve the current Model Context Protocol (MCP) server configurations.",
)
async def get_mcp_configuration() -> McpConfigResponse:
    """Get the current MCP configuration.

    Returns:
        The current MCP configuration with all servers.

    Example:
        ```json
        {
            "mcp_servers": {
                "github": {
                    "enabled": true,
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {"GITHUB_TOKEN": "ghp_xxx"},
                    "description": "GitHub MCP server for repository operations"
                }
            }
        }
        ```
    """
    config = get_extensions_config()

    return McpConfigResponse(mcp_servers={name: _mcp_server_response(server) for name, server in config.mcp_servers.items()})


@router.put(
    "/mcp/config",
    response_model=McpConfigResponse,
    summary="Update MCP Configuration",
    description="Update Model Context Protocol (MCP) server configurations and save to file.",
)
def update_mcp_configuration(request: McpConfigUpdateRequest) -> McpConfigResponse:
    """Update the MCP configuration.

    This will:
    1. Save the new configuration to the mcp_config.json file
    2. Reload the configuration cache
    3. Reset MCP tools cache to trigger reinitialization

    Args:
        request: The new MCP configuration to save.

    Returns:
        The updated MCP configuration.

    Raises:
        HTTPException: 500 if the configuration file cannot be written.

    Example Request:
        ```json
        {
            "mcp_servers": {
                "github": {
                    "enabled": true,
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {"GITHUB_TOKEN": "$GITHUB_TOKEN"},
                    "description": "GitHub MCP server for repository operations"
                }
            }
        }
        ```
    """
    try:
        # Get the current config path (or determine where to save it)
        config_path = ExtensionsConfig.resolve_config_path()

        config_data = _read_raw_config(config_path)
        existing_servers = _raw_mcp_servers(config_data)
        config_data["mcpServers"] = {
            name: _restore_redacted(
                server.model_dump(by_alias=True, exclude=_MCP_RESPONSE_ONLY_FIELDS, exclude_none=True),
                existing_servers.get(name, {}),
            )
            for name, server in request.mcp_servers.items()
        }
        config_data.pop("mcp_servers", None)

        # Write the configuration to file atomically
        write_json_atomic(config_path, config_data)
        logger.info(f"MCP configuration updated and saved to: {config_path}")

        # NOTE: No need to reload/reset cache here - LangGraph Server (separate process)
        # will detect config file changes via mtime and reinitialize MCP tools automatically

        # Reload the configuration and update the global cache
        reloaded_config = reload_extensions_config()
        generate_agent_tool_guide()
        return McpConfigResponse(mcp_servers={name: _mcp_server_response(server) for name, server in reloaded_config.mcp_servers.items()})

    except Exception as e:
        logger.error(f"Failed to update MCP configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update MCP configuration: {str(e)}")


class McpServerUpsertRequest(BaseModel):
    """Add or replace a single MCP server entry."""

    name: str = Field(..., description="MCP server identifier")
    server: McpServerConfigResponse = Field(..., description="Server configuration payload")


class McpSmokeResponse(BaseModel):
    generated_at: str | None = None
    summary: dict = Field(default_factory=dict)
    servers: dict = Field(default_factory=dict)


@router.get(
    "/mcp/smoke",
    response_model=McpSmokeResponse,
    summary="Get latest MCP smoke-test results",
)
async def get_mcp_smoke_results() -> McpSmokeResponse:
    return McpSmokeResponse(**load_mcp_smoke_snapshot())


@router.post(
    "/mcp/smoke",
    response_model=McpSmokeResponse,
    summary="Run MCP smoke tests",
)
async def run_mcp_smoke_results() -> McpSmokeResponse:
    return McpSmokeResponse(**await run_mcp_smoke_tests())


class McpServerMutationResponse(BaseModel):
    success: bool = True
    message: str = ""
    mcp_servers: dict[str, McpServerConfigResponse] = Field(default_factory=dict)


def _persist_mcp_servers(servers: dict[str, dict[str, Any]]) -> dict[str, McpServerConfigResponse]:
    config_path = ExtensionsConfig.resolve_config_path()
    config_data = _read_raw_config(config_path)
    config_data["mcpServers"] = servers
    config_data.pop("mcp_servers", None)
    write_json_atomic(config_path, config_data)
    reloaded_config = reload_extensions_config()
    return {name: _mcp_server_response(server) for name, server in reloaded_config.mcp_servers.items()}


@router.post(
    "/mcp/servers",
    response_model=McpServerMutationResponse,
    summary="Add or update a single MCP server",
)
def upsert_mcp_server(request: McpServerUpsertRequest) -> McpServerMutationResponse:
    name = (request.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="MCP server name is required")

    config_path = ExtensionsConfig.resolve_config_path()
    config_data = _read_raw_config(config_path)
    servers = _raw_mcp_servers(config_data)
    servers[name] = _restore_redacted(
        request.server.model_dump(by_alias=True, exclude=_MCP_RESPONSE_ONLY_FIELDS, exclude_none=True),
        servers.get(name, {}),
    )

    try:
        refreshed = _persist_mcp_servers(servers)
        generate_agent_tool_guide()
    except Exception as exc:  # noqa: BLE001 - surface in API
        logger.error("Failed to upsert MCP server %s: %s", name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return McpServerMutationResponse(
        success=True,
        message=f"MCP server '{name}' saved",
        mcp_servers=refreshed,
    )


@router.delete(
    "/mcp/servers/{name}",
    response_model=McpServerMutationResponse,
    summary="Remove a single MCP server",
)
def delete_mcp_server(name: str) -> McpServerMutationResponse:
    config_path = ExtensionsConfig.resolve_config_path()
    servers = _raw_mcp_servers(_read_raw_config(config_path))
    if name not in servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    servers.pop(name, None)

    try:
        refreshed = _persist_mcp_servers(servers)
        generate_agent_tool_guide()
    except Exception as exc:  # noqa: BLE001 - surface in API
        logger.error("Failed to delete MCP server %s: %s", name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return McpServerMutationResponse(
        success=True,
        message=f"MCP server '{name}' removed",
        mcp_servers=refreshed,
    )
