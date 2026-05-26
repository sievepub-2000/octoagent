"""Gateway router for plugin capability discovery."""

from fastapi import APIRouter, HTTPException

from src.tools.plugins import (
    PluginCapabilityListResponse,
    PluginInstallRequest,
    PluginManifestListResponse,
    PluginRecommendationRequest,
    PluginRecommendationResponse,
    PluginRegistryEntry,
    PluginRegistryResponse,
    PluginToggleRequest,
    get_plugin_service,
)
from src.utils.agent_tool_guide import async_refresh_agent_tool_guide
from src.storage.workflow import utc_now

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("/capabilities", response_model=PluginCapabilityListResponse)
async def list_plugin_capabilities() -> PluginCapabilityListResponse:
    return get_plugin_service().list_plugins()


@router.get("/manifests", response_model=PluginManifestListResponse)
async def list_plugin_manifests() -> PluginManifestListResponse:
    return get_plugin_service().list_manifests()


@router.get("/registry", response_model=PluginRegistryResponse)
async def list_plugin_registry() -> PluginRegistryResponse:
    return get_plugin_service().list_registry()


@router.post("/recommendations", response_model=PluginRecommendationResponse)
async def recommend_plugins(
    request: PluginRecommendationRequest,
) -> PluginRecommendationResponse:
    return get_plugin_service().recommend_plugins(
        mode=request.mode,
        card_kinds=request.card_kinds,
    )


@router.post("/install", response_model=PluginRegistryEntry)
async def install_plugin(
    request: PluginInstallRequest,
) -> PluginRegistryEntry:
    entry = get_plugin_service().install_plugin(request, created_at=utc_now())
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{request.plugin_id}' not found")
    await async_refresh_agent_tool_guide()
    return entry


@router.post("/{plugin_id}/enable", response_model=PluginRegistryEntry)
async def enable_plugin(plugin_id: str) -> PluginRegistryEntry:
    entry = get_plugin_service().set_plugin_enabled(plugin_id, PluginToggleRequest(enabled=True))
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    await async_refresh_agent_tool_guide()
    return entry


@router.post("/{plugin_id}/disable", response_model=PluginRegistryEntry)
async def disable_plugin(plugin_id: str) -> PluginRegistryEntry:
    entry = get_plugin_service().set_plugin_enabled(plugin_id, PluginToggleRequest(enabled=False))
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    await async_refresh_agent_tool_guide()
    return entry


@router.delete("/{plugin_id}")
async def uninstall_plugin(plugin_id: str) -> dict:
    success = get_plugin_service().uninstall_plugin(plugin_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    await async_refresh_agent_tool_guide()
    return {"success": True, "plugin_id": plugin_id}
