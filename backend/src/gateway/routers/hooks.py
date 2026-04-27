import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.hook_core import get_hook_core_service
from src.utils.agent_tool_guide import async_refresh_agent_tool_guide

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["hooks"])


# ── Response / Request models ─────────────────────────────────────────────────

class HookTriggerResponse(BaseModel):
    trigger: str
    command_count: int = 0


class HookResponse(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True
    triggers: list[HookTriggerResponse] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)


class HooksListResponse(BaseModel):
    hooks: list[HookResponse] = Field(default_factory=list)


class HookUpdateRequest(BaseModel):
    enabled: bool


class RuntimeHookResponse(BaseModel):
    hook_id: str
    event: str
    enabled: bool
    source: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeHooksListResponse(BaseModel):
    hooks: list[RuntimeHookResponse] = Field(default_factory=list)


class HookRuntimeStateResponse(BaseModel):
    total_hooks: int = 0
    enabled_hooks: int = 0
    events: list[str] = Field(default_factory=list)
    listeners: dict[str, int] = Field(default_factory=dict)
    total_webhooks: int = 0
    enabled_webhooks: int = 0


class WebhookCreateRequest(BaseModel):
    webhook_id: str
    url: str
    events: list[str]
    enabled: bool = True
    secret: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v

    @field_validator("events")
    @classmethod
    def events_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("events must not be empty")
        return v


class WebhookResponse(BaseModel):
    webhook_id: str
    url: str
    events: list[str]
    enabled: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebhooksListResponse(BaseModel):
    webhooks: list[WebhookResponse] = Field(default_factory=list)


class HookEmitRequest(BaseModel):
    event: str
    payload: dict[str, Any] = Field(default_factory=dict)


class HookEmitResponse(BaseModel):
    event: str
    listeners_invoked: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/hooks", response_model=HooksListResponse)
async def list_hooks() -> HooksListResponse:
    hooks = [HookResponse.model_validate(item) for item in get_hook_core_service().list_available_hooks()]
    return HooksListResponse(hooks=hooks)


@router.put("/hooks/{hook_name}", response_model=HookResponse)
async def update_hook(hook_name: str, request: HookUpdateRequest) -> HookResponse:
    updated = get_hook_core_service().set_hook_enabled(hook_name, request.enabled)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Hook '{hook_name}' not found")
    await async_refresh_agent_tool_guide()
    return HookResponse.model_validate(updated)


@router.get("/hooks/runtime", response_model=RuntimeHooksListResponse)
async def list_runtime_hooks() -> RuntimeHooksListResponse:
    """List all registered runtime hook bindings."""
    svc = get_hook_core_service()
    bindings = svc.list_runtime_hooks()
    return RuntimeHooksListResponse(
        hooks=[
            RuntimeHookResponse(
                hook_id=b.hook_id,
                event=b.event,
                enabled=b.enabled,
                source=b.source,
                metadata=dict(b.metadata),
            )
            for b in bindings
        ]
    )


@router.get("/hooks/state", response_model=HookRuntimeStateResponse)
async def get_hooks_runtime_state() -> HookRuntimeStateResponse:
    """Return aggregated runtime state: counts, active events, listener map."""
    state = get_hook_core_service().runtime_state()
    return HookRuntimeStateResponse(
        total_hooks=state.get("total_hooks", 0),
        enabled_hooks=state.get("enabled_hooks", 0),
        events=state.get("events", []),
        listeners=state.get("listeners", {}),
        total_webhooks=state.get("total_webhooks", 0),
        enabled_webhooks=state.get("enabled_webhooks", 0),
    )


@router.get("/hooks/webhooks", response_model=WebhooksListResponse)
async def list_webhooks() -> WebhooksListResponse:
    """List all registered webhooks."""
    svc = get_hook_core_service()
    webhooks = svc.list_webhooks()
    return WebhooksListResponse(
        webhooks=[
            WebhookResponse(
                webhook_id=w.webhook_id,
                url=w.url,
                events=w.events,
                enabled=w.enabled,
                metadata=dict(w.metadata),
            )
            for w in webhooks
        ]
    )


@router.post("/hooks/webhooks", response_model=WebhookResponse, status_code=201)
async def create_webhook(request: WebhookCreateRequest) -> WebhookResponse:
    """Register a new external webhook endpoint."""
    svc = get_hook_core_service()
    try:
        reg = svc.register_webhook(
            request.webhook_id,
            url=request.url,
            events=request.events,
            enabled=request.enabled,
            secret=request.secret,
            metadata=request.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await async_refresh_agent_tool_guide()
    return WebhookResponse(
        webhook_id=reg.webhook_id,
        url=reg.url,
        events=reg.events,
        enabled=reg.enabled,
        metadata=dict(reg.metadata),
    )


@router.delete("/hooks/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: str) -> None:
    """Remove a registered webhook."""
    removed = get_hook_core_service().remove_webhook(webhook_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Webhook '{webhook_id}' not found")
    await async_refresh_agent_tool_guide()


@router.post("/hooks/emit", response_model=HookEmitResponse)
async def emit_event(request: HookEmitRequest) -> HookEmitResponse:
    """Manually emit a named event (for admin/debugging)."""
    svc = get_hook_core_service()
    count = svc.dispatch(request.event, request.payload)
    return HookEmitResponse(event=request.event, listeners_invoked=count)