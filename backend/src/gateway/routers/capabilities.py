import logging
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from src.gateway.security import require_operator_or_403
from src.tools.capability import (
    UnifiedCapabilityItem,
    UnifiedCapabilityRegistrySnapshot,
    UnifiedCapabilitySummary,
    get_capability_core_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["capabilities"])

CapabilityCategory = Literal["skills", "agents", "instructions", "hooks", "mcp"]


class CapabilityInventoryResponse(BaseModel):
    source_root: str
    target_root: str
    source: dict[CapabilityCategory, list[str]]
    installed: dict[CapabilityCategory, list[str]]
    matched: dict[CapabilityCategory, list[str]]


class CapabilityMigrationRequest(BaseModel):
    categories: list[CapabilityCategory] | None = Field(default=None)


class CapabilityMigrationResult(BaseModel):
    category: CapabilityCategory
    name: str
    status: Literal["installed", "updated", "skipped", "error"]
    message: str


class CapabilityMigrationCategorySummary(BaseModel):
    category: CapabilityCategory
    source_total: int = 0
    installed_before: int = 0
    installed_after: int = 0
    matched_before: int = 0
    matched_after: int = 0
    pending_before: int = 0
    pending_after: int = 0
    installed_delta: int = 0
    matched_delta: int = 0
    installed_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    error_count: int = 0


class CapabilityMigrationSummary(BaseModel):
    total_results: int = 0
    changed_count: int = 0
    success_count: int = 0
    error_count: int = 0
    pending_after: int = 0
    matched_delta: int = 0
    categories: dict[CapabilityCategory, CapabilityMigrationCategorySummary] = Field(default_factory=dict)


class CapabilityMigrationResponse(BaseModel):
    success: bool
    results: list[CapabilityMigrationResult]
    previous_inventory: CapabilityInventoryResponse
    inventory: CapabilityInventoryResponse
    summary: CapabilityMigrationSummary


class CapabilityHookRuntimeResponse(BaseModel):
    total_hooks: int = 0
    enabled_hooks: int = 0
    total_webhooks: int = 0
    enabled_webhooks: int = 0


class CapabilityCompatRuntimeResponse(BaseModel):
    enabled: bool = False
    source_root: str | None = None
    trust_level: Literal["untrusted", "trusted"] = "untrusted"
    configured_items: int = 0


class CapabilityRuntimeStateResponse(BaseModel):
    source_root: str
    target_root: str
    cache_state: Literal["warm", "cold"]
    listeners_registered: bool
    last_inventory_built_at: str | None = None
    last_migration_at: str | None = None
    total_source_items: int = 0
    total_installed_items: int = 0
    total_matched_items: int = 0
    hook_runtime: CapabilityHookRuntimeResponse
    agent_skills_compat: CapabilityCompatRuntimeResponse = Field(default_factory=CapabilityCompatRuntimeResponse)


class CapabilityAuditEventResponse(BaseModel):
    event: str
    created_at: str
    details: dict[str, object] = Field(default_factory=dict)


class CapabilityAuditResponse(BaseModel):
    event_count: int = 0
    recent_events: list[CapabilityAuditEventResponse] = Field(default_factory=list)
    last_migration_summary: CapabilityMigrationSummary | None = None
    last_migration_at: str | None = None


class CapabilityRegistryResponse(UnifiedCapabilityRegistrySnapshot):
    items: list[UnifiedCapabilityItem] = Field(default_factory=list)
    summary: UnifiedCapabilitySummary


class CapabilityBindingContractItemResponse(BaseModel):
    capability_id: str
    kind: str
    name: str
    display_name: str
    provider: str
    source: str = ""
    enabled: bool = False
    installed: bool = False
    configurable: bool = False
    bindable_targets: list[str] = Field(default_factory=list)
    dispatch_contract: dict[str, object] = Field(default_factory=dict)
    audit_state: dict[str, object] = Field(default_factory=dict)
    operator_policy: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class CapabilityBindingContractSummaryResponse(BaseModel):
    total_items: int = 0
    enabled_items: int = 0
    blocked_items: int = 0
    by_kind: dict[str, int] = Field(default_factory=dict)


