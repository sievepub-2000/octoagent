from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from src.tools.builtins.bytebot_compat_tools import BYTEBOT_COMPAT_TOOLS
from src.tools.builtins.desktop_driver_tools import DESKTOP_DRIVER_TOOLS, desktop_driver_status
from src.tools.registry.contracts import ToolCapabilityRegistryResponse
from src.tools.registry.service import ToolRegistryService

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get(
    "/registry",
    response_model=ToolCapabilityRegistryResponse,
    summary="Get Unified Tool Capability Registry",
    description="Aggregate MCP, skills, plugins, channels, and runtime capability surfaces in one endpoint.",
)
async def get_tool_capability_registry() -> ToolCapabilityRegistryResponse:
    # Building the unified registry scans skill files and probes several
    # capability sources.  Running it on the ASGI event loop makes the skill
    # loader deliberately return an empty cold cache, so the first Tools Hub
    # request after a restart incorrectly reports zero skills.
    return await asyncio.to_thread(ToolRegistryService().build_registry)


class DesktopControlTool(BaseModel):
    name: str
    description: str


class DesktopControlStatusResponse(BaseModel):
    category: str = "desktop-control"
    badge: str = "native-driver"
    enabled: bool
    env_flag: str = "OCTOAGENT_SYSTEM_TOOLS_ENABLED"
    note: str
    tools: list[DesktopControlTool]


@router.get(
    "/desktop-control/status",
    response_model=DesktopControlStatusResponse,
    summary="Bytebot desktop-control adapter status",
    description="Observation-only adapter exposing Bytebot desktop vocabulary. Returns stub payloads; mount controlled by BYTEBOT_COMPAT_ENABLED env flag (default off).",
)
async def get_desktop_control_status() -> DesktopControlStatusResponse:
    status = desktop_driver_status()
    tools = [
        DesktopControlTool(
            name=getattr(tool, "name", str(tool)),
            description=(getattr(tool, "description", "") or "").split("\n", 1)[0][:200],
        )
        for tool in [*DESKTOP_DRIVER_TOOLS, *BYTEBOT_COMPAT_TOOLS]
    ]
    return DesktopControlStatusResponse(
        enabled=bool(status.get("available")),
        badge="native-driver" if status.get("available") else "driver-unavailable",
        note=("Native desktop driver tools are registered as system-permission tools. They use pyautogui when importable and xdotool as fallback; actions require an active graphical display."),
        tools=tools,
    )
