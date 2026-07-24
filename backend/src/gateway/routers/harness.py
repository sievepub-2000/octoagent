from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter

from src.harness.memory import get_harness_memory
from src.tools.builtins.bytebot_compat_tools import BYTEBOT_COMPAT_TOOLS
from src.tools.builtins.desktop_driver_tools import DESKTOP_DRIVER_TOOLS, desktop_driver_status
from src.tools.registry.service import ToolRegistryService

router = APIRouter(prefix="/api/harness", tags=["harness"])


def _snapshot() -> dict:
    registry = ToolRegistryService().build_registry().model_dump(mode="json")
    return {
        **registry,
        "module": "harness",
        "architecture": "agent-runtime+harness",
        "scanned_at": datetime.now(UTC).isoformat(),
        "memory": get_harness_memory().stats(),
    }


@router.get("", summary="Get the live Harness capability snapshot")
async def get_harness_snapshot() -> dict:
    return await asyncio.to_thread(_snapshot)


@router.post("/refresh", summary="Rescan every Harness-managed capability source")
async def refresh_harness_snapshot() -> dict:
    return await asyncio.to_thread(_snapshot)


@router.get("/desktop-control/status", summary="Get the Harness desktop execution status")
async def desktop_control_status() -> dict:
    status = desktop_driver_status()
    return {
        "category": "desktop-control",
        "badge": "native-driver" if status.get("available") else "driver-unavailable",
        "enabled": bool(status.get("available")),
        "env_flag": "OCTOAGENT_SYSTEM_TOOLS_ENABLED",
        "note": "Harness-managed desktop adapter; system permission is enforced at dispatch.",
        "tools": [
            {
                "name": getattr(tool, "name", str(tool)),
                "description": (getattr(tool, "description", "") or "").split("\n", 1)[0][:200],
            }
            for tool in [*DESKTOP_DRIVER_TOOLS, *BYTEBOT_COMPAT_TOOLS]
        ],
    }
