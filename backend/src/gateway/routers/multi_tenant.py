"""Multi-tenant management gateway router.

Exposes tenant registration, isolation policy management, and
request-time tenant context resolution.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from src.gateway.security import require_operator_or_403
from src.governance.multi_tenant import get_tenant_registry
from src.governance.operator import confirmation_matches

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tenants", tags=["multi_tenant"])
TENANT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


# ── Models ─────────────────────────────────────────────────────────────────────


class TenantResponse(BaseModel):
    tenant_id: str
    display_name: str
    tier: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_enterprise: bool = False


class TenantsListResponse(BaseModel):
    tenants: list[TenantResponse] = Field(default_factory=list)
    total: int = 0


class IsolationPolicyResponse(BaseModel):
    workspace_isolation: str
    data_isolation: str
    skill_sharing: str
    max_concurrent_workspaces: int
    max_agents_per_workspace: int


class TenantDetailResponse(BaseModel):
    tenant: TenantResponse
    policy: IsolationPolicyResponse


class CreateTenantRequest(BaseModel):
    tenant_id: str
    display_name: str = ""
    tier: Literal["free", "pro", "enterprise"] = "free"
    metadata: dict[str, Any] = Field(default_factory=dict)
    policy: IsolationPolicyResponse | None = None


class TenantContextResponse(BaseModel):
    tenant_id: str
    display_name: str
    tier: str
    resolved_from: str


class LimitCheckResponse(BaseModel):
    tenant_id: str
    check: str
    current_count: int
    allowed: bool
    limit: int


class MultiTenantGovernanceResponse(BaseModel):
    registry_path: str = ""
    tenant_count: int = 0
    enterprise_count: int = 0
    max_concurrent_workspaces: int = 0
    max_agents_per_workspace: int = 0
    audit_events: list[dict[str, Any]] = Field(default_factory=list)


class MultiTenantExportResponse(BaseModel):
    version: str
    registry_path: str
    tenants: dict[str, dict[str, Any]] = Field(default_factory=dict)
    policies: dict[str, dict[str, Any]] = Field(default_factory=dict)
    audit_events: list[dict[str, Any]] = Field(default_factory=list)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _tenant_to_response(t) -> TenantResponse:
    return TenantResponse(
        tenant_id=t.tenant_id,
        display_name=t.display_name,
        tier=t.tier,
        metadata=t.metadata,
        is_enterprise=t.is_enterprise,
    )


def _policy_to_response(p) -> IsolationPolicyResponse:
    return IsolationPolicyResponse(
        workspace_isolation=p.workspace_isolation,
        data_isolation=p.data_isolation,
        skill_sharing=p.skill_sharing,
        max_concurrent_workspaces=p.max_concurrent_workspaces,
        max_agents_per_workspace=p.max_agents_per_workspace,
    )


def _resolve_tenant_id(x_tenant_id: str | None) -> str:
    """Resolve tenant from X-Tenant-ID header, defaulting to 'default'."""
    return (x_tenant_id or "").strip() or "default"


def _require_registered_tenant(reg, tenant_id: str):
    tenant = reg.get_tenant(tenant_id)
    if tenant.tenant_id == "default" and tenant_id != "default":
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
    return tenant


def _validate_tenant_id(tenant_id: str) -> str:
    tenant_id = (tenant_id or "").strip()
    if not TENANT_ID_RE.fullmatch(tenant_id):
        raise HTTPException(
            status_code=400,
            detail="tenant_id must be 1-64 characters and contain only letters, numbers, '_' or '-'",
        )
    return tenant_id


def _require_operator(
    *,
    role: str | None,
    token: str | None,
    minimum: str = "operator",
) -> None:
    require_operator_or_403(role=role, token=token, minimum=minimum)


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("", response_model=TenantsListResponse)
async def list_tenants() -> TenantsListResponse:
    """List all registered tenants."""
    reg = get_tenant_registry()
    tenants = reg.list_tenants()
    return TenantsListResponse(
        tenants=[_tenant_to_response(t) for t in tenants],
        total=len(tenants),
    )


@router.get("/governance", response_model=MultiTenantGovernanceResponse)
async def get_multi_tenant_governance() -> MultiTenantGovernanceResponse:
    """Return operator-facing tenant governance counters and audit events."""
    return MultiTenantGovernanceResponse.model_validate(get_tenant_registry().governance_snapshot())


@router.get("/export", response_model=MultiTenantExportResponse)
async def export_multi_tenant_registry(
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="admin", alias="X-OctoAgent-Operator-Role"),
) -> MultiTenantExportResponse:
    """Export persisted tenant/policy registry state for audit and backup."""
    _require_operator(role=x_octoagent_operator_role, token=x_octoagent_operator_token, minimum="admin")
    return MultiTenantExportResponse.model_validate(get_tenant_registry().export_state())


@router.post("", response_model=TenantDetailResponse, status_code=201)
async def create_tenant(
    request: CreateTenantRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> TenantDetailResponse:
    """Register a new tenant with an optional isolation policy."""
    from src.governance.multi_tenant import TenantContext, TenantIsolationPolicy

    _require_operator(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    tenant_id = _validate_tenant_id(request.tenant_id)
    reg = get_tenant_registry()
    tenant = TenantContext(
        tenant_id=tenant_id,
        display_name=request.display_name,
        tier=request.tier,
        metadata=request.metadata,
    )
    policy: TenantIsolationPolicy | None = None
    if request.policy is not None:
        policy = TenantIsolationPolicy(
            workspace_isolation=request.policy.workspace_isolation,
            data_isolation=request.policy.data_isolation,
            skill_sharing=request.policy.skill_sharing,
            max_concurrent_workspaces=request.policy.max_concurrent_workspaces,
            max_agents_per_workspace=request.policy.max_agents_per_workspace,
        )
    reg.register(tenant, policy)
    return TenantDetailResponse(
        tenant=_tenant_to_response(tenant),
        policy=_policy_to_response(reg.get_policy(tenant.tenant_id)),
    )


@router.put("/{tenant_id}/policy", response_model=TenantDetailResponse)
async def update_tenant_policy(
    tenant_id: str,
    request: IsolationPolicyResponse,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> TenantDetailResponse:
    """Update the isolation policy for a registered tenant."""
    from src.governance.multi_tenant import TenantIsolationPolicy

    _require_operator(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    tenant_id = _validate_tenant_id(tenant_id)
    reg = get_tenant_registry()
    tenant = _require_registered_tenant(reg, tenant_id)
    policy = reg.update_policy(
        tenant_id,
        TenantIsolationPolicy(
            workspace_isolation=request.workspace_isolation,
            data_isolation=request.data_isolation,
            skill_sharing=request.skill_sharing,
            max_concurrent_workspaces=request.max_concurrent_workspaces,
            max_agents_per_workspace=request.max_agents_per_workspace,
        ),
    )
    return TenantDetailResponse(tenant=_tenant_to_response(tenant), policy=_policy_to_response(policy))


@router.delete("/{tenant_id}", status_code=204)
async def delete_tenant(
    tenant_id: str,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
    x_octoagent_confirmation: str | None = Header(default="", alias="X-OctoAgent-Confirmation"),
) -> None:
    """Deregister a tenant from the persisted governance registry."""
    _require_operator(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    if not confirmation_matches("DELETE TENANT", x_octoagent_confirmation):
        raise HTTPException(status_code=409, detail="Tenant deletion requires confirmation: CONFIRM DELETE TENANT")
    tenant_id = _validate_tenant_id(tenant_id)
    if tenant_id == "default":
        raise HTTPException(status_code=400, detail="Default tenant cannot be deleted")
    if not get_tenant_registry().deregister(tenant_id):
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")


@router.get("/{tenant_id}", response_model=TenantDetailResponse)
async def get_tenant(tenant_id: str) -> TenantDetailResponse:
    """Get detail for a specific tenant including its isolation policy."""
    tenant_id = _validate_tenant_id(tenant_id)
    reg = get_tenant_registry()
    tenant = _require_registered_tenant(reg, tenant_id)
    return TenantDetailResponse(
        tenant=_tenant_to_response(tenant),
        policy=_policy_to_response(reg.get_policy(tenant_id)),
    )


@router.get("/{tenant_id}/limits/workspaces", response_model=LimitCheckResponse)
async def check_workspace_limit(
    tenant_id: str,
    current_count: int = Query(default=0, ge=0),
) -> LimitCheckResponse:
    """Check whether the tenant can create another workspace."""
    tenant_id = _validate_tenant_id(tenant_id)
    reg = get_tenant_registry()
    _require_registered_tenant(reg, tenant_id)
    policy = reg.get_policy(tenant_id)
    allowed = reg.enforce_workspace_limit(tenant_id, current_count)
    return LimitCheckResponse(
        tenant_id=tenant_id,
        check="workspace",
        current_count=current_count,
        allowed=allowed,
        limit=policy.max_concurrent_workspaces,
    )


@router.get("/{tenant_id}/limits/agents", response_model=LimitCheckResponse)
async def check_agent_limit(
    tenant_id: str,
    current_count: int = Query(default=0, ge=0),
) -> LimitCheckResponse:
    """Check whether the tenant can spawn another agent."""
    tenant_id = _validate_tenant_id(tenant_id)
    reg = get_tenant_registry()
    _require_registered_tenant(reg, tenant_id)
    policy = reg.get_policy(tenant_id)
    allowed = reg.enforce_agent_limit(tenant_id, current_count)
    return LimitCheckResponse(
        tenant_id=tenant_id,
        check="agent",
        current_count=current_count,
        allowed=allowed,
        limit=policy.max_agents_per_workspace,
    )
