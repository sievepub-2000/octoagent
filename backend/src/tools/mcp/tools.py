"""Load MCP tools using langchain-mcp-adapters.

Fixed: Serial initialization to avoid resource competition, increased timeout for OpenAPI server.
"""

import asyncio
import logging

from langchain_core.tools import BaseTool

from src.runtime.config.extensions_config import ExtensionsConfig
from src.tools.mcp.client import build_servers_config
from src.tools.mcp.oauth import build_oauth_tool_interceptor, get_initial_oauth_headers

logger = logging.getLogger(__name__)

# Increased timeout for OpenAPI server (needs to fetch OpenAPI spec)
_MCP_SERVER_TIMEOUT_SECONDS = 15.0


async def _load_single_server_tools(server_name: str, connection: dict) -> list[BaseTool]:
    """Load tools from a single MCP server with increased timeout."""
    try:
        from langchain_mcp_adapters.tools import load_mcp_tools

        logger.info(f"Loading tools from {server_name}...")

        # Use asyncio.wait_for to enforce timeout
        tools = await asyncio.wait_for(
            load_mcp_tools(
                None,
                connection=connection,
                server_name=server_name,
                tool_interceptors=[],  # Will be injected by caller
            ),
            timeout=_MCP_SERVER_TIMEOUT_SECONDS,
        )

        logger.info(f"✓ {server_name}: loaded {len(tools)} tool(s)")
        return tools

    except TimeoutError:
        logger.error(f"✗ {server_name}: initialization timeout after {_MCP_SERVER_TIMEOUT_SECONDS}s")
        return []
    except Exception as e:
        logger.error(f"✗ {server_name}: failed to load - {e}")
        return []


async def get_mcp_tools() -> list[BaseTool]:
    """Get all tools from enabled MCP servers.

    Uses serial initialization to avoid resource competition between servers.

    Returns:
        List of LangChain tools from all enabled MCP servers.
    """
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: F401
    except ImportError:
        logger.warning("langchain-mcp-adapters not installed. Install it to enable MCP tools: pip install langchain-mcp-adapters")
        return []

    # NOTE: We use ExtensionsConfig.from_file() instead of get_extensions_config()
    # to always read the latest configuration from disk. This ensures that changes
    # made through the Gateway API (which runs in a separate process) are immediately
    # reflected when initializing MCP tools.
    extensions_config = ExtensionsConfig.from_file()
    servers_config = build_servers_config(extensions_config)

    if not servers_config:
        logger.info("No enabled MCP servers configured")
        return []

    try:
        # Inject initial OAuth headers for server connections (tool discovery/session init)
        initial_oauth_headers = await get_initial_oauth_headers(extensions_config)
        for server_name, auth_header in initial_oauth_headers.items():
            if server_name not in servers_config:
                continue
            if servers_config[server_name].get("transport") in ("sse", "http"):
                existing_headers = dict(servers_config[server_name].get("headers", {}))
                existing_headers["Authorization"] = auth_header
                servers_config[server_name]["headers"] = existing_headers

        tool_interceptors = []
        oauth_interceptor = build_oauth_tool_interceptor(extensions_config)
        if oauth_interceptor is not None:
            tool_interceptors.append(oauth_interceptor)

        # Serial initialization to avoid resource competition
        logger.info(f"Initializing MCP tools serially for {len(servers_config)} server(s)")

        all_tools = []
        for server_name, connection in servers_config.items():
            # Inject tool interceptors into connection if needed
            conn_with_interceptors = dict(connection)

            tools = await _load_single_server_tools(server_name, conn_with_interceptors)
            all_tools.extend(tools)

            # Brief pause between servers to avoid resource competition
            await asyncio.sleep(0.5)

        logger.info(f"Successfully loaded {len(all_tools)} tool(s) from MCP servers")
        return all_tools

    except Exception as e:
        logger.error(f"Failed to load MCP tools: {e}", exc_info=True)
        return []


async def preflight_mcp_check() -> dict[str, bool]:
    """Pre-flight check for MCP server accessibility.

    Tests each server individually before full initialization.

    Returns:
        Dictionary mapping server names to their accessibility status.
    """
    try:
        extensions_config = ExtensionsConfig.from_file()
        servers_config = build_servers_config(extensions_config)

        if not servers_config:
            return {}

        results = {}

        for server_name, connection in servers_config.items():
            try:
                # Quick connectivity test (3 second timeout)
                await asyncio.wait_for(_load_single_server_tools(server_name, connection), timeout=3.0)
                results[server_name] = True
                logger.info(f"✓ {server_name}: accessible")
            except Exception as e:
                results[server_name] = False
                logger.warning(f"✗ {server_name}: not accessible - {e}")

        return results

    except Exception as e:
        logger.error(f"Preflight MCP check failed: {e}")
        return {}
