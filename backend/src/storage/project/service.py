"""Persistent long-lived projects, independent from workflow executions."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from src.runtime.config.paths import get_paths

from .memory import get_project_memory_service

PermissionMode = Literal["approval", "directory", "system"]
ProjectStatus = Literal["active", "archived"]
_ALLOWED_ROOTS = (Path("/home"), Path("/opt"), Path("/srv"), Path("/tmp"), Path("/var/lib"))


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Project(BaseModel):
    project_id: str
    name: str
    root_path: str
    instructions: str = ""
    default_model: str = ""
    permission_mode: PermissionMode = "directory"
    status: ProjectStatus = "active"
    repo_url: str = ""
    branch: str = ""
    created_at: str
    updated_at: str
    memory_summary: str = ""
    pinned_files: list[str] = Field(default_factory=list)


def _git_value(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            check=False,
            encoding="utf-8",
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _resolve_root(value: str) -> Path:
    root = Path(value or get_paths().default_workspace_dir).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Project directory does not exist: {root}")
    if not any(root == allowed or allowed in root.parents for allowed in _ALLOWED_ROOTS):
        raise ValueError("Project directory must be under /home, /opt, /srv, /tmp, or /var/lib")
    return root


class ProjectService:
    def __init__(self, store_path: Path | None = None) -> None:
        self._store_path = store_path
        self._lock = RLock()
        self._memory = get_project_memory_service()

    @property
    def store_path(self) -> Path:
        return self._store_path or (get_paths().projects_dir / "projects.json")

    def _read(self) -> list[Project]:
        try:
            payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        return [Project.model_validate(item) for item in payload.get("projects", [])]

    def _write(self, projects: list[Project]) -> None:
        path = self.store_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"projects": [item.model_dump(mode="json") for item in projects]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def list_projects(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            projects = self._read()
        if not include_archived:
            projects = [item for item in projects if item.status == "active"]
        return [item.model_dump(mode="json") for item in sorted(projects, key=lambda item: item.updated_at, reverse=True)]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._lock:
            project = next((item for item in self._read() if item.project_id == project_id), None)
        return project.model_dump(mode="json") if project else None

    def create_project(
        self,
        name: str,
        root_path: str,
        instructions: str = "",
        default_model: str = "",
        permission_mode: PermissionMode = "directory",
    ) -> dict[str, Any]:
        root = _resolve_root(root_path)
        timestamp = _now()
        project = Project(
            project_id=f"proj-{uuid4()}",
            name=name.strip() or root.name,
            root_path=str(root),
            instructions=instructions.strip(),
            default_model=default_model.strip(),
            permission_mode=permission_mode,
            repo_url=_git_value(root, "remote", "get-url", "origin"),
            branch=_git_value(root, "branch", "--show-current"),
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._lock:
            projects = self._read()
            projects.append(project)
            self._write(projects)
        self._memory.ensure_project_memory(project.project_id, project.name, project.instructions)
        return project.model_dump(mode="json")

    def update_project(self, project_id: str, **changes: Any) -> dict[str, Any] | None:
        with self._lock:
            projects = self._read()
            for index, project in enumerate(projects):
                if project.project_id != project_id:
                    continue
                payload = project.model_dump()
                for key in ("name", "instructions", "default_model", "permission_mode", "status", "pinned_files"):
                    if key in changes and changes[key] is not None:
                        payload[key] = changes[key]
                if changes.get("root_path") is not None:
                    root = _resolve_root(str(changes["root_path"]))
                    payload.update(
                        root_path=str(root),
                        repo_url=_git_value(root, "remote", "get-url", "origin"),
                        branch=_git_value(root, "branch", "--show-current"),
                    )
                payload["updated_at"] = _now()
                projects[index] = Project.model_validate(payload)
                self._write(projects)
                return projects[index].model_dump(mode="json")
        return None

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            projects = self._read()
            remaining = [item for item in projects if item.project_id != project_id]
            if len(remaining) == len(projects):
                return False
            self._write(remaining)
        self._memory.delete_project_memory(project_id)
        return True

    def get_project_memory(self, project_id: str) -> dict[str, Any]:
        return self._memory.load_project_memory(project_id) or {}

    def update_project_memory(self, project_id: str, summary: str) -> dict[str, Any]:
        self._memory.save_project_memory(project_id, summary)
        return self.get_project_memory(project_id)


_service = ProjectService()


def get_project_service() -> ProjectService:
    return _service
