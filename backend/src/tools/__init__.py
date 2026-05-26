from __future__ import annotations

from langchain.tools import BaseTool

from .service import ToolService


def get_available_tools(
    groups: list[str] | None = None,
    include_mcp: bool = True,
    model_name: str | None = None,
    permission_mode: str | None = None,
    subagent_enabled: bool = False,
) -> list[BaseTool]:
    return ToolService().get_available_tools(
        groups=groups,
        include_mcp=include_mcp,
        model_name=model_name,
        permission_mode=permission_mode,
        subagent_enabled=subagent_enabled,
    )


__all__ = ["get_available_tools"]
