from __future__ import annotations

from langchain.tools import BaseTool

from .catalog import ToolCatalog
from .mcp_provider import MCPToolProvider


class ToolService:
    def __init__(
        self,
        *,
        catalog: ToolCatalog | None = None,
        mcp_provider: MCPToolProvider | None = None,
    ):
        self._catalog = catalog or ToolCatalog()
        self._mcp_provider = mcp_provider or MCPToolProvider()

    def get_available_tools(
        self,
        *,
        groups: list[str] | None = None,
        include_mcp: bool = True,
        model_name: str | None = None,
        subagent_enabled: bool = False,
    ) -> list[BaseTool]:
        configured_tools = self._catalog.load_configured_tools(groups)
        builtin_tools = self._catalog.load_builtin_tools(
            model_name=model_name,
            subagent_enabled=subagent_enabled,
        )
        mcp_tools = self._mcp_provider.load(include_mcp=include_mcp)
        return configured_tools + builtin_tools + mcp_tools
