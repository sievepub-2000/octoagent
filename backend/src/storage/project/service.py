"""Persistent project definitions and their effective agent execution context."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from src.runtime.config.paths import get_paths

PermissionMode = Literal["approval", "directory", "system"]
ProjectStatus = Literal["active", "archived"]
_ALLOWED_ROOTS = (Path("/home"), Path("/opt"), Path("/srv"), Path("/tmp"), Path("/var/lib"))
_PERMISSION_ORDER = {"approval": 0, "directory": 1, "system": 2}


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


class ProjectExecutionContext(BaseModel):
    project_id: str
    name: str
    root_path: str
    instructions: str
    model_name: str
    permission_mode: PermissionMode
    memory_summary: str
    pinned_files: list[str]

    def prompt_section(self) -> str:
        lines = [
            "<project_context>",
            f"Project: {self.name}",
            f"Working directory: {self.root_path}",
        ]
        if self.instructions:
            lines.extend(("Project instructions:", self.instructions))
        if self.memory_summary:
            lines.extend(("Project memory:", self.memory_summary))
        if self.pinned_files:
            lines.append("Pinned files: " + ", ".join(self.pinned_files))
        lines.append("</project_context>")
        return "\n".join(lines)


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
    allowed_roots = (*_ALLOWED_ROOTS, get_paths().workspace_root)
    if not any(root == allowed or allowed in root.parents for allowed in allowed_roots):
        raise ValueError("Project directory must be under an allowed system root or the configured OctoAgent workspace")
    return root


def _effective_permission(project_mode: str, requested_mode: str | None) -> PermissionMode:
    def normalize(value: str | None) -> PermissionMode:
        normalized = (value or "").strip().lower()
        if normalized in {"system", "yolo", "full"}:
            return "system"
        if normalized in {"directory", "workspace", "repo", "project"}:
            return "directory"
        return "approval"

    project = normalize(project_mode)
    requested = normalize(requested_mode) if requested_mode is not None else project
    return min((project, requested), key=_PERMISSION_ORDER.__getitem__)


class ProjectService:
    """Single source of truth for projects and runtime project policy."""

    def __init__(self, store_path: Path | None = None) -> None:
        default_dir = get_paths().projects_dir
        self._postgres_dsn = None if store_path else (os.getenv("OCTOAGENT_CHECKPOINTER_DSN") or os.getenv("DATABASE_URL"))
        if store_path is None and not self._postgres_dsn:
            raise RuntimeError("PostgreSQL DSN is required for the project store")
        self._database_path = (
            store_path.with_suffix(".sqlite3")
            if store_path and store_path.suffix == ".json"
            else store_path or default_dir / "projects.sqlite3"
        )
        self._legacy_path = store_path if store_path and store_path.suffix == ".json" else default_dir / "projects.json"
        self._lock = RLock()
        self._initialize()

    @property
    def store_path(self) -> Path:
        return self._database_path

    def _connect_sqlite(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        if self._postgres_dsn:
            self._initialize_postgres()
            return
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connect_sqlite() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    instructions TEXT NOT NULL DEFAULT '',
                    default_model TEXT NOT NULL DEFAULT '',
                    permission_mode TEXT NOT NULL DEFAULT 'directory',
                    status TEXT NOT NULL DEFAULT 'active',
                    repo_url TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    memory_summary TEXT NOT NULL DEFAULT '',
                    pinned_files TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            if count == 0 and self._legacy_path.exists():
                try:
                    payload = json.loads(self._legacy_path.read_text(encoding="utf-8"))
                    projects = [Project.model_validate(item) for item in payload.get("projects", [])]
                except (json.JSONDecodeError, ValueError):
                    projects = []
                for project in projects:
                    self._insert(connection, project)

    def _connect_postgres(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self._postgres_dsn, connect_timeout=5, row_factory=dict_row)

    def _initialize_postgres(self) -> None:
        with self._lock, self._connect_postgres() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    instructions TEXT NOT NULL DEFAULT '',
                    default_model TEXT NOT NULL DEFAULT '',
                    permission_mode TEXT NOT NULL DEFAULT 'directory',
                    status TEXT NOT NULL DEFAULT 'active',
                    repo_url TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    memory_summary TEXT NOT NULL DEFAULT '',
                    pinned_files JSONB NOT NULL DEFAULT '[]'::jsonb
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS projects_status_updated_idx ON projects (status, updated_at DESC)")
            cursor.execute("SELECT count(*) AS count FROM projects")
            empty = int(cursor.fetchone()["count"]) == 0
        if empty:
            self._migrate_legacy_sqlite()

    def _migrate_legacy_sqlite(self) -> None:
        """Import the retired workspace SQLite database once, if present."""
        if not self._database_path.is_file():
            return
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute("SELECT * FROM projects").fetchall()
        except sqlite3.DatabaseError:
            rows = []
        finally:
            connection.close()
        if not rows:
            return
        with self._connect_postgres() as target:
            for row in rows:
                project = self._project(row)
                if project is not None:
                    self._insert(target, project)

    def _insert(self, connection, project: Project) -> None:
        payload = project.model_dump()
        if self._postgres_dsn:
            payload["pinned_files"] = json.dumps(project.pinned_files, ensure_ascii=False)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO projects
                    (project_id, name, root_path, instructions, default_model, permission_mode,
                     status, repo_url, branch, created_at, updated_at, memory_summary, pinned_files)
                    VALUES (%(project_id)s, %(name)s, %(root_path)s, %(instructions)s, %(default_model)s,
                            %(permission_mode)s, %(status)s, %(repo_url)s, %(branch)s, %(created_at)s,
                            %(updated_at)s, %(memory_summary)s, %(pinned_files)s::jsonb)
                    ON CONFLICT (project_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        root_path = EXCLUDED.root_path,
                        instructions = EXCLUDED.instructions,
                        default_model = EXCLUDED.default_model,
                        permission_mode = EXCLUDED.permission_mode,
                        status = EXCLUDED.status,
                        repo_url = EXCLUDED.repo_url,
                        branch = EXCLUDED.branch,
                        updated_at = EXCLUDED.updated_at,
                        memory_summary = EXCLUDED.memory_summary,
                        pinned_files = EXCLUDED.pinned_files
                    """,
                    payload,
                )
            return
        payload["pinned_files"] = json.dumps(project.pinned_files, ensure_ascii=False)
        connection.execute(
            """
            INSERT OR REPLACE INTO projects
            (project_id, name, root_path, instructions, default_model, permission_mode,
             status, repo_url, branch, created_at, updated_at, memory_summary, pinned_files)
            VALUES (:project_id, :name, :root_path, :instructions, :default_model, :permission_mode,
                    :status, :repo_url, :branch, :created_at, :updated_at, :memory_summary, :pinned_files)
            """,
            payload,
        )

    @staticmethod
    def _project(row: sqlite3.Row | dict[str, Any] | None) -> Project | None:
        if row is None:
            return None
        payload = dict(row)
        if isinstance(payload.get("pinned_files"), str):
            try:
                payload["pinned_files"] = json.loads(payload["pinned_files"])
            except (TypeError, json.JSONDecodeError):
                payload["pinned_files"] = []
        for key in ("created_at", "updated_at"):
            value = payload.get(key)
            if isinstance(value, datetime):
                payload[key] = value.isoformat()
        return Project.model_validate(payload)

    def list_projects(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        if self._postgres_dsn:
            query = "SELECT * FROM projects"
            params: tuple[Any, ...] = ()
            if not include_archived:
                query += " WHERE status = %s"
                params = ("active",)
            query += " ORDER BY updated_at DESC"
            with self._connect_postgres() as connection, connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        else:
            query = "SELECT * FROM projects"
            params = ()
            if not include_archived:
                query += " WHERE status = ?"
                params = ("active",)
            query += " ORDER BY updated_at DESC"
            with self._connect_sqlite() as connection:
                rows = connection.execute(query, params).fetchall()
        return [project.model_dump(mode="json") for row in rows if (project := self._project(row))]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        if self._postgres_dsn:
            with self._connect_postgres() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT * FROM projects WHERE project_id = %s", (project_id,))
                project = self._project(cursor.fetchone())
        else:
            with self._connect_sqlite() as connection:
                project = self._project(connection.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone())
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
        connection_factory = self._connect_postgres if self._postgres_dsn else self._connect_sqlite
        with self._lock, connection_factory() as connection:
            self._insert(connection, project)
        return project.model_dump(mode="json")

    def update_project(self, project_id: str, **changes: Any) -> dict[str, Any] | None:
        current = self.get_project(project_id)
        if current is None:
            return None
        for key in ("name", "instructions", "default_model", "permission_mode", "status", "pinned_files", "memory_summary"):
            if key in changes and changes[key] is not None:
                current[key] = changes[key]
        if changes.get("root_path") is not None:
            root = _resolve_root(str(changes["root_path"]))
            current.update(
                root_path=str(root),
                repo_url=_git_value(root, "remote", "get-url", "origin"),
                branch=_git_value(root, "branch", "--show-current"),
            )
        current["updated_at"] = _now()
        project = Project.model_validate(current)
        connection_factory = self._connect_postgres if self._postgres_dsn else self._connect_sqlite
        with self._lock, connection_factory() as connection:
            self._insert(connection, project)
        return project.model_dump(mode="json")

    def delete_project(self, project_id: str) -> bool:
        """Permanently delete an archived project definition only."""

        current = self.get_project(project_id)
        if current is None:
            return False
        if current.get("status") != "archived":
            raise ValueError("Project must be archived before permanent deletion")
        if self._postgres_dsn:
            with self._lock, self._connect_postgres() as connection, connection.cursor() as cursor:
                cursor.execute("DELETE FROM projects WHERE project_id = %s", (project_id,))
                deleted = cursor.rowcount
        else:
            with self._lock, self._connect_sqlite() as connection:
                cursor = connection.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
                deleted = cursor.rowcount
        return deleted > 0

    def resolve_execution_context(
        self,
        project_id: str,
        *,
        requested_model: str | None = None,
        requested_permission: str | None = None,
    ) -> ProjectExecutionContext:
        payload = self.get_project(project_id)
        if payload is None:
            raise ValueError(f"Project not found: {project_id}")
        project = Project.model_validate(payload)
        if project.status != "active":
            raise ValueError(f"Project is archived: {project_id}")
        return ProjectExecutionContext(
            project_id=project.project_id,
            name=project.name,
            root_path=project.root_path,
            instructions=project.instructions,
            model_name=(requested_model or project.default_model).strip(),
            permission_mode=_effective_permission(project.permission_mode, requested_permission),
            memory_summary=project.memory_summary,
            pinned_files=project.pinned_files,
        )


_service: ProjectService | None = None


def get_project_service() -> ProjectService:
    global _service
    if _service is None:
        _service = ProjectService()
    return _service
