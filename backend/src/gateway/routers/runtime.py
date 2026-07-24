import asyncio
import json
import os
import shutil
from datetime import UTC
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.agents.core.run_record_store import build_run_record_summary, list_run_records
from src.agents.subagents.executor import get_subagent_runtime_snapshot
from src.agents.subagents.policy import is_host_memory_oom_critical
from src.models.factory import resolve_effective_fallback_model_names
from src.runtime.config import get_app_config
from src.runtime.config.integrations_config import get_integrations_config
from src.runtime.config.paths import get_setup_state_file, resolve_configured_default_model_name
from src.runtime.config.subagents_config import get_subagents_app_config
from src.runtime.system_guard.service import get_system_guard_service
from src.tools.system_execution import get_system_execution_service


def _resolve_repo_root() -> Path:
    """Resolve the repo root robustly.

    `backend/src/gateway/routers/runtime.py` -> parents[4] = repo root.
    Falls back to ``Path.cwd()``.
    """
    try:
        anchored = Path(__file__).resolve().parents[4]
        if (anchored / "backend").is_dir() and (anchored / "frontend").is_dir():
            return anchored
    except Exception:
        pass
    return Path.cwd()


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
    degraded_mode_supported: bool = Field(
        default=False,
        description="Whether this model path can continue in degraded mode through a configured fallback chain.",
    )


class RuntimeAgentLimits(BaseModel):
    max_concurrent_subagents: int
    max_active_subagents_per_thread: int
    max_total_subagents_per_thread: int
    max_total_subagent_jobs: int
    max_events_per_subagent: int
    max_ai_messages_per_subagent: int
    terminal_job_retention_seconds: int
    memory_guard_enabled: bool
    min_available_memory_gb: float
    oom_critical_available_memory_gb: float
    estimated_memory_per_subagent_gb: float
    recommended_max_parallel_branches: int
    recommended_max_agents_per_workflow: int


class RuntimeStatus(BaseModel):
    active_subagents: int
    retained_jobs: int = 0
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


