import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.gateway.security import require_operator_or_403
from src.harness.hook_core import get_hook_core_service
from src.harness.hooks import get_hook_registry
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
    runtime_events: dict[str, list[HookTriggerResponse]] = {}
    for name, event in get_hook_registry().list_registered():
        runtime_events.setdefault(name, []).append(HookTriggerResponse(trigger=event, command_count=1))
    hooks.extend(
        HookResponse(
            name=name,
            description="OctoAgent runtime hook",
            enabled=True,
            triggers=triggers,
            files=[],
        )
        for name, triggers in sorted(runtime_events.items())
    )
    return HooksListResponse(hooks=hooks)


@router.put("/hooks/{hook_name}", response_model=HookResponse)
async def update_hook(
    hook_name: str,
    request: HookUpdateRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> HookResponse:
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    updated = get_hook_core_service().set_hook_enabled(hook_name, request.enabled)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Hook '{hook_name}' not found")
    await async_refresh_agent_tool_guide()
    return HookResponse.model_validate(updated)


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


@router.post("/hooks/emit", response_model=HookEmitResponse)
async def emit_event(
    request: HookEmitRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> HookEmitResponse:
    """Manually emit a named event (for admin/debugging)."""
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    svc = get_hook_core_service()
    count = svc.dispatch(request.event, request.payload)
    return HookEmitResponse(event=request.event, listeners_invoked=count)
