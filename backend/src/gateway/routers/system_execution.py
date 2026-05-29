"""Gateway router for system-level execution skeleton."""

from pathlib import Path

import yaml
from fastapi import APIRouter, Header, HTTPException

from src.gateway.security import require_operator_or_403
from src.runtime.config.app_config import AppConfig, reload_app_config
from src.runtime.config.integrations_config import SystemExecutionConfig
from src.tools.system_execution import (
    SystemExecutionAuditEntry,
    SystemExecutionCapability,
    SystemExecutionCliRequest,
    SystemExecutionCliResponse,
    SystemExecutionDesktopSnapshot,
    SystemExecutionPermissionPolicy,
    SystemExecutionPlan,
    SystemExecutionPlanRequest,
    SystemExecutionSession,
    SystemExecutionSessionListResponse,
    SystemExecutionSessionRecoveryRequest,
    SystemExecutionSessionUpdateRequest,
    SystemExecutionStepExecutionRequest,
    SystemExecutionStepExecutionResult,
    get_system_execution_service,
)

router = APIRouter(prefix="/api/system-execution", tags=["system-execution"])


def _config_path() -> Path:
    return AppConfig.resolve_config_path()


def _load_config_data() -> dict:
    return yaml.safe_load(_config_path().read_text(encoding="utf-8")) or {}