class RuntimeRunRecordsResponse(BaseModel):
    records: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


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
    default_model_name = resolve_configured_default_model_name(model.name for model in app_config.models)

    recommended_parallel = min(
        subagents_config.max_concurrent_subagents,
        subagents_config.max_active_subagents_per_thread,
    )
    recommended_agents = min(
        subagents_config.max_total_subagents_per_thread,
        max(3, recommended_parallel + 2),
    )

    available_memory_gb = _coerce_available_memory(runtime_snapshot.get("available_memory_gb"))
    if not subagents_config.enable_system_memory_guard:
        memory_guard_state = "disabled"
    elif available_memory_gb is None:
        memory_guard_state = "unknown"
    elif is_host_memory_oom_critical(available_memory_gb):
        memory_guard_state = "tight"
    else:
        memory_guard_state = "ok"

    return RuntimeCapabilitiesResponse(
        default_model=default_model_name,
        models=[
            RuntimeModelCapability(
                name=model.name,
                display_name=model.display_name,
                supports_thinking=model.supports_thinking,
                supports_reasoning_effort=model.supports_reasoning_effort,
                fallback_models=model.fallback_models,
                max_context_tokens=model.max_context_tokens,
                effective_fallback_models=resolve_effective_fallback_model_names(
                    model.name,
                    thinking_enabled=model.supports_thinking,
                ),
                degraded_mode_supported=bool(resolve_effective_fallback_model_names(model.name)),
            )
            for model in app_config.models
        ],
        agent_limits=RuntimeAgentLimits(
            max_concurrent_subagents=subagents_config.max_concurrent_subagents,
            max_active_subagents_per_thread=subagents_config.max_active_subagents_per_thread,
            max_total_subagents_per_thread=subagents_config.max_total_subagents_per_thread,
            max_total_subagent_jobs=subagents_config.max_total_subagent_jobs,
            max_events_per_subagent=subagents_config.max_events_per_subagent,
            max_ai_messages_per_subagent=subagents_config.max_ai_messages_per_subagent,
            terminal_job_retention_seconds=subagents_config.terminal_job_retention_seconds,
            memory_guard_enabled=subagents_config.enable_system_memory_guard,
            min_available_memory_gb=subagents_config.min_available_memory_gb,
            oom_critical_available_memory_gb=subagents_config.oom_critical_available_memory_gb,
            estimated_memory_per_subagent_gb=subagents_config.estimated_memory_per_subagent_gb,
            recommended_max_parallel_branches=recommended_parallel,
            recommended_max_agents_per_workflow=recommended_agents,
        ),
        runtime_status=RuntimeStatus(
            active_subagents=runtime_snapshot["active_subagents"],
            retained_jobs=int(runtime_snapshot.get("retained_jobs", 0) or 0),
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
    "/run-records",
    response_model=RuntimeRunRecordsResponse,
    summary="List Runtime Run Records",
    description="Return recent auditable agent run records for operator observability.",
)
async def get_runtime_run_records(
    limit: int = 50,
    thread_id: str | None = None,
) -> RuntimeRunRecordsResponse:
    bounded_limit = max(1, min(limit, 200))
    records = list_run_records(limit=bounded_limit, thread_id=thread_id)
    return RuntimeRunRecordsResponse(
        records=records,
        summary=build_run_record_summary(records),
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
    if setup_workspace_path and not Path(setup_workspace_path).exists():
        # A setup snapshot created on the host can contain the host-side
        # checkout path. In a container, prefer the explicitly mounted home
        # when both paths refer to the same workspace directory.
        runtime_home = os.getenv("OCTO_AGENT_HOME", "").strip()
        if runtime_home and Path(runtime_home).exists() and Path(setup_workspace_path).name == Path(runtime_home).name:
            setup_workspace_path = runtime_home
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
            detail=(f"engine={integrations.system_execution.engine}, system_cli_enabled={integrations.system_execution.system_cli_enabled}, rules={len(policy.rules)}"),
            recommendation=None if integrations.system_execution.enabled else "Enable integrations.system_execution if operator CLI flows are required.",
        )
    )

    try:
        from src.tools.capability import get_capability_core_service

        capability_service = get_capability_core_service()
        registry = capability_service.build_registry_snapshot()
        contract = capability_service.build_binding_contract()
        registry_total = int((registry.get("summary") or {}).get("total_items") or 0)
        contract_total = int((contract.get("summary") or {}).get("total_items") or 0)
        by_kind = (registry.get("summary") or {}).get("by_kind") or {}
        checks.append(
            RuntimeDoctorCheck(
                id="capability-registry",
                title="Managed capability activation registry",
                status="ok" if registry_total > 0 else "fail",
                detail=f"managed_items={registry_total}, kinds={by_kind}; Harness performs full live discovery",
                recommendation=None if registry_total > 0 else "Capability registry returned no items; check skills/plugins/MCP/channel loading.",
            )
        )
        checks.append(
            RuntimeDoctorCheck(
                id="capability-binding-contract",
                title="Managed capability binding contract",
                status="ok" if contract_total == registry_total and contract_total > 0 else "fail",
                detail=f"contract_items={contract_total}, registry_items={registry_total}",
                recommendation=None if contract_total == registry_total and contract_total > 0 else "Binding contract should cover every registry item.",
            )
        )
    except Exception as exc:
        checks.append(
            RuntimeDoctorCheck(
                id="capability-registry",
                title="Managed capability activation registry",
                status="fail",
                detail=str(exc),
                recommendation="Inspect CapabilityCore registry construction and extension config loading.",
            )
        )

    try:
        from src.gateway.channels.service import ChannelService, get_channel_service

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
        pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        available_gb = (pages * page_size) / (1024**3)
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
        from src.runtime.governance import collect_runtime_governance_snapshot_async

        governance = await collect_runtime_governance_snapshot_async()
        disk = governance.get("disk", {})
        worker = governance.get("worker_isolation", {})
        langgraph_state = governance.get("langgraph_state", {})
        event_loop = governance.get("event_loop", {})
        disk_free_gb = float(disk.get("free_gb") or 0)
        queue_depth = int(worker.get("total_queued") or 0)
        checkpoint_count = int(langgraph_state.get("checkpoint_count") or 0)
        event_loop_latency_ms = float(event_loop.get("latency_ms") or 0)
        checks.append(
            RuntimeDoctorCheck(
                id="runtime-disk",
                title="Runtime disk",
                status="ok" if disk_free_gb >= 2 else "warn",
                detail=(f"path={disk.get('path')}, free_gb={disk_free_gb:.2f}, used_percent={disk.get('used_percent')}"),
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
                id="langgraph-state",
                title="LangGraph PostgreSQL state",
                status="ok" if not langgraph_state.get("error") else "warn",
                detail=(f"threads={langgraph_state.get('thread_count')}, checkpoints={checkpoint_count}"),
                recommendation=None if not langgraph_state.get("error") else str(langgraph_state.get("error")),
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
                recommendation="Inspect runtime governance collection and LangGraph PostgreSQL state.",
            )
        )

    runtime_profile = os.getenv("OCTOAGENT_RUNTIME_PROFILE", "development").strip().lower()
    binary_locations = await asyncio.to_thread(lambda: {binary: shutil.which(binary) for binary in ("git", "node", "pnpm", "python3")})
    for binary, location in binary_locations.items():
        production_optional = binary == "pnpm" and runtime_profile == "production" and not location
        checks.append(
            RuntimeDoctorCheck(
                id=f"binary:{binary}",
                title=f"Binary: {binary}",
                status="ok" if location or production_optional else "warn",
                detail=location or ("Not required in production image" if production_optional else "Not found in PATH"),
                recommendation=None if location or production_optional else f"Install {binary} or ensure it is available in PATH.",
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
    from src.runtime.governance import collect_runtime_governance_snapshot_async

    return RuntimeLongRunningHealthResponse(snapshot=await collect_runtime_governance_snapshot_async())


@router.get("/maintenance/status")
async def get_runtime_maintenance_status() -> dict[str, Any]:
    from src.runtime.governance import get_runtime_maintenance_scheduler

    return get_runtime_maintenance_scheduler().status()


@router.post("/maintenance/run")
async def run_runtime_maintenance() -> dict[str, Any]:
    from src.runtime.governance import get_runtime_maintenance_scheduler

    return get_runtime_maintenance_scheduler().run_once()


# =====================================================================
# Phase 1 (2026-05-26): runtime effective-config snapshot
# Single JSON exit for all OCTO_* env + key config.yaml values.
# =====================================================================


class RuntimeEffectiveConfigResponse(BaseModel):
    """Single-point runtime configuration snapshot."""

    generated_at: str = Field(..., description="ISO 8601 UTC timestamp when this snapshot was produced")
    runtime_governance_version: str = Field(..., description="Runtime governance version string")
    repo_root: str = Field(..., description="Resolved repository root path")
    env: dict[str, str] = Field(..., description="OCTO_* / OCTOAGENT_* environment variables in effect")
    paths: dict[str, str] = Field(..., description="Resolved writable runtime paths")
    feature_flags: dict[str, bool | str | int] = Field(..., description="Boolean / scalar feature flags derived from env + config")
    ports: dict[str, int] = Field(..., description="Resolved port assignments")
    default_model: str | None = Field(default=None, description="Configured default model name, if any")


@router.get("/effective-config", response_model=RuntimeEffectiveConfigResponse)
async def get_runtime_effective_config() -> RuntimeEffectiveConfigResponse:
    """Return the single-source runtime configuration snapshot.

    Phase 1 of the 2026-05-26 stability roadmap. Consolidates the 25+ OCTO_*
    environment variables, the 4 runtime_*.py module values, and a handful
    of derived config.yaml fields into one JSON document. CLI ``octoagent
    config show`` calls this endpoint so operators do not need to read 5
    files cross-referenced to debug a misconfigured deployment.
    """
    from datetime import datetime

    env_prefixes = ("OCTO_", "OCTOAGENT_")
    env_keys = sorted(k for k in os.environ if k.startswith(env_prefixes))
    # Mask anything that smells like a credential. False-positives are fine —
    # operators who need the value can read the file directly.
    _SECRET_FRAGMENTS = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY", "APIKEY", "AUTH", "PRIVATE", "COOKIE")

    def _mask(key: str, value: str) -> str:
        if not value:
            return value
        upper = key.upper()
        if any(frag in upper for frag in _SECRET_FRAGMENTS):
            if len(value) <= 6:
                return "***"
            return f"{value[:3]}***{value[-2:]} (len={len(value)})"
        return value

    env_snapshot = {k: _mask(k, os.environ[k]) for k in env_keys}

    # default_model is best-effort: read setup.json directly
    default_model: str | None = None
    try:
        import json as _j

        sf = get_setup_state_file()
        if Path(sf).is_file():
            raw = _j.loads(Path(sf).read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                v = raw.get("default_model")
                default_model = str(v) if v else None
    except Exception:
        default_model = None

    paths_snapshot: dict[str, str] = {
        "repo_root": str(_resolve_repo_root()),
        "setup_state_file": str(get_setup_state_file()),
    }
    try:
        from src.runtime.permissions import get_runtime_writable_paths

        for label, p in get_runtime_writable_paths().items():
            paths_snapshot[label] = str(p)
    except Exception:
        pass

    flags: dict[str, bool | str | int] = {}
    flags["host_memory_oom_critical"] = bool(is_host_memory_oom_critical())
    for key in (
        "OCTO_HARNESS_RUN_JOURNAL",
        "OCTO_HARNESS_BUDGET_ENABLED",
        "OCTOAGENT_SYSTEM_TOOLS_ENABLED",
        "OCTO_WEB_FETCH_ALLOW_INSECURE_SSL_RETRY",
    ):
        if key in os.environ:
            flags[key] = os.environ[key]

    ports: dict[str, int] = {}
    for key in (
        "OCTO_NGINX_PORT",
        "OCTO_GATEWAY_PORT",
        "OCTO_LANGGRAPH_PORT",
        "OCTO_FRONTEND_PORT",
        "OCTO_PROVISIONER_PORT",
        "OCTO_TTYD_PORT",
        "OCTO_SANDBOX_BASE_PORT",
        "OCTO_EXECUTION_WORKER_PORT",
    ):
        raw = os.environ.get(key)
        if raw and raw.isdigit():
            ports[key] = int(raw)

    return RuntimeEffectiveConfigResponse(
        generated_at=datetime.now(UTC).isoformat(),
        runtime_governance_version="2026.5.22",
        repo_root=paths_snapshot["repo_root"],
        env=env_snapshot,
        paths=paths_snapshot,
        feature_flags=flags,
        ports=ports,
        default_model=default_model,
    )


# =====================================================================
# Phase 4a (2026-05-26): tool-trace JSONL tail endpoint
# Reads workspace/runtime/observability/tool-trace.jsonl for the
# visual trace viewer (/workspace/observability/trace).
# =====================================================================


class ToolTraceEvent(BaseModel):
    """Single tool / subprocess / sandbox / recovery trace event."""

    ts: str | None = Field(default=None, description="Event timestamp (ISO 8601)")
    kind: str | None = Field(default=None, description="Event kind: tool / subprocess / sandbox / recovery / exception")
    name: str | None = Field(default=None, description="Tool or operation name")
    duration_ms: float | None = Field(default=None, description="Operation duration in milliseconds when available")
    status: str | None = Field(default=None, description="ok / error / timeout / cancelled")
    extra: dict[str, Any] = Field(default_factory=dict, description="Additional event-specific fields")


class ToolTraceResponse(BaseModel):
    """Recent slice of the tool-trace JSONL stream."""

    generated_at: str = Field(..., description="ISO 8601 UTC timestamp when this snapshot was produced")
    source_file: str = Field(..., description="Path of the trace JSONL file")
    file_exists: bool = Field(..., description="Whether the trace file exists on disk")
    total_lines: int = Field(..., description="Lines actually returned (after tail)")
    events: list[ToolTraceEvent] = Field(..., description="Parsed events, oldest-first")


@router.get("/tool-trace", response_model=ToolTraceResponse)
async def get_runtime_tool_trace(limit: int = 200) -> ToolTraceResponse:
    """Return the tail of the runtime tool-trace JSONL stream.

    Phase 4a of the 2026-05-26 stability roadmap. Backs the visual trace
    viewer at /workspace/observability/trace. Tails up to ``limit`` (default
    200, capped at 2000) most-recent events to keep response small.
    """
    import json as _json
    from datetime import datetime

    limit = max(1, min(int(limit), 2000))

    trace_path = _resolve_repo_root() / "workspace" / "runtime" / "observability" / "tool-trace.jsonl"

    events: list[ToolTraceEvent] = []
    file_exists = trace_path.is_file()
    if file_exists:
        try:
            # Tail without loading the entire file
            lines: list[str] = []
            with trace_path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    lines.append(line)
                    if len(lines) > limit:
                        lines.pop(0)
            for raw in lines:
                try:
                    obj = _json.loads(raw)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                events.append(
                    ToolTraceEvent(
                        ts=obj.get("ts") or obj.get("timestamp"),
                        kind=obj.get("kind") or obj.get("type"),
                        name=obj.get("name") or obj.get("tool") or obj.get("op"),
                        duration_ms=obj.get("duration_ms") or obj.get("ms"),
                        status=obj.get("status"),
                        extra={k: v for k, v in obj.items() if k not in {"ts", "timestamp", "kind", "type", "name", "tool", "op", "duration_ms", "ms", "status"}},
                    )
                )
        except OSError:
            file_exists = False

    return ToolTraceResponse(
        generated_at=datetime.now(UTC).isoformat(),
        source_file=str(trace_path),
        file_exists=file_exists,
        total_lines=len(events),
        events=events,
    )


# ---------------------------------------------------------------------------
# Phase 6: distributed dispatcher introspection (no-ops when disabled)
# ---------------------------------------------------------------------------

from src.harness.dispatcher import (  # noqa: E402
    dispatch_queue_stats as _dispatch_queue_stats,
)
from src.harness.dispatcher import (  # noqa: E402
    leader_status as _leader_status,
)
from src.harness.dispatcher import (  # noqa: E402
    list_workers as _list_workers,
)


@router.get("/workers")
async def get_workers():
    return {"workers": await _list_workers()}


@router.get("/dispatch")
async def get_dispatch_queue():
    return await _dispatch_queue_stats()


@router.get("/leader")
async def get_leader():
    return _leader_status()
