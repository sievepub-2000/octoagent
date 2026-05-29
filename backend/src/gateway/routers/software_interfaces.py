from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.tools.software_interfaces.catalog import get_software_interface, list_software_interfaces, summarize_categories
from src.tools.software_interfaces.composio_gateway import (
    authorize,
    delete_connection,
    gateway_config,
    get_user_scopes,
    list_active_triggers,
    list_available_triggers,
    list_connections,
    list_tools,
    set_user_scopes,
    sync_connection,
)

router = APIRouter(prefix="/api/software-interfaces", tags=["software-interfaces"])


class SoftwareInterfaceItem(BaseModel):
    id: str
    slug: str
    name: str
    category: str
    description: str
    source: str
    auth_provider: str
    status: str
    supports_oauth: bool


class SoftwareInterfaceCategory(BaseModel):
    id: str
    label: str
    count: int


class SoftwareInterfaceCatalogResponse(BaseModel):
    source: str = "composio_catalog"
    total: int
    categories: list[SoftwareInterfaceCategory]
    interfaces: list[SoftwareInterfaceItem]


class SoftwareInterfaceStatusResponse(BaseModel):
    enabled: bool
    mode: str
    base_url_configured: bool
    api_key_configured: bool
    catalog_total: int


class SoftwareInterfaceAuthorizeRequest(BaseModel):
    extra_params: dict[str, object] = Field(default_factory=dict)


class SoftwareInterfaceExecuteRequest(BaseModel):
    tool: str
    arguments: dict[str, object] = Field(default_factory=dict)


class SoftwareInterfaceScopesRequest(BaseModel):
    read: bool = True
    write: bool = True
    admin: bool = False


class SoftwareInterfaceLogoutRequest(BaseModel):
    connection_id: str | None = None


class SoftwareInterfaceSyncRequest(BaseModel):
    reason: str = "manual"


class SoftwareInterfaceTriggerEnableRequest(BaseModel):
    slug: str
    connection_id: str
    toolkit: str | None = None
    trigger_config: dict[str, object] = Field(default_factory=dict)


@router.get("/catalog", response_model=SoftwareInterfaceCatalogResponse)
async def get_catalog() -> SoftwareInterfaceCatalogResponse:
    interfaces = [SoftwareInterfaceItem(**item.as_dict()) for item in list_software_interfaces()]
    return SoftwareInterfaceCatalogResponse(
        total=len(interfaces),
        categories=[SoftwareInterfaceCategory(**category) for category in summarize_categories()],
        interfaces=interfaces,
    )


@router.get("/status", response_model=SoftwareInterfaceStatusResponse)
async def get_status() -> SoftwareInterfaceStatusResponse:
    cfg = gateway_config()
    return SoftwareInterfaceStatusResponse(
        enabled=cfg.enabled,
        mode=cfg.mode,
        base_url_configured=bool(cfg.base_url),
        api_key_configured=cfg.api_key_configured,
        catalog_total=len(list_software_interfaces()),
    )


@router.get("/connections")
async def get_connections() -> dict[str, object]:
    return list_connections()


@router.delete("/connections/{connection_id}")
async def delete_software_interface_connection(connection_id: str) -> dict[str, object]:
    return delete_connection(connection_id)


@router.get("/{toolkit}/tools")
async def get_toolkit_tools(toolkit: str) -> dict[str, object]:
    if get_software_interface(toolkit) is None:
        raise HTTPException(status_code=404, detail="Unknown software interface toolkit")
    return list_tools([toolkit])


@router.post("/{toolkit}/authorize")
async def authorize_toolkit(toolkit: str, request: SoftwareInterfaceAuthorizeRequest) -> dict[str, object]:
    if get_software_interface(toolkit) is None:
        raise HTTPException(status_code=404, detail="Unknown software interface toolkit")
    return authorize(toolkit, dict(request.extra_params))


@router.post("/{toolkit}/logout")
async def logout_toolkit(toolkit: str, request: SoftwareInterfaceLogoutRequest) -> dict[str, object]:
    if get_software_interface(toolkit) is None:
        raise HTTPException(status_code=404, detail="Unknown software interface toolkit")
    if request.connection_id:
        return delete_connection(request.connection_id)
    connections = list_connections()
    for connection in connections.get("connections", []):
        if not isinstance(connection, dict):
            continue
        if str(connection.get("toolkit", "")).strip().lower() == toolkit.strip().lower():
            connection_id = str(connection.get("id", "")).strip()
            if connection_id:
                return delete_connection(connection_id)
    if connections.get("status") == "not_configured":
        return connections
    return {"success": False, "status": "not_connected", "toolkit": toolkit, "detail": "No connection found for toolkit."}


@router.get("/{toolkit}/scopes")
async def get_toolkit_scopes(toolkit: str) -> dict[str, object]:
    if get_software_interface(toolkit) is None:
        raise HTTPException(status_code=404, detail="Unknown software interface toolkit")
    return get_user_scopes(toolkit)


@router.put("/{toolkit}/scopes")
async def update_toolkit_scopes(toolkit: str, request: SoftwareInterfaceScopesRequest) -> dict[str, object]:
    if get_software_interface(toolkit) is None:
        raise HTTPException(status_code=404, detail="Unknown software interface toolkit")
    return set_user_scopes(toolkit, request.model_dump())


@router.post("/connections/{connection_id}/sync")
async def sync_software_interface_connection(connection_id: str, request: SoftwareInterfaceSyncRequest) -> dict[str, object]:
    return sync_connection(connection_id, request.reason)


@router.get("/{toolkit}/triggers/available")
async def get_available_triggers(toolkit: str, connection_id: str | None = None) -> dict[str, object]:
    if get_software_interface(toolkit) is None:
        raise HTTPException(status_code=404, detail="Unknown software interface toolkit")
    return list_available_triggers(toolkit, connection_id)


@router.get("/{toolkit}/triggers")
async def get_active_triggers(toolkit: str, connection_id: str | None = None) -> dict[str, object]:
    if get_software_interface(toolkit) is None:
        raise HTTPException(status_code=404, detail="Unknown software interface toolkit")
    return list_active_triggers(toolkit, connection_id)