def _write_system_execution_config(config: SystemExecutionConfig) -> SystemExecutionConfig:
    config_data = _load_config_data()
    integrations = dict(config_data.get("integrations") or {})
    integrations["system_execution"] = config.model_dump(exclude_none=True)
    config_data["integrations"] = integrations
    target = _config_path()
    target.write_text(yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    reload_app_config(str(target))
    return config


def _require_operator(
    *,
    role: str | None,
    token: str | None,
    minimum: str = "operator",
) -> None:
    require_operator_or_403(role=role, token=token, minimum=minimum)


@router.get(
    "/capabilities",
    response_model=SystemExecutionCapability,
    summary="Get System Execution Capabilities",
    description="Expose the current desktop/system execution runtime capability surface.",
)
async def get_system_execution_capabilities() -> SystemExecutionCapability:
    return get_system_execution_service().get_capability()


@router.get(
    "/permission-policy",
    response_model=SystemExecutionPermissionPolicy,
    summary="Get System Execution Permission Policy",
    description="Expose the typed permission rules used to gate system/browser/file side effects.",
)
async def get_system_execution_permission_policy() -> SystemExecutionPermissionPolicy:
    return get_system_execution_service().get_permission_policy()


@router.get(
    "/config",
    response_model=SystemExecutionConfig,
    summary="Get System Execution Config",
    description="Read the persisted system-execution config used for CLI scope and permission policy decisions.",
)
async def get_system_execution_config() -> SystemExecutionConfig:
    return get_system_execution_service()._policy._system_execution_config()


@router.put(
    "/config",
    response_model=SystemExecutionConfig,
    summary="Update System Execution Config",
    description="Persist system-execution config and reload application config.",
)
async def update_system_execution_config(
    request: SystemExecutionConfig,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> SystemExecutionConfig:
    _require_operator(role=x_octoagent_operator_role, token=x_octoagent_operator_token, minimum="admin")
    return _write_system_execution_config(request)


@router.post(
    "/plan",
    response_model=SystemExecutionPlan,
    summary="Plan System Execution",
    description="Build a bounded system-execution plan without claiming a live desktop executor exists.",
)
async def plan_system_execution(
    request: SystemExecutionPlanRequest,
) -> SystemExecutionPlan:
    return get_system_execution_service().plan(request)


@router.post(
    "/sessions",
    response_model=SystemExecutionSession,
    summary="Create System Execution Session",
    description="Create a dry-run system execution session from the requested plan.",
)
async def create_system_execution_session(
    request: SystemExecutionPlanRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> SystemExecutionSession:
    _require_operator(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    return get_system_execution_service().create_session(request, dry_run=True)


@router.post(
    "/sessions/live",
    response_model=SystemExecutionSession,
    summary="Create Live System Execution Session",
    description="Create a non-dry-run system execution session for bounded manual execution testing.",
)
async def create_live_system_execution_session(
    request: SystemExecutionPlanRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> SystemExecutionSession:
    _require_operator(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    return get_system_execution_service().create_session(request, dry_run=False)


@router.get(
    "/sessions",
    response_model=SystemExecutionSessionListResponse,
    summary="List System Execution Sessions",
    description="Return recent persisted system execution sessions with optional target/task filters.",
)
async def list_system_execution_sessions(
    target: str | None = None,
    related_task_id: str | None = None,
    limit: int = 20,
) -> SystemExecutionSessionListResponse:
    sessions = get_system_execution_service().list_sessions(
        target=target,
        related_task_id=related_task_id,
        limit=limit,
    )
    return SystemExecutionSessionListResponse(sessions=sessions)


@router.get(
    "/sessions/{session_id}",
    response_model=SystemExecutionSession,
    summary="Get System Execution Session",
    description="Retrieve a previously created system execution session.",
)
async def get_system_execution_session(session_id: str) -> SystemExecutionSession:
    session = get_system_execution_service().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


@router.post(
    "/sessions/{session_id}/status",
    response_model=SystemExecutionSession,
    summary="Update System Execution Session Status",
    description="Advance a system execution session through a dry-run lifecycle and append audit detail.",
)
async def update_system_execution_session(
    session_id: str,
    request: SystemExecutionSessionUpdateRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> SystemExecutionSession:
    _require_operator(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    session = get_system_execution_service().update_session(session_id, request)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


@router.post(
    "/sessions/{session_id}/recover",
    response_model=SystemExecutionSession,
    summary="Recover System Execution Session",
    description="Reset a blocked session so the remaining bounded steps can be retried.",
)
async def recover_system_execution_session(
    session_id: str,
    request: SystemExecutionSessionRecoveryRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> SystemExecutionSession:
    _require_operator(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    session = get_system_execution_service().recover_session(session_id, request)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


@router.post(
    "/sessions/{session_id}/execute-next",
    response_model=SystemExecutionStepExecutionResult,
    summary="Execute Next System Execution Step",
    description="Simulate the next planned system execution step and append audit state.",
)
async def execute_next_system_execution_step(
    session_id: str,
    request: SystemExecutionStepExecutionRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> SystemExecutionStepExecutionResult:
    _require_operator(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    result = get_system_execution_service().execute_next_step(session_id, request)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return result


@router.post(
    "/cli/workspace",
    response_model=SystemExecutionCliResponse,
    summary="Execute Workspace CLI Command",
    description="Run a bounded server-side CLI command from the OctoAgent working directory scope.",
)
async def execute_workspace_cli_command(
    request: SystemExecutionCliRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> SystemExecutionCliResponse:
    _require_operator(role=x_octoagent_operator_role or request.role, token=x_octoagent_operator_token)
    return get_system_execution_service().execute_cli_command(request, scope="workspace")


@router.post(
    "/cli/system",
    response_model=SystemExecutionCliResponse,
    summary="Execute System CLI Command",
    description="Run a bounded server-side CLI command from the broader host system scope.",
)
async def execute_system_cli_command(
    request: SystemExecutionCliRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> SystemExecutionCliResponse:
    _require_operator(role=x_octoagent_operator_role or request.role, token=x_octoagent_operator_token, minimum="admin")
    return get_system_execution_service().execute_cli_command(request, scope="system")


@router.get(
    "/sessions/{session_id}/snapshot",
    response_model=SystemExecutionDesktopSnapshot,
    summary="Get System Execution Snapshot",
    description="Retrieve the latest desktop/system snapshot captured for a session.",
)
async def get_system_execution_snapshot(
    session_id: str,
) -> SystemExecutionDesktopSnapshot:
    snapshot = get_system_execution_service().get_snapshot(session_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Snapshot for '{session_id}' not found")
    return snapshot


@router.get(
    "/sessions/{session_id}/audit",
    response_model=list[SystemExecutionAuditEntry],
    summary="Get System Execution Audit Log",
    description="Retrieve planned/simulated audit entries for a system execution session.",
)
async def get_system_execution_audit(
    session_id: str,
) -> list[SystemExecutionAuditEntry]:
    session = get_system_execution_service().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return get_system_execution_service().get_audits(session_id)
