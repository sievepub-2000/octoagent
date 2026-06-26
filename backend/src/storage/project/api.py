"""Project API router — lightweight delegation to task-workspaces with memory isolation."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from src.storage.task_workspaces import (
    CreateTaskWorkspaceRequest,
    get_task_workspace_service,
)
from src.storage.task_workspaces.workflow_module import TaskWorkflowModule
from src.storage.workflow.observation import parse_run_log_timeline
from src.storage.project.memory import get_project_memory_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _build_summary(ws) -> dict:
    mem_svc = get_project_memory_service()
    mem = mem_svc.load_project_memory(ws.task_id) or {}
    return {
        "project_id": ws.task_id,
        "name": ws.name,
        "goal": ws.goal,
        "status": ws.status,
        "created_at": ws.created_at,
        "updated_at": ws.updated_at,
        "progress": ws.progress.model_dump() if hasattr(ws.progress, "model_dump") else {},
        "memory_summary": (mem.get("summary") or "")[:200],
    }


def _build_detail(ws) -> dict:
    wf = TaskWorkflowModule()
    run_log = wf._files.read_run_log(ws.task_id) or ""
    artifacts = wf._files.sync_task_attachments(ws.task_id)
    mem_svc = get_project_memory_service()
    mem = mem_svc.load_project_memory(ws.task_id) or {}
    return {
        "project_id": ws.task_id,
        "name": ws.name,
        "goal": ws.goal,
        "status": ws.status,
        "created_at": ws.created_at,
        "updated_at": ws.updated_at,
        "summary": ws.summary,
        "agents": [{"agent_id": a.agent_id, "name": a.name, "role": a.role, "status": a.status}
                   for a in ws.agents],
        "run_log": run_log,
        "artifacts": artifacts,
        "timeline": parse_run_log_timeline(run_log) if run_log else [],
        "progress": ws.progress.model_dump() if hasattr(ws.progress, "model_dump") else {},
        "memory": mem,
    }


@router.get("")
async def list_projects() -> list[dict[str, Any]]:
    svc = get_task_workspace_service()
    workspaces = svc.list_workspaces()
    return [_build_summary(ws) for ws in workspaces]


@router.post("")
async def create_project(body: dict[str, Any]) -> dict[str, Any]:
    name = body.get("name", "Untitled Project")
    goal = body.get("goal", "")
    svc = get_task_workspace_service()
    request = CreateTaskWorkspaceRequest(name=name, goal=goal, mode="single")
    ws = svc.create_workspace(request)
    mem_svc = get_project_memory_service()
    mem_svc.ensure_project_memory(ws.task_id, name, goal)
    return _build_detail(ws)


@router.get("/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    svc = get_task_workspace_service()
    ws = svc.get_workspace(project_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _build_detail(ws)


@router.put("/{project_id}")
async def update_project(project_id: str, body: dict[str, Any]) -> dict[str, Any]:
    from src.storage.task_workspaces.contracts import UpdateTaskWorkspaceRequest
    svc = get_task_workspace_service()
    patch = {}
    if "name" in body:
        patch["name"] = body["name"]
    if "goal" in body:
        patch["goal"] = body["goal"]
    ws = svc.update_workspace(project_id, UpdateTaskWorkspaceRequest(**patch))
    if ws is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _build_detail(ws)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str) -> None:
    svc = get_task_workspace_service()
    mem_svc = get_project_memory_service()
    mem_svc.delete_project_memory(project_id)
    ok = svc.delete_workspace(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/{project_id}/memory")
async def get_project_memory(project_id: str) -> dict[str, Any]:
    mem_svc = get_project_memory_service()
    mem = mem_svc.load_project_memory(project_id) or {}
    return mem


@router.put("/{project_id}/memory")
async def update_project_memory(project_id: str, body: dict[str, Any]) -> dict[str, Any]:
    mem_svc = get_project_memory_service()
    summary = body.get("summary", "")
    mem_svc.save_project_memory(project_id, summary)
    return mem_svc.load_project_memory(project_id) or {}


@router.get("/system/summaries")
async def list_all_project_summaries() -> list[dict[str, Any]]:
    mem_svc = get_project_memory_service()
    return mem_svc.list_all_project_summaries()
