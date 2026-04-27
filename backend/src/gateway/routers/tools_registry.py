from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

from src.tools.builtins.bytebot_compat_tools import BYTEBOT_COMPAT_TOOLS
from src.tools_registry.contracts import ToolCapabilityRegistryResponse
from src.tools_registry.service import ToolRegistryService

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get(
    "/registry",
    response_model=ToolCapabilityRegistryResponse,
    summary="Get Unified Tool Capability Registry",
    description="Aggregate MCP, skills, plugins, channels, and runtime capability surfaces in one endpoint.",
)
async def get_tool_capability_registry() -> ToolCapabilityRegistryResponse:
    return ToolRegistryService().build_registry()


class DesktopControlTool(BaseModel):
    name: str
    description: str


class DesktopControlStatusResponse(BaseModel):
    category: str = "desktop-control"
    badge: str = "stub"
    enabled: bool
    env_flag: str = "BYTEBOT_COMPAT_ENABLED"
    note: str
    tools: list[DesktopControlTool]


@router.get(
    "/desktop-control/status",
    response_model=DesktopControlStatusResponse,
    summary="Bytebot desktop-control adapter status",
    description="Observation-only adapter exposing Bytebot desktop vocabulary. Returns stub payloads; mount controlled by BYTEBOT_COMPAT_ENABLED env flag (default off).",
)
async def get_desktop_control_status() -> DesktopControlStatusResponse:
    flag = os.environ.get("BYTEBOT_COMPAT_ENABLED", "").strip().lower()
    enabled = flag in {"1", "true", "yes", "on"}
    tools = [
        DesktopControlTool(
            name=getattr(tool, "name", str(tool)),
            description=(getattr(tool, "description", "") or "").split("\n", 1)[0][:200],
        )
        for tool in BYTEBOT_COMPAT_TOOLS
    ]
    return DesktopControlStatusResponse(
        enabled=enabled,
        note=(
            "Observation-only stub. All actions return not_implemented JSON so "
            "agents degrade gracefully. Use /api/browser-runtime/* for real "
            "browser automation."
        ),
        tools=tools,
    )

