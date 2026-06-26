from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from src.gateway.observability import record_exception_trace
from src.storage.query import get_query_engine_service
from src.storage.task_workspaces import (
    CreateTaskWorkspaceRequest,
    TaskWorkspace,
    get_task_workspace_execution_controller,
    get_task_workspace_service,
)
from src.storage.task_workspaces.workflow_module import TaskWorkflowModule
from src.storage.workflow.observation import parse_run_log_timeline
from src.storage.workflow.status import workflow_stage_for_status

from .memory import ProjectMemoryService, get_project_memory_service

logger = logging.getLogger(__name__)


class ProjectSummary:
    __slots__ = ("project_id", "name", "goal", "status", "created_at", "updated_at", "progress", "memory_summary")
    def __init__(self, ws: TaskWorkspace):
        self.project_id = ws.task_id
        self.name = ws.name
        self.goal = ws.goal
        self.status = ws.status
        self.created_at = ws.created_at
        self.updated_at = ws.updated_at
        self.progress = ws.progress.model_dump() if hasattr(ws.progress, "model_dump") else {}
        self.memory_summary = ""

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}


class ProjectDetail:
    __slots__ = ("project_id", "name", "goal", "status", "created_at", "updated_at",
                 "summary", "agents", "run_log", "artifacts", "timeline", "progress", "memory")
    def __init__(self, ws: TaskWorkspace, run_log: str, artifacts: list, memory: dict):
        self.project_id = ws.task_id
        self.name = ws.name
        self.goal = ws.goal
        self.status = ws.status
        self.created_at = ws.created_at
        self.updated_at = ws.updated_at
        self.summary = ws.summary
        self.agents = [{"agent_id": a.agent_id, "name": a.name, "role": a.role, "status": a.status}
                       for a in ws.agents]
        self.run_log = run_log
        self.artifacts = artifacts
        self.timeline = parse_run_log_timeline(run_log) if run_log else []
        self.progress = ws.progress.model_dump() if hasattr(ws.progress, "model_dump") else {}
        self.memory = memory

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}


def _make_id() -> str:
    return "proj-" + str(uuid4())


def _utc_now() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat()


class ProjectService:
    def __init__(self):
        self._delegate = get_task_workspace_service()
        self._workflow_module = TaskWorkflowModule()
        self._memory_service = get_project_memory_service()

    def list_projects(self) -> list[dict]:
        workspaces = self._delegate.list_workspaces()
        projects = []
        for ws in workspaces:
            ps = ProjectSummary(ws)
            mem = self._memory_service.load_project_memory(ws.task_id)
            if mem and "summary" in mem:
                ps.memory_summary = mem["summary"][:200]
            projects.append(ps.to_dict())
        return projects

    def get_project(self, project_id: str) -> dict | None:
        ws = self._delegate.get_workspace(project_id)
        if ws is None:
            return None
        run_log = self._workflow_module._files.read_run_log(project_id) or ""
        artifacts = self._workflow_module._files.sync_task_attachments(project_id)
        mem = self._memory_service.load_project_memory(project_id) or {}
        pd = ProjectDetail(ws, run_log, artifacts, mem)
        return pd.to_dict()

    def create_project(self, name: str, goal: str = "") -> dict:
        request = CreateTaskWorkspaceRequest(
            name=name,
            goal=goal,
            mode="single",
        )
        ws = self._delegate.create_workspace(request)
        self._memory_service.ensure_project_memory(ws.task_id, name, goal)
        self._delegate.merge_workspace_metadata(
            ws.task_id,
            project_id=ws.task_id,
            project_memory_path=str(self._memory_service.project_memory_path(ws.task_id)),
        )
        proj = ProjectDetail(
            ws, run_log="", artifacts=[],
            memory=self._memory_service.load_project_memory(ws.task_id) or {},
        )
        return proj.to_dict()

    def update_project(self, project_id: str, name: str | None = None, goal: str | None = None) -> dict | None:
        from src.storage.task_workspaces.contracts import UpdateTaskWorkspaceRequest
        patch = {}
        if name is not None:
            patch["name"] = name
        if goal is not None:
            patch["goal"] = goal
        if not patch:
            return self.get_project(project_id)
        ws = self._delegate.update_workspace(project_id, UpdateTaskWorkspaceRequest(**patch))
        if ws is None:
            return None
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        self._memory_service.delete_project_memory(project_id)
        return self._delegate.delete_workspace(project_id)

    def get_project_memory(self, project_id: str) -> dict:
        mem = self._memory_service.load_project_memory(project_id)
        return mem or {}

    def update_project_memory(self, project_id: str, summary: str) -> dict:
        self._memory_service.save_project_memory(project_id, summary)
        return self.get_project_memory(project_id)


_service = ProjectService()


def get_project_service() -> ProjectService:
    return _service
