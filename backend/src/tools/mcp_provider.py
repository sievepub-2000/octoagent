from __future__ import annotations

import logging

from langchain.tools import BaseTool

logger = logging.getLogger(__name__)


class MCPToolProvider:
    def load(self, *, include_mcp: bool = True) -> list[BaseTool]:
        if not include_mcp:
            return []

        try:
            from src.config.extensions_config import ExtensionsConfig
            from src.mcp.cache import get_cached_mcp_tools

            extensions_config = ExtensionsConfig.from_file()
            if not extensions_config.get_enabled_mcp_servers():
                return []

            mcp_tools = get_cached_mcp_tools()
            if mcp_tools:
                logger.info("Using %s cached MCP tool(s)", len(mcp_tools))
            return mcp_tools
        except ImportError:
            logger.warning(
                "MCP module not available. Install 'langchain-mcp-adapters' package to enable MCP tools."
            )
        except Exception as exc:
            logger.error("Failed to get cached MCP tools: %s", exc)
        return []
