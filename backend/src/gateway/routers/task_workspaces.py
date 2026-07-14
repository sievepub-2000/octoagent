"""Gateway router for task workspaces and card orchestration surfaces."""

import asyncio
import json
import logging
import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse

from src.agents.core import get_agent_core_service
from src.gateway.routers.task_workspace_router_models import (
    ApplyTaskWorkspaceBuilderActionRequest,
    ApplyTaskWorkspaceBuilderBatchRequest,
    ExecuteTaskRequest,
    QuerySession,
    TaskAgentListResponse,
    TaskAgentMessagesResponse,
    TaskArtifactListResponse,
    TaskCardGraphResponse,
    TaskResultResponse,
    TaskRunLogResponse,
    TaskStudioRuntimeEventsResponse,
    TaskStudioRuntimeResponse,
    TaskWorkspaceBuilderHistoryResponse,
    TaskWorkspaceBuilderPreviewResponse,
    TaskWorkspaceListResponse,
    build_task_workspace_builder_history_response,
    build_task_workspace_builder_preview_response,
)
from src.governance.multi_tenant import get_tenant_registry
from src.storage.workflow import (
    AgentMessage,
    CheckpointRef,
    CreateAgentMessageRequest,
    CreateCheckpointRequest,
    CreateTaskWorkspaceRequest,
    TaskArtifactFile,
    TaskCardGraph,
    TaskProgress,
    TaskWorkflowModule,
    TaskWorkspace,
    TaskWorkspaceSummary,
    UpdateTaskCardGraphRequest,
    UpdateTaskWorkspaceRequest,
    get_workflow_core_service,
    safe_auto_execute_workspace,
)
from src.utils.datetime import utc_now_iso as _utc_now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/task-workspaces", tags=["task-workspaces"])

__all__ = [
    "AgentMessage",
    "CheckpointRef",
    "TaskCardGraph",
    "TaskProgress",
    "TaskWorkspace",
    "router",
]

# Regex for valid task/agent IDs: alphanumeric, hyphens, underscores
_VALID_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _to_summary(workspace: TaskWorkspace) -> TaskWorkspaceSummary:
    return TaskWorkspaceSummary(
        task_id=workspace.task_id,
        name=workspace.name,
        mode=workspace.mode,
        summary=workspace.summary,
        agent_runtime_provider=workspace.agent_runtime_provider,
        execution_strategy=getattr(workspace, "execution_strategy", "fixed") or "fixed",
        status=workspace.status,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        goal=workspace.goal,
        progress=workspace.progress,
    )


