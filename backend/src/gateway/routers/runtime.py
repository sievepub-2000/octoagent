import json
import os
import shutil
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.config import get_app_config
from src.config.integrations_config import get_integrations_config
from src.config.paths import get_setup_state_file, resolve_configured_default_model_name
from src.config.subagents_config import get_subagents_app_config
from src.models.factory import EMBEDDED_BACKUP_MODEL_NAME, embedded_backup_enabled
from src.subagents.executor import get_subagent_runtime_snapshot
from src.system_execution import get_system_execution_service
from src.system_guard.service import get_system_guard_service

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


def _coerce_available_memory(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


class RuntimeModelCapability(BaseModel):
    name: str = Field(..., description="Model name")
    display_name: str | None = Field(None, description="Human-readable model name")
    supports_thinking: bool = Field(default=False, description="Whether the model supports thinking mode")
    supports_reasoning_effort: bool = Field(default=False, description="Whether the model supports reasoning effort controls")
    fallback_models: list[str] = Field(
        default_factory=list,
        description="Ordered fallback model names configured for this model.",
    )
    max_context_tokens: int | None = Field(
        default=None,
        description="Declared max context window, if configured.",
    )
    effective_fallback_models: list[str] = Field(
        default_factory=list,
        description="Ordered effective fallback chain including runtime-provided emergency backups.",
    )
    embedded_backup_available: bool = Field(
        default=False,
        description="Whether the built-in embedded emergency backup model is enabled for this model path.",
    )
    degraded_mode_supported: bool = Field(
        default=False,
        description="Whether this model path can continue in degraded mode through a configured fallback chain.",
    )


class RuntimeAgentLimits(BaseModel):
    max_concurrent_subagents: int
    max_active_subagents_per_thread: int
    max_total_subagents_per_thread: int
    memory_guard_enabled: bool
    min_available_memory_gb: float
    estimated_memory_per_subagent_gb: float
    recommended_max_parallel_branches: int
    recommended_max_agents_per_workflow: int


class RuntimeStatus(BaseModel):
    active_subagents: int
    available_memory_gb: float | None = None
    memory_guard_state: str
    jobs_by_status: dict[str, int] = Field(default_factory=dict)
    thread_active_counts: dict[str, int] = Field(default_factory=dict)
    jobs_by_agent: dict[str, int] = Field(default_factory=dict)
    timed_out_count: int = 0
    rejected_count: int = 0
    recent_failures: list[dict] = Field(default_factory=list)


class RuntimeCapabilitiesResponse(BaseModel):
    default_model: str | None = None
    embedded_backup_model: str | None = None
    embedded_backup_enabled: bool = False
    models: list[RuntimeModelCapability]
    agent_limits: RuntimeAgentLimits
    runtime_status: RuntimeStatus


class SystemGuardStatusResponse(BaseModel):
    latest_snapshot: dict | None = None
    recent_snapshots: list[dict] = Field(default_factory=list)
    retention: dict = Field(default_factory=dict)


class SystemGuardRepairRequest(BaseModel):
    advisory_only: bool = Field(
        default=False,
        description="When true, only generate the repair advisory without executing built-in repair actions.",
    )


class SystemGuardRepairResponse(BaseModel):
    ok: bool
    issues: list[dict] = Field(default_factory=list)
    repair_report: dict = Field(default_factory=dict)
    persisted: dict | None = None
    session_id: str | None = None


class SystemGuardExportResponse(BaseModel):
    namespace: str
    generated_at: str
    latest_snapshot: dict | None = None
    recent_snapshots: list[dict] = Field(default_factory=list)
    retention: dict = Field(default_factory=dict)
    signed: bool
    signature_algorithm: str
    signature: str


class RuntimeDoctorCheck(BaseModel):
    id: str
    title: str
    status: str
    detail: str
    recommendation: str | None = None


class RuntimeDoctorResponse(BaseModel):
    overall_status: str
    checks: list[RuntimeDoctorCheck] = Field(default_factory=list)


class RuntimeLongRunningHealthResponse(BaseModel):
    snapshot: dict[str, Any] = Field(default_factory=dict)


class LangGraphContractPruneRequest(BaseModel):
    max_checkpoints_per_thread: int = Field(default=20, ge=1, le=500)
    max_runs_per_thread: int = Field(default=100, ge=1, le=1000)
    remote_thread_ids: list[str] = Field(default_factory=list)
    remote_strategy: str = "delete"


class LangGraphContractCopyRequest(BaseModel):
    source_thread_id: str
    target_thread_id: str
    target_task_id: str | None = None
    remote: bool = False


class RuntimeMaintenanceRunRequest(BaseModel):
    max_checkpoints_per_thread: int | None = Field(default=None, ge=1, le=500)
    max_runs_per_thread: int | None = Field(default=None, ge=1, le=1000)


class LangGraphLifecycleRequest(BaseModel):
    action: Literal["pause", "resume", "cancel", "replay", "terminate"]
    run_id: str | None = None
    actor: str = "operator"
    reason: str = ""
    remote: bool = False


def _resolve_effective_fallback_models(configured_fallbacks: list[str]) -> list[str]:
    effective = list(configured_fallbacks)
    if embedded_backup_enabled():
        effective.append(EMBEDDED_BACKUP_MODEL_NAME)
    return list(dict.fromkeys(effective))


@router.get(
    "/capabilities",
    response_model=RuntimeCapabilitiesResponse,
    summary="Get Runtime Capabilities",
    description="Expose lightweight runtime guardrails for workflow planning, model fallback, and local deployment safety.",
)
async def get_runtime_capabilities() -> RuntimeCapabilitiesResponse:
    app_config = get_app_config()
    subagents_config = get_subagents_app_config()
    runtime_snapshot = get_subagent_runtime_snapshot()
    default_model_name = resolve_configured_default_model_name(
        model.name for model in app_config.models
    )

    recommended_parallel = min(
        subagents_config.max_concurrent_subagents,
        subagents_config.max_active_subagents_per_thread,
    )
    recommended_agents = min(
        subagents_config.max_total_subagents_per_thread,
        max(3, recommended_parallel + 2),
    )

    available_memory_gb = _coerce_available_memory(runtime_snapshot.get("available_memory_gb"))
    required_memory_gb = (
        subagents_config.min_available_memory_gb
        + subagents_config.estimated_memory_per_subagent_gb
    )
    if not subagents_config.enable_system_memory_guard:
        memory_guard_state = "disabled"
    elif available_memory_gb is None:
        memory_guard_state = "unknown"
    elif available_memory_gb < required_memory_gb:
        memory_guard_state = "tight"
    else:
        memory_guard_state = "ok"

    return RuntimeCapabilitiesResponse(
        default_model=default_model_name,
        embedded_backup_model=EMBEDDED_BACKUP_MODEL_NAME if embedded_backup_enabled() else None,
        embedded_backup_enabled=embedded_backup_enabled(),
        models=[
            RuntimeModelCapability(
                name=model.name,
                display_name=model.display_name,
                supports_thinking=model.supports_thinking,
                supports_reasoning_effort=model.supports_reasoning_effort,
                fallback_models=model.fallback_models,
                max_context_tokens=model.max_context_tokens,
                effective_fallback_models=_resolve_effective_fallback_models(model.fallback_models),
                embedded_backup_available=embedded_backup_enabled(),
                degraded_mode_supported=bool(
                    model.fallback_models or embedded_backup_enabled()
                ),
            )
            for model in app_config.models
        ],
        agent_limits=RuntimeAgentLimits(
            max_concurrent_subagents=subagents_config.max_concurrent_subagents,
            max_active_subagents_per_thread=subagents_config.max_active_subagents_per_thread,
            max_total_subagents_per_thread=subagents_config.max_total_subagents_per_thread,
            memory_guard_enabled=subagents_config.enable_system_memory_guard,
            min_available_memory_gb=subagents_config.min_available_memory_gb,
            estimated_memory_per_subagent_gb=subagents_config.estimated_memory_per_subagent_gb,
            recommended_max_parallel_branches=recommended_parallel,
            recommended_max_agents_per_workflow=recommended_agents,
        ),
        runtime_status=RuntimeStatus(
            active_subagents=runtime_snapshot["active_subagents"],
            available_memory_gb=available_memory_gb,
            memory_guard_state=memory_guard_state,
            jobs_by_status=runtime_snapshot.get("jobs_by_status", {}),
            thread_active_counts=runtime_snapshot.get("thread_active_counts", {}),
            jobs_by_agent=runtime_snapshot.get("jobs_by_agent", {}),
            timed_out_count=int(runtime_snapshot.get("timed_out_count", 0) or 0),
            rejected_count=int(runtime_snapshot.get("rejected_count", 0) or 0),
            recent_failures=runtime_snapshot.get("recent_failures", []),
        ),
    )


@router.get(
    "/system-guard/status",
    response_model=SystemGuardStatusResponse,
    summary="Get System Guard Status",
    description="Expose latest startup/shutdown self-check snapshots persisted by system guard.",
)
async def get_system_guard_status(limit: int = 10) -> SystemGuardStatusResponse:
    service = get_system_guard_service()
    bounded_limit = max(1, min(limit, 100))
    return SystemGuardStatusResponse(
        latest_snapshot=service.latest_snapshot(),
        recent_snapshots=service.recent_snapshots(limit=bounded_limit),
        retention=service.retention_summary(),
    )


@router.post(
    "/system-guard/repair",
    response_model=SystemGuardRepairResponse,
    summary="Run System Guard Repair",
    description="Trigger a manual system-guard repair pass and persist the resulting lifecycle snapshot.",
)
async def run_system_guard_repair(
    request: SystemGuardRepairRequest,
) -> SystemGuardRepairResponse:
    service = get_system_guard_service()
    result = service.run_manual_repair(advisory_only=request.advisory_only)
    return SystemGuardRepairResponse(**result)


@router.get(
    "/system-guard/export",
    response_model=SystemGuardExportResponse,
    summary="Export System Guard Snapshots",
    description="Export recent system-guard lifecycle snapshots with an integrity signature for offline analysis.",
)
async def export_system_guard_snapshots(limit: int = 20) -> SystemGuardExportResponse:
    service = get_system_guard_service()
    try:
        result = service.export_snapshots(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SystemGuardExportResponse(**result)


@router.get(
    "/doctor",
    response_model=RuntimeDoctorResponse,
    summary="Run Runtime Doctor",
    description="Expose a lightweight operator preflight over setup, models, system-execution policy, and host binary availability.",
)
async def get_runtime_doctor() -> RuntimeDoctorResponse:
    app_config = get_app_config()
    integrations = get_integrations_config()
    policy = get_system_execution_service().get_permission_policy()

    checks: list[RuntimeDoctorCheck] = []

    config_path = app_config.resolve_config_path()
    if config_path.exists():
        checks.append(RuntimeDoctorCheck(id="config", title="Config file", status="ok", detail=str(config_path)))
    else:
        checks.append(
            RuntimeDoctorCheck(
                id="config",
                title="Config file",
                status="fail",
                detail=f"Missing config file at {config_path}",
                recommendation="Create config.yaml from config.example.yaml before starting the stack.",
            )
        )

    setup_state_file = get_setup_state_file()
    setup_workspace_path = ""
    if setup_state_file.exists():
        try:
            state = json.loads(setup_state_file.read_text(encoding="utf-8"))
            setup_workspace_path = str(state.get("workspace_path") or "")
        except Exception:
            setup_workspace_path = ""
    if setup_workspace_path:
        checks.append(
            RuntimeDoctorCheck(
                id="workspace",
                title="Setup workspace",
                status="ok" if Path(setup_workspace_path).exists() else "warn",
                detail=setup_workspace_path,
                recommendation=None if Path(setup_workspace_path).exists() else "Re-run setup or create the configured workspace path.",
            )
        )
    else:
        checks.append(
            RuntimeDoctorCheck(
                id="workspace",
                title="Setup workspace",
                status="warn",
                detail="No persisted setup workspace path found.",
                recommendation="Run the setup wizard to persist workspace defaults.",
            )
        )

    if app_config.models:
        checks.append(
            RuntimeDoctorCheck(
                id="models",
                title="Configured models",
                status="ok",
                detail=f"{len(app_config.models)} model(s) configured.",
            )
        )
    else:
        checks.append(
            RuntimeDoctorCheck(
                id="models",
                title="Configured models",
                status="fail",
                detail="No models are configured.",
                recommendation="Add at least one model entry before using chat or workflows.",
            )
        )

    checks.append(
        RuntimeDoctorCheck(
            id="system-execution",
            title="System execution",
            status="ok" if integrations.system_execution.enabled else "warn",
            detail=(
                f"engine={integrations.system_execution.engine}, system_cli_enabled={integrations.system_execution.system_cli_enabled}, "
                f"rules={len(policy.rules)}"
            ),
            recommendation=None if integrations.system_execution.enabled else "Enable integrations.system_execution if operator CLI flows are required.",
        )
    )

    try:
        from src.capability_core import get_capability_core_service

        capability_service = get_capability_core_service()
        registry = capability_service.build_registry_snapshot()
        contract = capability_service.build_binding_contract()
        registry_total = int((registry.get("summary") or {}).get("total_items") or 0)
        contract_total = int((contract.get("summary") or {}).get("total_items") or 0)
        by_kind = (registry.get("summary") or {}).get("by_kind") or {}
        checks.append(
            RuntimeDoctorCheck(
                id="capability-registry",
                title="Capability registry",
                status="ok" if registry_total > 0 else "fail",
                detail=f"items={registry_total}, kinds={by_kind}",
                recommendation=None if registry_total > 0 else "Capability registry returned no items; check skills/plugins/MCP/channel loading.",
            )
        )
        checks.append(
            RuntimeDoctorCheck(
                id="capability-binding-contract",
                title="Capability binding contract",
                status="ok" if contract_total == registry_total and contract_total > 0 else "fail",
                detail=f"contract_items={contract_total}, registry_items={registry_total}",
                recommendation=None if contract_total == registry_total and contract_total > 0 else "Binding contract should cover every registry item.",
            )
        )
    except Exception as exc:
        checks.append(
            RuntimeDoctorCheck(
                id="capability-registry",
                title="Capability registry",
                status="fail",
                detail=str(exc),
                recommendation="Inspect CapabilityCore registry construction and extension config loading.",
            )
        )

    try:
        from src.channels.service import ChannelService, get_channel_service

        channel_service = get_channel_service() or ChannelService.from_app_config()
        channel_status = channel_service.get_status()
        channels = channel_status.get("channels") if isinstance(channel_status, dict) else {}
        channel_count = len(channels) if isinstance(channels, dict) else 0
        enabled_count = sum(1 for item in (channels or {}).values() if isinstance(item, dict) and item.get("enabled"))
        checks.append(
            RuntimeDoctorCheck(
                id="channels",
                title="Channel registry",
                status="ok" if channel_count > 0 else "warn",
                detail=f"channels={channel_count}, enabled={enabled_count}, service_running={bool(channel_status.get('service_running'))}",
                recommendation=None if channel_count > 0 else "No channel registry entries were discovered.",
            )
        )
    except Exception as exc:
        checks.append(
            RuntimeDoctorCheck(
                id="channels",
                title="Channel registry",
                status="warn",
                detail=str(exc),
                recommendation="Inspect channel configuration if IM ingress is required.",
            )
        )

    try:
        from src.agent_runtime import get_agent_runtime_manager

        runtime_manager = get_agent_runtime_manager()
        provider_health = runtime_manager.provider_health()
        default_provider = runtime_manager.resolve_provider_name()
        default_status = provider_health.get(default_provider)
        if isinstance(default_status, dict):
            default_available = bool(default_status.get("available"))
        else:
            default_available = bool(getattr(default_status, "available", False)) if default_status is not None else False
        checks.append(
            RuntimeDoctorCheck(
                id="runtime-provider",
                title="Runtime provider",
                status="ok" if default_available else "warn",
                detail=f"default={default_provider}, providers={list(provider_health.keys())}",
                recommendation=None if default_available else "Verify LangGraph SDK/runtime configuration before running workflows.",
            )
        )
    except Exception as exc:
        checks.append(
            RuntimeDoctorCheck(
                id="runtime-provider",
                title="Runtime provider",
                status="warn",
                detail=str(exc),
                recommendation="Inspect agent runtime provider configuration.",
            )
        )

    try:
        pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        available_gb = (pages * page_size) / (1024 ** 3)
        checks.append(
            RuntimeDoctorCheck(
                id="host-memory",
                title="Host available memory",
                status="ok" if available_gb >= 2 else "warn",
                detail=f"available_gb={available_gb:.2f}",
                recommendation=None if available_gb >= 2 else "Reduce workflow concurrency or enable stronger memory guard settings.",
            )
        )
    except Exception:
        pass

    try:
        from src.runtime_governance import collect_runtime_governance_snapshot_async

        governance = await collect_runtime_governance_snapshot_async()
        disk = governance.get("disk", {})
        worker = governance.get("worker_isolation", {})
        langgraph_contract = governance.get("langgraph_contract", {})
        event_loop = governance.get("event_loop", {})
        disk_free_gb = float(disk.get("free_gb") or 0)
        queue_depth = int(worker.get("total_queued") or 0)
        checkpoint_count = int(langgraph_contract.get("checkpoint_count") or 0)
        active_runs = int(langgraph_contract.get("active_runs") or 0)
        event_loop_latency_ms = float(event_loop.get("latency_ms") or 0)
        checks.append(
            RuntimeDoctorCheck(
                id="runtime-disk",
                title="Runtime disk",
                status="ok" if disk_free_gb >= 2 else "warn",
                detail=(
                    f"path={disk.get('path')}, free_gb={disk_free_gb:.2f}, "
                    f"used_percent={disk.get('used_percent')}"
                ),
                recommendation=None if disk_free_gb >= 2 else "Prune checkpoints/artifacts or expand runtime storage.",
            )
        )
        checks.append(
            RuntimeDoctorCheck(
                id="runtime-queues",
                title="Runtime worker queues",
                status="ok" if queue_depth == 0 else "warn",
                detail=f"active={worker.get('total_active')}, queued={queue_depth}, pools={worker.get('pools')}",
                recommendation=None if queue_depth == 0 else "Reduce workflow concurrency or increase worker isolation limits.",
            )
        )
        checks.append(
            RuntimeDoctorCheck(
                id="langgraph-contract",
                title="LangGraph contract ledger",
                status="ok",
                detail=(
                    f"threads={langgraph_contract.get('thread_count')}, checkpoints={checkpoint_count}, "
                    f"active_runs={active_runs}"
                ),
            )
        )
        checks.append(
            RuntimeDoctorCheck(
                id="event-loop-latency",
                title="Event loop latency",
                status="ok" if event_loop_latency_ms < 100 else "warn",
                detail=f"latency_ms={event_loop_latency_ms:.3f}",
                recommendation=None if event_loop_latency_ms < 100 else "Move blocking work into isolated workers.",
            )
        )
    except Exception as exc:
        checks.append(
            RuntimeDoctorCheck(
                id="runtime-governance",
                title="Runtime governance snapshot",
                status="warn",
                detail=str(exc),
                recommendation="Inspect runtime_governance collection and LangGraph contract ledger state.",
            )
        )

    for binary in ("git", "node", "pnpm", "python3"):
        location = shutil.which(binary)
        checks.append(
            RuntimeDoctorCheck(
                id=f"binary:{binary}",
                title=f"Binary: {binary}",
                status="ok" if location else "warn",
                detail=location or "Not found in PATH",
                recommendation=None if location else f"Install {binary} or ensure it is available in PATH.",
            )
        )

    overall_status = "ok"
    if any(check.status == "fail" for check in checks):
        overall_status = "fail"
    elif any(check.status == "warn" for check in checks):
        overall_status = "warn"
    return RuntimeDoctorResponse(overall_status=overall_status, checks=checks)


@router.get("/long-running-health", response_model=RuntimeLongRunningHealthResponse)
async def get_long_running_health() -> RuntimeLongRunningHealthResponse:
    from src.runtime_governance import collect_runtime_governance_snapshot_async

    return RuntimeLongRunningHealthResponse(
        snapshot=await collect_runtime_governance_snapshot_async()
    )


@router.get("/maintenance/status")
async def get_runtime_maintenance_status() -> dict[str, Any]:
    from src.runtime_governance import get_runtime_maintenance_scheduler

    return get_runtime_maintenance_scheduler().status()


@router.post("/maintenance/run")
async def run_runtime_maintenance(request: RuntimeMaintenanceRunRequest) -> dict[str, Any]:
    from src.runtime_governance import get_runtime_maintenance_scheduler

    scheduler = get_runtime_maintenance_scheduler()
    if request.max_checkpoints_per_thread is not None:
        scheduler.max_checkpoints_per_thread = request.max_checkpoints_per_thread
    if request.max_runs_per_thread is not None:
        scheduler.max_runs_per_thread = request.max_runs_per_thread
    return scheduler.run_once()


@router.get("/langgraph-contract")
async def get_langgraph_contract() -> dict[str, Any]:
    from src.agent_runtime import get_langgraph_workflow_contract_service

    service = get_langgraph_workflow_contract_service()
    payload = service.export_state()
    try:
        payload["remote_capabilities"] = await service.remote_capabilities()
    except Exception as exc:
        payload["remote_capabilities"] = {"error": str(exc)}
    return payload


@router.post("/langgraph-contract/prune")
async def prune_langgraph_contract(request: LangGraphContractPruneRequest) -> dict[str, Any]:
    from src.agent_runtime import get_langgraph_workflow_contract_service

    service = get_langgraph_workflow_contract_service()
    local = service.prune(
        max_checkpoints_per_thread=request.max_checkpoints_per_thread,
        max_runs_per_thread=request.max_runs_per_thread,
    )
    remote: dict[str, Any] | None = None
    if request.remote_thread_ids:
        remote = await service.prune_remote_threads(
            request.remote_thread_ids,
            strategy=request.remote_strategy,
        )
    return {"local": local, "remote": remote}


@router.post("/langgraph-contract/copy")
async def copy_langgraph_contract_thread(request: LangGraphContractCopyRequest) -> dict[str, Any]:
    from src.agent_runtime import get_langgraph_workflow_contract_service

    service = get_langgraph_workflow_contract_service()
    copied = service.copy_thread_contract(
        request.source_thread_id,
        request.target_thread_id,
        target_task_id=request.target_task_id,
    )
    if copied is None:
        raise HTTPException(status_code=404, detail=f"Thread '{request.source_thread_id}' not found")
    payload = copied.model_dump(mode="json")
    if request.remote:
        payload["remote"] = await service.copy_remote_thread(request.source_thread_id)
    return payload


@router.delete("/langgraph-contract/threads/{thread_id}")
async def delete_langgraph_contract_thread(thread_id: str) -> dict[str, Any]:
    from src.agent_runtime import get_langgraph_workflow_contract_service

    service = get_langgraph_workflow_contract_service()
    remote: dict[str, Any] | None = None
    try:
        remote = await service.delete_remote_thread(thread_id)
    except Exception as exc:
        remote = {"ok": False, "error": str(exc)}
    deleted = service.delete_thread_contract(thread_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Thread '{thread_id}' not found")
    return {"deleted": True, "remote": remote}


@router.post("/langgraph-contract/threads/{thread_id}/lifecycle")
async def record_langgraph_workflow_lifecycle(
    thread_id: str,
    request: LangGraphLifecycleRequest,
) -> dict[str, Any]:
    from src.agent_runtime import get_langgraph_workflow_contract_service

    service = get_langgraph_workflow_contract_service()
    remote_result: dict[str, Any] | None = None
    if request.remote:
        try:
            if request.action in {"cancel", "terminate"} and request.run_id:
                from langgraph_sdk import get_client

                base_url = str((await service.remote_capabilities()).get("base_url") or "http://localhost:19884")
                client = get_client(url=base_url)
                remote_result = {
                    "ok": True,
                    "operation": "runs.cancel",
                    "result": await client.runs.cancel(thread_id, request.run_id),
                }
            elif request.action == "replay":
                remote_result = await service.copy_remote_thread(thread_id)
            else:
                remote_result = {
                    "ok": True,
                    "skipped": True,
                    "reason": "no_remote_mapping_for_action",
                    "action": request.action,
                }
        except Exception as exc:
            remote_result = {"ok": False, "error": str(exc), "action": request.action}

    result = service.record_lifecycle_action(
        thread_id=thread_id,
        run_id=request.run_id,
        action=request.action,
        actor=request.actor,
        reason=request.reason,
        remote=remote_result,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=f"Thread '{thread_id}' not found")
    return result


# ---------------------------------------------------------------------------
#  Agent runtime provider health
# ---------------------------------------------------------------------------


class RuntimeProviderStatus(BaseModel):
    available: bool = Field(..., description="Whether the provider SDK is installed and loadable")
    detail: str = Field(default="ok", description="Status detail or error message")
    sdk_info: dict[str, Any] = Field(default_factory=dict, description="SDK version and capability metadata")


class RuntimeProviderHealthResponse(BaseModel):
    default_provider: str = Field(..., description="Currently configured default provider")
    providers: dict[str, RuntimeProviderStatus] = Field(
        default_factory=dict,
        description="Per-provider availability status",
    )


class RuntimeExecutionSnapshotResponse(BaseModel):
    provider: str = Field(..., description="Runtime provider name")
    session_id: str | None = Field(default=None, description="Provider-neutral runtime session identifier")
    execution_target: str | None = Field(default=None, description="Resolved runtime execution target")
    message_count: int = Field(default=0, description="Observed message count")
    tool_call_count: int = Field(default=0, description="Observed tool call count")
    model_name: str | None = Field(default=None, description="Resolved execution model when available")
    status: str = Field(default="completed", description="Last observed execution status")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Provider-specific snapshot metadata")


class RuntimeProviderContractResponse(BaseModel):
    provider: str = Field(..., description="Runtime provider name")
    runtime_kind: str = Field(..., description="Underlying runtime kind")
    session_identifier_kind: str = Field(..., description="Canonical session identifier type")
    execution_target_kind: str = Field(..., description="Canonical execution target type")
    tool_runtime_contract: str = Field(..., description="Tool invocation/runtime contract class")
    supports_subagents: bool = Field(default=False, description="Whether the runtime supports subagent execution")
    supports_thread_reuse: bool = Field(default=False, description="Whether the runtime can resume a prior session/thread")
    sdk_info: dict[str, Any] = Field(default_factory=dict, description="SDK metadata for the provider")
    last_execution: RuntimeExecutionSnapshotResponse | None = Field(default=None, description="Most recent execution snapshot for this provider")


class RuntimeProviderContractsResponse(BaseModel):
    default_provider: str = Field(..., description="Currently configured default provider")
    providers: dict[str, RuntimeProviderContractResponse] = Field(default_factory=dict, description="Per-provider runtime contract metadata")


@router.get("/provider-health", response_model=RuntimeProviderHealthResponse)
async def get_runtime_provider_health() -> RuntimeProviderHealthResponse:
    """Report availability of each registered agent runtime provider."""
    from src.agent_runtime import get_agent_runtime_manager

    manager = get_agent_runtime_manager()
    raw = manager.provider_health()
    default_name = manager.resolve_provider_name()
    return RuntimeProviderHealthResponse(
        default_provider=default_name,
        providers={
            name: RuntimeProviderStatus(
                available=info["available"],
                detail=str(info["detail"]),
                sdk_info=info.get("sdk_info", {}),
            )
            for name, info in raw.items()
        },
    )


@router.get("/provider-contracts", response_model=RuntimeProviderContractsResponse)
async def get_runtime_provider_contracts() -> RuntimeProviderContractsResponse:
    """Report provider-neutral runtime contracts and the latest execution snapshots."""
    from src.agent_runtime import get_agent_runtime_manager

    manager = get_agent_runtime_manager()
    default_name = manager.resolve_provider_name()
    contracts = manager.provider_contracts()
    last_snapshots = manager.last_execution_snapshots()
    providers: dict[str, RuntimeProviderContractResponse] = {}
    for name, contract in contracts.items():
        snapshot = last_snapshots.get(name)
        providers[name] = RuntimeProviderContractResponse(
            provider=contract.provider,
            runtime_kind=contract.runtime_kind,
            session_identifier_kind=contract.session_identifier_kind,
            execution_target_kind=contract.execution_target_kind,
            tool_runtime_contract=contract.tool_runtime_contract,
            supports_subagents=contract.supports_subagents,
            supports_thread_reuse=contract.supports_thread_reuse,
            sdk_info=contract.sdk_info,
            last_execution=(
                RuntimeExecutionSnapshotResponse(
                    provider=snapshot.provider,
                    session_id=snapshot.session_id,
                    execution_target=snapshot.execution_target,
                    message_count=snapshot.message_count,
                    tool_call_count=snapshot.tool_call_count,
                    model_name=snapshot.model_name,
                    status=snapshot.status,
                    metadata=snapshot.metadata,
                )
                if snapshot is not None
                else None
            ),
        )
    return RuntimeProviderContractsResponse(default_provider=default_name, providers=providers)