class CapabilityBindingContractResponse(BaseModel):
    generated_at: str | None = None
    summary: CapabilityBindingContractSummaryResponse
    items: list[CapabilityBindingContractItemResponse] = Field(default_factory=list)


class CapabilityPolicyUpdateRequest(BaseModel):
    decision: Literal["inherit", "allow", "deny", "audit_only"] = "inherit"
    reason: str = ""
    operator: str = "operator"


class CapabilityPolicyStateResponse(BaseModel):
    policy_path: str
    policies: list[dict[str, object]] = Field(default_factory=list)
    audit_events: list[dict[str, object]] = Field(default_factory=list)
    summary: dict[str, object] = Field(default_factory=dict)


class CapabilityPolicyImportRequest(BaseModel):
    payload: dict[str, object] = Field(default_factory=dict)
    operator: str = "operator"
    reason: str = "imported_policy_state"


class CapabilityPolicyExportResponse(BaseModel):
    version: str
    policy_path: str
    generated_at: str
    state: dict[str, object]
    signature_algorithm: str
    signature: str


class CapabilityPolicyPrecheckResponse(BaseModel):
    ok: bool
    policy_count: int = 0
    deny_count: int = 0
    audit_only_count: int = 0
    signature: str = ""
    recommendations: list[str] = Field(default_factory=list)


class CapabilityToggleRequest(BaseModel):
    enabled: bool = Field(..., description="Whether this capability should be configured as enabled")


class CapabilityCompatSettingsRequest(BaseModel):
    enabled: bool | None = Field(default=None)
    trust_level: Literal["untrusted", "trusted"] | None = Field(default=None)


class CapabilityCompatConflictResponse(BaseModel):
    capability_id: str
    kind: str
    name: str
    provider: str
    source: str
    reason: str


class CapabilityCompatPreviewItemResponse(BaseModel):
    capability_id: str
    kind: str
    name: str
    display_name: str
    description: str = ""
    source: str = ""
    configured_enabled: bool = False
    projected_enabled: bool = False
    trusted: bool = True
    toggleable: bool = False
    activation_blockers: list[str] = Field(default_factory=list)
    conflicts: list[CapabilityCompatConflictResponse] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class CapabilityCompatPreviewResponse(BaseModel):
    enabled: bool = False
    source_root: str | None = None
    trust_level: Literal["untrusted", "trusted"] = "untrusted"
    total_items: int = 0
    conflict_count: int = 0
    blocked_count: int = 0
    configurable_count: int = 0
    items: list[CapabilityCompatPreviewItemResponse] = Field(default_factory=list)


@router.get("/capabilities/inventory", response_model=CapabilityInventoryResponse)
async def get_capability_inventory() -> CapabilityInventoryResponse:
    try:
        return CapabilityInventoryResponse.model_validate(get_capability_core_service().build_inventory())
    except Exception as exc:
        logger.error("Failed to build capability inventory: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read capability inventory: {exc}") from exc


