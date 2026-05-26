"""Expose the per-host ResourceProfile so the frontend can sync caps."""

from fastapi import APIRouter

from src.agents.resource_profile import get_resource_profile

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


@router.get("/profile")
async def runtime_profile() -> dict:
    """Return hardware-aware recommended caps for this host."""
    return get_resource_profile().to_dict()
