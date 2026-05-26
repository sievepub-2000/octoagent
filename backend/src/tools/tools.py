import logging

from langchain.tools import BaseTool

from src.tools.service import ToolService

logger = logging.getLogger(__name__)


def get_available_tools(
    groups: list[str] | None = None,
    include_mcp: bool = True,
    model_name: str | None = None,
    subagent_enabled: bool = False,
) -> list[BaseTool]:
    """Get all available tools from config.

    Note: MCP tools should be initialized at application startup using
    `initialize_mcp_tools()` from src.tools.mcp module.

    Args:
        groups: Optional list of tool groups to filter by.
        include_mcp: Whether to include tools from MCP servers (default: True).
        model_name: Optional model name to determine if vision tools should be included.
        subagent_enabled: Whether to include subagent tools (task, task_status).

    Returns:
        List of available tools.
    """
    return ToolService().get_available_tools(
        groups=groups,
        include_mcp=include_mcp,
        model_name=model_name,
        subagent_enabled=subagent_enabled,
    )
