from __future__ import annotations

import logging

from langchain.tools import BaseTool

from src.tools.permissions import max_tool_permission_scope, set_tool_permission_metadata

logger = logging.getLogger(__name__)


class MCPToolProvider:
    def load(self, *, include_mcp: bool = True) -> list[BaseTool]:
        if not include_mcp:
            return []

        try:
            from src.runtime.config.extensions_config import ExtensionsConfig
            from src.tools.mcp.cache import get_cached_mcp_tools

            extensions_config = ExtensionsConfig.from_file()
            enabled_servers = extensions_config.get_enabled_mcp_servers()
            if not enabled_servers:
                return []

            mcp_tools = get_cached_mcp_tools()
            if mcp_tools:
                logger.info("Using %s cached MCP tool(s)", len(mcp_tools))
            scope = max_tool_permission_scope([server.permission_scope for server in enabled_servers.values()])
            return [set_tool_permission_metadata(tool, scope, source="mcp") for tool in mcp_tools]
        except ImportError:
            logger.warning("MCP module not available. Install 'langchain-mcp-adapters' package to enable MCP tools.")
        except Exception as exc:
            logger.error("Failed to get cached MCP tools: %s", exc)
        return []