@router.post("/capabilities/migrate", response_model=CapabilityMigrationResponse)
async def migrate_capabilities(
    request: CapabilityMigrationRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> CapabilityMigrationResponse:
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    try:
        result = await get_capability_core_service().migrate_capabilities(request.categories)
        return CapabilityMigrationResponse.model_validate(
            result,
        )
    except Exception as exc:
        logger.error("Capability migration failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Capability migration failed: {exc}") from exc


@router.get("/capabilities/runtime-state", response_model=CapabilityRuntimeStateResponse)
async def get_capability_runtime_state() -> CapabilityRuntimeStateResponse:
    try:
        return CapabilityRuntimeStateResponse.model_validate(get_capability_core_service().build_runtime_state())
    except Exception as exc:
        logger.error("Failed to build capability runtime state: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read capability runtime state: {exc}") from exc


@router.get("/capabilities/audit", response_model=CapabilityAuditResponse)
async def get_capability_audit() -> CapabilityAuditResponse:
    try:
        return CapabilityAuditResponse.model_validate(get_capability_core_service().build_audit_state())
    except Exception as exc:
        logger.error("Failed to build capability audit state: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read capability audit state: {exc}") from exc


@router.get("/capabilities/registry", response_model=CapabilityRegistryResponse)
async def get_capability_registry() -> CapabilityRegistryResponse:
    try:
        return CapabilityRegistryResponse.model_validate(get_capability_core_service().build_registry_snapshot())
    except Exception as exc:
        logger.error("Failed to build capability registry: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read capability registry: {exc}",
        ) from exc


@router.get("/capabilities/binding-contract", response_model=CapabilityBindingContractResponse)
async def get_capability_binding_contract() -> CapabilityBindingContractResponse:
    try:
        return CapabilityBindingContractResponse.model_validate(get_capability_core_service().build_binding_contract())
    except Exception as exc:
        logger.error("Failed to build capability binding contract: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read capability binding contract: {exc}",
        ) from exc


@router.get("/capabilities/policies", response_model=CapabilityPolicyStateResponse)
async def get_capability_policies() -> CapabilityPolicyStateResponse:
    try:
        from src.tools.capability import get_capability_policy_service

        return CapabilityPolicyStateResponse.model_validate(get_capability_policy_service().list_state())
    except Exception as exc:
        logger.error("Failed to read capability policies: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read capability policies: {exc}") from exc


@router.get("/capabilities/policies/export", response_model=CapabilityPolicyExportResponse)
async def export_capability_policies(
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="admin", alias="X-OctoAgent-Operator-Role"),
) -> CapabilityPolicyExportResponse:
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token, minimum="admin")
    try:
        from src.tools.capability import get_capability_policy_service

        return CapabilityPolicyExportResponse.model_validate(get_capability_policy_service().export_state())
    except Exception as exc:
        logger.error("Failed to export capability policies: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to export capability policies: {exc}") from exc


@router.post("/capabilities/policies/import", response_model=CapabilityPolicyStateResponse)
async def import_capability_policies(
    request: CapabilityPolicyImportRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="admin", alias="X-OctoAgent-Operator-Role"),
) -> CapabilityPolicyStateResponse:
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token, minimum="admin")
    try:
        from src.tools.capability import get_capability_policy_service

        return CapabilityPolicyStateResponse.model_validate(
            get_capability_policy_service().import_state(
                request.payload,
                operator=request.operator,
                reason=request.reason,
            )
        )
    except Exception as exc:
        logger.error("Failed to import capability policies: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to import capability policies: {exc}") from exc


@router.get("/capabilities/policies/precheck", response_model=CapabilityPolicyPrecheckResponse)
async def precheck_capability_policies() -> CapabilityPolicyPrecheckResponse:
    try:
        from src.tools.capability import get_capability_policy_service

        state = get_capability_policy_service().list_state()
        export = get_capability_policy_service().export_state()
        policies = state.get("policies") if isinstance(state.get("policies"), list) else []
        deny_count = sum(1 for policy in policies if isinstance(policy, dict) and policy.get("decision") == "deny")
        audit_only_count = sum(1 for policy in policies if isinstance(policy, dict) and policy.get("decision") == "audit_only")
        recommendations: list[str] = []
        if audit_only_count:
            recommendations.append("Review audit_only policies before release promotion.")
        return CapabilityPolicyPrecheckResponse(
            ok=True,
            policy_count=len(policies),
            deny_count=deny_count,
            audit_only_count=audit_only_count,
            signature=str(export.get("signature") or ""),
            recommendations=recommendations,
        )
    except Exception as exc:
        logger.error("Failed to precheck capability policies: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to precheck capability policies: {exc}") from exc