def _get_workspace_or_404(task_id: str) -> TaskWorkspace:
    if not _VALID_ID_RE.match(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")
    workspace = get_workflow_core_service().get_workspace(task_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return workspace


async def _safe_auto_execute_lead_agent(workspace: TaskWorkspace) -> None:
    await safe_auto_execute_workspace(
        workspace,
        merge_workspace_metadata=_merge_workspace_metadata,
        workflow_module_factory=TaskWorkflowModule,
    )


# Provider-neutral alias (preferred going forward)
_safe_auto_execute = _safe_auto_execute_lead_agent


def _merge_workspace_metadata(task_id: str, **metadata) -> TaskWorkspace | None:
    service = get_workflow_core_service()
    if hasattr(service, "merge_workspace_metadata"):
        return service.merge_workspace_metadata(task_id, **metadata)
    workspace = service.get_workspace(task_id)
    if workspace is None:
        return None
    merged = dict(workspace.metadata or {})
    merged.update(metadata)
    return service.update_workspace(task_id, UpdateTaskWorkspaceRequest(metadata=merged))


def _metadata_string(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


_SCHEDULER_TASK: asyncio.Task[None] | None = None
_SCHEDULER_INTERVAL_SECONDS = 2
_RUNNABLE_STATUSES = {"created", "planned", "paused", "waiting_review"}


def _decode_workflow_summary(summary: str | None) -> dict[str, object]:
    if not isinstance(summary, str):
        return {}
    raw = summary.strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _extract_schedule_state(workspace: TaskWorkspace) -> tuple[str | None, str | None, bool]:
    metadata = workspace.metadata or {}
    run_mode_candidate = metadata.get("workflow_run_mode")
    schedule_at_candidate = metadata.get("workflow_schedule_at")
    pending_candidate = metadata.get("workflow_schedule_pending")

    summary_payload = _decode_workflow_summary(workspace.summary)
    if not isinstance(run_mode_candidate, str) or not run_mode_candidate.strip():
        summary_mode = summary_payload.get("runMode")
        if isinstance(summary_mode, str):
            run_mode_candidate = summary_mode
    if not isinstance(schedule_at_candidate, str) or not schedule_at_candidate.strip():
        summary_schedule = summary_payload.get("scheduledAt")
        if isinstance(summary_schedule, str):
            schedule_at_candidate = summary_schedule

    run_mode = str(run_mode_candidate).strip().lower() if isinstance(run_mode_candidate, str) else None
    if run_mode not in {"chat", "cron", "yolo"}:
        run_mode = None

    schedule_at = str(schedule_at_candidate).strip() if isinstance(schedule_at_candidate, str) and str(schedule_at_candidate).strip() else None
    pending = bool(pending_candidate)
    if run_mode == "cron" and schedule_at and pending_candidate is None:
        pending = True
    return run_mode, schedule_at, pending


def _parse_iso_timestamp(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


async def _trigger_workspace_run(
    *,
    task_id: str,
    auto_compile: bool,
    auto_iterate: bool,
    max_iterations: int,
    mark_schedule_consumed: bool = False,
) -> TaskWorkspace:
    service = get_workflow_core_service()
    workspace = service.get_workspace(task_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")

    if auto_compile:
        workspace = service.compile_workspace_plan(task_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")

    metadata = dict(workspace.metadata or {})
    metadata["auto_iterate"] = auto_iterate
    metadata["max_iterations"] = max(1, max_iterations)
    if mark_schedule_consumed:
        metadata["workflow_schedule_pending"] = False
        metadata["workflow_schedule_triggered_at"] = _utc_now()
        metadata["workflow_schedule_last_error"] = None
    workspace = service.update_workspace(task_id, UpdateTaskWorkspaceRequest(metadata=metadata))
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")

    workspace = get_agent_core_service().ensure_handoff_sessions(task_id) or workspace
    workspace = get_agent_core_service().mark_workspace_running(task_id, task_service=service)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")

    asyncio.create_task(_safe_auto_execute(workspace))
    return workspace


async def _process_scheduled_workspaces() -> None:
    service = get_workflow_core_service()
    now_utc = datetime.now(UTC)
    for workspace in service.list_workspaces():
        run_mode, schedule_at, pending = _extract_schedule_state(workspace)
        if run_mode != "cron" or not pending or not schedule_at:
            continue

        schedule_at_dt = _parse_iso_timestamp(schedule_at)
        if schedule_at_dt is None:
            logger.warning(
                "Skip invalid workflow schedule timestamp for task %s: %s",
                workspace.task_id,
                schedule_at,
            )
            _merge_workspace_metadata(
                workspace.task_id,
                workflow_schedule_pending=False,
                workflow_schedule_last_error=f"Invalid schedule timestamp: {schedule_at}",
            )
            continue

        if schedule_at_dt > now_utc:
            continue
        if workspace.status not in _RUNNABLE_STATUSES:
            continue

        try:
            await _trigger_workspace_run(
                task_id=workspace.task_id,
                auto_compile=True,
                auto_iterate=workspace.mode != "single",
                max_iterations=1 if workspace.mode == "single" else 3,
                mark_schedule_consumed=True,
            )
            logger.info("Scheduled workflow %s triggered at %s", workspace.task_id, _utc_now())
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to trigger scheduled workflow %s", workspace.task_id)
            _merge_workspace_metadata(
                workspace.task_id,
                workflow_schedule_pending=False,
                workflow_schedule_last_error=str(exc),
            )


async def _scheduled_workspace_runner() -> None:
    while True:
        try:
            await _process_scheduled_workspaces()
        except Exception:  # noqa: BLE001
            logger.exception("Task workspace schedule loop failed")
        await asyncio.sleep(_SCHEDULER_INTERVAL_SECONDS)


def _ensure_scheduler_started() -> None:
    global _SCHEDULER_TASK
    if _SCHEDULER_TASK is not None and not _SCHEDULER_TASK.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _SCHEDULER_TASK = loop.create_task(_scheduled_workspace_runner(), name="task-workspace-scheduler")
    logger.info("Task workspace scheduler started")


@router.get("", response_model=TaskWorkspaceListResponse)
async def list_task_workspaces(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> TaskWorkspaceListResponse:
    _ensure_scheduler_started()
    workspaces = get_workflow_core_service().list_workspaces()
    if x_tenant_id:
        tenant_id = x_tenant_id.strip()
        workspaces = [workspace for workspace in workspaces if str((workspace.metadata or {}).get("tenant_id") or "default") == tenant_id]
    return TaskWorkspaceListResponse(workspaces=[_to_summary(workspace) for workspace in workspaces])


@router.post("", response_model=TaskWorkspace)
async def create_task_workspace(
    request: CreateTaskWorkspaceRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> TaskWorkspace:
    _ensure_scheduler_started()
    tenant_id = (x_tenant_id or "").strip() or "default"
    tenant_registry = get_tenant_registry()
    tenant = tenant_registry.get_tenant(tenant_id)
    if tenant.tenant_id == "default" and tenant_id != "default":
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
    current_count = sum(1 for workspace in get_workflow_core_service().list_workspaces() if str((workspace.metadata or {}).get("tenant_id") or "default") == tenant_id)
    if not tenant_registry.enforce_workspace_limit(tenant_id, current_count):
        policy = tenant_registry.get_policy(tenant_id)
        raise HTTPException(
            status_code=409,
            detail=(f"Tenant '{tenant_id}' workspace limit exceeded ({current_count}/{policy.max_concurrent_workspaces})"),
        )
    workspace = get_workflow_core_service().create_workspace(request)
    workspace = (
        get_workflow_core_service().merge_workspace_metadata(
            workspace.task_id,
            tenant_id=tenant_id,
            tenant_tier=tenant.tier,
            tenant_policy=tenant_registry.get_policy(tenant_id).__dict__,
        )
        or workspace
    )

    run_mode, schedule_at, _pending = _extract_schedule_state(workspace)
    if run_mode == "cron" and not schedule_at:
        # Default behavior for scheduled mode without explicit datetime:
        # run immediately right after creation.
        return await _trigger_workspace_run(
            task_id=workspace.task_id,
            auto_compile=True,
            auto_iterate=workspace.mode != "single",
            max_iterations=1 if workspace.mode == "single" else 3,
            mark_schedule_consumed=True,
        )

    return workspace


@router.get("/{task_id}", response_model=TaskWorkspace)
async def get_task_workspace(task_id: str) -> TaskWorkspace:
    return _get_workspace_or_404(task_id)


@router.get("/{task_id}/builder-actions/preview", response_model=TaskWorkspaceBuilderPreviewResponse)
async def preview_task_workspace_builder_actions(task_id: str) -> TaskWorkspaceBuilderPreviewResponse:
    _get_workspace_or_404(task_id)
    svc = get_workflow_core_service()
    preview = svc.get_builder_preview(task_id)
    if preview is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return build_task_workspace_builder_preview_response(preview)


@router.get("/{task_id}/builder-actions/history", response_model=TaskWorkspaceBuilderHistoryResponse)
async def get_task_workspace_builder_history(task_id: str) -> TaskWorkspaceBuilderHistoryResponse:
    svc = get_workflow_core_service()
    history = svc.get_builder_history(task_id)
    if history is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return build_task_workspace_builder_history_response(history)


@router.post("/{task_id}/builder-actions/apply", response_model=TaskWorkspaceBuilderHistoryResponse)
async def apply_task_workspace_builder_action(
    task_id: str,
    request: ApplyTaskWorkspaceBuilderActionRequest,
) -> TaskWorkspaceBuilderHistoryResponse:
    svc = get_workflow_core_service()
    try:
        result = svc.apply_builder_action(task_id, request.action_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return build_task_workspace_builder_history_response(result)


@router.post("/{task_id}/builder-actions/apply-batch", response_model=TaskWorkspaceBuilderHistoryResponse)
async def apply_task_workspace_builder_action_batch(
    task_id: str,
    request: ApplyTaskWorkspaceBuilderBatchRequest,
) -> TaskWorkspaceBuilderHistoryResponse:
    svc = get_workflow_core_service()
    try:
        result = svc.apply_builder_action_batch(
            task_id,
            action_ids=request.action_ids,
            use_apply_all_patch=request.use_apply_all_patch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return build_task_workspace_builder_history_response(result)


@router.delete("/{task_id}", status_code=204)
async def delete_task_workspace(task_id: str) -> None:
    if not _VALID_ID_RE.match(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")
    # Collect thread IDs before deleting so we can clean up LangGraph + checkpoints.db
    from src.agents.runtime import get_langgraph_workflow_contract_service  # noqa: PLC0415

    contract_service = get_langgraph_workflow_contract_service()
    contract = contract_service.contract_for_task(task_id)
    thread_ids = [t.get("thread_id") for t in contract.get("threads", []) if isinstance(t, dict) and t.get("thread_id")]
    deleted = get_workflow_core_service().delete_workspace(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    # Cascade-delete each thread from LangGraph registry and checkpoints.db.
    # delete_workspace already removed them from workflow_contract.json; now
    # remove them from the LangGraph in-memory store and the SQLite backend so
    # conversation data is fully erased.
    for thread_id in thread_ids:
        try:
            await contract_service.delete_remote_thread(thread_id)
        except Exception:
            pass


@router.put("/{task_id}", response_model=TaskWorkspace)
async def update_task_workspace(
    task_id: str,
    request: UpdateTaskWorkspaceRequest,
) -> TaskWorkspace:
    _ensure_scheduler_started()
    workspace = get_workflow_core_service().update_workspace(task_id, request)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return workspace


@router.get("/{task_id}/cards", response_model=TaskCardGraphResponse)
async def get_task_workspace_cards(task_id: str) -> TaskCardGraphResponse:
    workspace = _get_workspace_or_404(task_id)
    return TaskCardGraphResponse(
        task_id=task_id,
        card_graph=workspace.card_graph,
        progress=workspace.progress,
    )


@router.put("/{task_id}/cards", response_model=TaskWorkspace)
async def update_task_workspace_cards(
    task_id: str,
    request: UpdateTaskCardGraphRequest,
) -> TaskWorkspace:
    workspace = get_workflow_core_service().update_card_graph(task_id, request)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return workspace


@router.post("/{task_id}/compile", response_model=TaskWorkspace)
async def compile_task_workspace(task_id: str) -> TaskWorkspace:
    workspace = get_workflow_core_service().compile_workspace_plan(task_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return workspace


@router.post("/{task_id}/run", response_model=TaskWorkspace)
async def run_task_workspace(
    task_id: str,
    request: ExecuteTaskRequest,
) -> TaskWorkspace:
    _ensure_scheduler_started()
    return await _trigger_workspace_run(
        task_id=task_id,
        auto_compile=request.auto_compile,
        auto_iterate=request.auto_iterate,
        max_iterations=request.max_iterations,
    )


@router.post("/{task_id}/checkpoints", response_model=TaskWorkspace)
async def create_task_workspace_checkpoint(
    task_id: str,
    request: CreateCheckpointRequest,
) -> TaskWorkspace:
    workspace = get_workflow_core_service().create_checkpoint(task_id, request)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return workspace


@router.get("/{task_id}/checkpoints", response_model=list)
async def list_task_workspace_checkpoints(task_id: str):
    return _get_workspace_or_404(task_id).checkpoints


@router.get("/{task_id}/run-log", response_model=TaskRunLogResponse)
async def get_task_workspace_run_log(task_id: str) -> TaskRunLogResponse:
    _get_workspace_or_404(task_id)
    run_log = get_workflow_core_service().read_run_log(task_id)
    return TaskRunLogResponse(
        task_id=task_id,
        run_log=run_log or "# Workflow Run Log\n\n## Final Results\n\n_Results pending._\n",
    )


@router.get("/{task_id}/result", response_model=TaskResultResponse)
async def get_task_workspace_result(task_id: str) -> TaskResultResponse:
    _get_workspace_or_404(task_id)
    service = get_workflow_core_service()
    if hasattr(service, "read_result_payload"):
        payload = service.read_result_payload(task_id)
        return TaskResultResponse(
            task_id=task_id,
            result_content=str(payload.get("content") or ""),
            has_result=bool(payload.get("has_result", False)),
            source_path=(str(payload.get("source_path")) if payload.get("source_path") else None),
            source_label=(str(payload.get("source_label")) if payload.get("source_label") else None),
            available_sources=[str(item) for item in payload.get("available_sources", []) if isinstance(item, str)],
        )

    result_content = service.read_result(task_id)
    if result_content is None:
        return TaskResultResponse(
            task_id=task_id,
            result_content="",
            has_result=False,
        )
    return TaskResultResponse(
        task_id=task_id,
        result_content=result_content,
        has_result=True,
    )


@router.get("/{task_id}/studio-runtime", response_model=TaskStudioRuntimeResponse)
async def get_task_workspace_studio_runtime(task_id: str) -> TaskStudioRuntimeResponse:
    _get_workspace_or_404(task_id)
    contract = get_workflow_core_service().get_studio_runtime_contract(task_id)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return TaskStudioRuntimeResponse.model_validate(contract)


@router.get("/{task_id}/studio-runtime/events", response_model=TaskStudioRuntimeEventsResponse)
async def get_task_workspace_studio_runtime_events(
    task_id: str,
    cursor: int = 0,
    limit: int = 20,
) -> TaskStudioRuntimeEventsResponse:
    _get_workspace_or_404(task_id)
    contract = get_workflow_core_service().list_studio_runtime_events(task_id, cursor=cursor, limit=limit)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return TaskStudioRuntimeEventsResponse.model_validate(contract)


@router.get("/{task_id}/artifacts", response_model=TaskArtifactListResponse)
async def list_task_workspace_artifacts(task_id: str) -> TaskArtifactListResponse:
    _get_workspace_or_404(task_id)
    files = [
        TaskArtifactFile(
            name=artifact["name"],
            path=artifact["path"],
            download_url=f"/api/task-workspaces/{task_id}/artifacts/{artifact['path']}?download=true",
        )
        for artifact in get_workflow_core_service().list_artifacts(task_id)
    ]
    return TaskArtifactListResponse(task_id=task_id, files=files)


@router.get("/{task_id}/artifacts/{artifact_path:path}")
async def get_task_workspace_artifact(task_id: str, artifact_path: str, request: Request) -> FileResponse:
    _get_workspace_or_404(task_id)
    actual_path = get_workflow_core_service().resolve_artifact_path(task_id, artifact_path)
    if actual_path is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_path}' not found")

    mime_type, _ = mimetypes.guess_type(actual_path)
    encoded_filename = quote(Path(actual_path).name)
    if request.query_params.get("download"):
        return FileResponse(
            path=actual_path,
            filename=Path(actual_path).name,
            media_type=mime_type,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
        )
    return FileResponse(
        path=actual_path,
        filename=Path(actual_path).name,
        media_type=mime_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}"},
    )


@router.post("/{task_id}/pause", response_model=TaskWorkspace)
async def pause_task_workspace(task_id: str) -> TaskWorkspace:
    workspace = _get_workspace_or_404(task_id)
    if workspace.status not in ("running", "waiting_review"):
        raise HTTPException(status_code=409, detail=f"Cannot pause task in '{workspace.status}' state")
    result = get_agent_core_service().pause_workspace_execution(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return result


@router.post("/{task_id}/resume", response_model=TaskWorkspace)
async def resume_task_workspace(task_id: str) -> TaskWorkspace:
    workspace = _get_workspace_or_404(task_id)
    if workspace.status not in ("created", "planned", "paused", "waiting_review"):
        raise HTTPException(status_code=409, detail=f"Cannot resume task in '{workspace.status}' state")
    result = get_agent_core_service().resume_workspace_execution(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return result


@router.post("/{task_id}/terminate", response_model=TaskWorkspace)
async def terminate_task_workspace(task_id: str) -> TaskWorkspace:
    workspace = _get_workspace_or_404(task_id)
    if workspace.status in ("terminated", "completed"):
        raise HTTPException(status_code=409, detail=f"Task already in '{workspace.status}' state")
    result = get_agent_core_service().terminate_workspace_execution(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    return result


@router.get("/{task_id}/agents", response_model=TaskAgentListResponse)
async def list_task_agents(task_id: str) -> TaskAgentListResponse:
    _get_workspace_or_404(task_id)
    return TaskAgentListResponse(task_id=task_id, agents=get_agent_core_service().list_task_agents(task_id))


@router.get("/{task_id}/agents/{agent_id}/messages", response_model=TaskAgentMessagesResponse)
async def list_task_agent_messages(
    task_id: str,
    agent_id: str,
) -> TaskAgentMessagesResponse:
    messages = get_agent_core_service().list_agent_messages(task_id, agent_id)
    if messages is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' in task workspace '{task_id}' not found",
        )
    return TaskAgentMessagesResponse(task_id=task_id, agent_id=agent_id, messages=messages)


@router.post("/{task_id}/agents/{agent_id}/messages", response_model=TaskAgentMessagesResponse)
async def create_task_agent_message(
    task_id: str,
    agent_id: str,
    request: CreateAgentMessageRequest,
) -> TaskAgentMessagesResponse:
    messages = await get_agent_core_service().execute_agent_message(task_id, agent_id, request)
    if messages is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' in task workspace '{task_id}' not found",
        )
    return TaskAgentMessagesResponse(task_id=task_id, agent_id=agent_id, messages=messages)


@router.post("/{task_id}/agents/{agent_id}/handoff", response_model=QuerySession)
async def create_task_agent_handoff(
    task_id: str,
    agent_id: str,
) -> QuerySession:
    session = get_agent_core_service().create_agent_handoff_session(task_id, agent_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' in task workspace '{task_id}' not found",
        )
    return session


@router.post("/{task_id}/agents/{agent_id}/pause", response_model=TaskWorkspace)
async def pause_task_agent(task_id: str, agent_id: str) -> TaskWorkspace:
    workspace = get_agent_core_service().pause_agent_execution(task_id, agent_id)
    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' in task workspace '{task_id}' not found",
        )
    return workspace


@router.post("/{task_id}/agents/{agent_id}/resume", response_model=TaskWorkspace)
async def resume_task_agent(task_id: str, agent_id: str) -> TaskWorkspace:
    workspace = get_agent_core_service().resume_agent_execution(task_id, agent_id)
    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' in task workspace '{task_id}' not found",
        )
    return workspace


@router.post("/{task_id}/agents/{agent_id}/terminate", response_model=TaskWorkspace)
async def terminate_task_agent(task_id: str, agent_id: str) -> TaskWorkspace:
    workspace = get_agent_core_service().terminate_agent_execution(task_id, agent_id)
    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' in task workspace '{task_id}' not found",
        )
    return workspace
