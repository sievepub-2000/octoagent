"""Project-scoped memory isolation service."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE = os.environ.get("OCTOAGENT_WORKSPACE", "workspace/default")
PROJECT_MEMORIES_DIR = os.environ.get(
    "PROJECT_MEMORIES_DIR",
    os.path.join(DEFAULT_WORKSPACE, "project_memories"),
)


def _ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def _project_memory_path(project_id: str) -> str:
    return os.path.join(PROJECT_MEMORIES_DIR, f"{project_id}.json")


def _index_path() -> str:
    return os.path.join(PROJECT_MEMORIES_DIR, "_system_projects.json")


def _read_json(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_json(path: str, data: dict[str, Any]) -> None:
    _ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class ProjectMemoryService:
    """Per-project memory isolation backed by separate JSON files."""

    @staticmethod
    def project_memory_path(project_id: str) -> str:
        return _project_memory_path(project_id)

    @staticmethod
    def load_project_memory(project_id: str) -> dict[str, Any]:
        return _read_json(_project_memory_path(project_id))

    @staticmethod
    def save_project_memory(project_id: str, summary: str, metadata: dict | None = None) -> None:
        path = _project_memory_path(project_id)
        memory = _read_json(path)
        memory["summary"] = summary
        memory["metadata"] = dict(metadata) if metadata else memory.get("metadata", {})
        memory["updated_at"] = datetime.now(UTC).isoformat()
        if "created_at" not in memory:
            memory["created_at"] = memory["updated_at"]
        _write_json(path, memory)
        idx = _read_json(_index_path())
        idx[project_id] = {
            "summary": summary[:300],
            "updated_at": memory["updated_at"],
            "created_at": memory.get("created_at", memory["updated_at"]),
            "tags": (metadata or {}).get("tags", []),
            "status": (metadata or {}).get("status", "active"),
        }
        _write_json(_index_path(), idx)

    @staticmethod
    def ensure_project_memory(project_id: str, name: str, goal: str) -> dict:
        path = _project_memory_path(project_id)
        if not os.path.exists(path):
            return ProjectMemoryService.save_project_memory(
                project_id, f"Project: {name}. Goal: {goal}",
                {"status": "active", "tags": []},
            )
        return _read_json(path)

    @staticmethod
    def append_project_memory_entry(project_id: str, entry_type: str, content: str, source: str | None = None) -> None:
        path = _project_memory_path(project_id)
        memory = _read_json(path)
        entries = memory.setdefault("entries", [])
        entries.append({
            "type": entry_type, "content": content,
            "source": source or "agent",
            "timestamp": datetime.now(UTC).isoformat(),
        })
        memory["updated_at"] = datetime.now(UTC).isoformat()
        if "created_at" not in memory:
            memory["created_at"] = memory["updated_at"]
        _write_json(path, memory)
        idx = _read_json(_index_path())
        if project_id in idx:
            idx[project_id]["updated_at"] = memory["updated_at"]
            _write_json(_index_path(), idx)

    @staticmethod
    def list_all_project_summaries() -> list[dict[str, Any]]:
        idx = _read_json(_index_path())
        return [
            {
                "project_id": pid, "summary": info.get("summary", ""),
                "status": info.get("status", "active"), "tags": info.get("tags", []),
                "updated_at": info.get("updated_at"), "created_at": info.get("created_at"),
            }
            for pid, info in idx.items()
        ]

    @staticmethod
    def delete_project_memory(project_id: str) -> bool:
        path = _project_memory_path(project_id)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        idx = _read_json(_index_path())
        idx.pop(project_id, None)
        _write_json(_index_path(), idx)
        return True


_mem_service = ProjectMemoryService()


def get_project_memory_service() -> ProjectMemoryService:
    return _mem_service