@router.put("/capabilities/policies/{capability_id:path}", response_model=CapabilityPolicyStateResponse)
async def update_capability_policy(
    capability_id: str,
    request: CapabilityPolicyUpdateRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> CapabilityPolicyStateResponse:
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    try:
        from src.tools.capability import get_capability_policy_service

        current_item = get_capability_core_service()._registry_item_by_id(capability_id)  # noqa: SLF001
        if current_item is None:
            raise HTTPException(status_code=404, detail=f"Capability '{capability_id}' not found")
        service = get_capability_policy_service()
        service.set_policy(
            capability_id,
            request.decision,
            reason=request.reason,
            operator=request.operator,
            tenant_id=(x_tenant_id or "default").strip() or "default",
        )
        return CapabilityPolicyStateResponse.model_validate(service.list_state())
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update capability policy: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update capability policy: {exc}") from exc


@router.put("/capabilities/registry/{capability_id:path}", response_model=UnifiedCapabilityItem)
async def update_capability_state(
    capability_id: str,
    request: CapabilityToggleRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> UnifiedCapabilityItem:
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    try:
        updated = await get_capability_core_service().update_capability_enabled(
            capability_id,
            request.enabled,
        )
        return UnifiedCapabilityItem.model_validate(updated)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to update capability state: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update capability state: {exc}") from exc


@router.get("/capabilities/compat/preview", response_model=CapabilityCompatPreviewResponse)
async def get_capability_compat_preview() -> CapabilityCompatPreviewResponse:
    try:
        return CapabilityCompatPreviewResponse.model_validate(get_capability_core_service().build_agent_skills_compat_preview())
    except Exception as exc:
        logger.error("Failed to build capability compat preview: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to build compat preview: {exc}") from exc


@router.put("/capabilities/compat/settings", response_model=CapabilityCompatPreviewResponse)
async def update_capability_compat_settings(
    request: CapabilityCompatSettingsRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> CapabilityCompatPreviewResponse:
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    try:
        payload = await get_capability_core_service().update_agent_skills_compat_settings(
            enabled=request.enabled,
            trust_level=request.trust_level,
        )
        return CapabilityCompatPreviewResponse.model_validate(payload)
    except Exception as exc:
        logger.error("Failed to update capability compat settings: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update compat settings: {exc}") from exc


class CacheInvalidateResponse(BaseModel):
    invalidated: bool
    message: str


@router.post("/capabilities/invalidate-cache", response_model=CacheInvalidateResponse)
async def invalidate_capability_cache(
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> CacheInvalidateResponse:
    """Force-invalidate the in-memory capability inventory cache.

    The next call to /capabilities/inventory will re-read from disk.
    """
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    svc = get_capability_core_service()
    svc._cached_inventory = None  # noqa: SLF001
    logger.info("Capability inventory cache invalidated via operator request")
    return CacheInvalidateResponse(invalidated=True, message="Inventory cache cleared; next request will rebuild from disk.")


class CategoryDetailItem(BaseModel):
    name: str
    in_source: bool
    installed: bool
    matched: bool


class CategoryDetailResponse(BaseModel):
    category: str
    items: list[CategoryDetailItem] = Field(default_factory=list)
    source_count: int = 0
    installed_count: int = 0
    matched_count: int = 0


@router.get("/capabilities/{category}", response_model=CategoryDetailResponse)
async def get_capability_category(category: CapabilityCategory) -> CategoryDetailResponse:
    """Return per-item detail for a single capability category."""
    try:
        inv = get_capability_core_service().build_inventory()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    source_set = set(inv["source"].get(category, []))
    installed_set = set(inv["installed"].get(category, []))
    matched_set = set(inv["matched"].get(category, []))
    all_names = sorted(source_set | installed_set)

    items = [
        CategoryDetailItem(
            name=name,
            in_source=name in source_set,
            installed=name in installed_set,
            matched=name in matched_set,
        )
        for name in all_names
    ]
    return CategoryDetailResponse(
        category=category,
        items=items,
        source_count=len(source_set),
        installed_count=len(installed_set),
        matched_count=len(matched_set),
    )
