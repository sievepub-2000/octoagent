"""Persistent store for task workspaces and agent transcript state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from src.config.paths import get_paths

from .contracts import AgentMessage, TaskWorkspace
from .workflow_files import WorkflowFileManager


@dataclass
class TaskWorkspaceStore:
    _lock: RLock = field(default_factory=RLock)
    _files: WorkflowFileManager = field(default_factory=WorkflowFileManager)

    @property
    def _base_dir(self) -> Path:
        return get_paths().workflow_tasks_state_dir

    @property
    def _store_path(self) -> Path:
        return self._base_dir / "store.json"

    def _default_payload(self) -> dict:
        return {"workspaces": [], "agent_messages": {}}

    def _read(self) -> dict:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        if not self._store_path.exists():
            return self._default_payload()
        with self._store_path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def _write(self, payload: dict) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        with self._store_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    def list_workspaces(self) -> list[TaskWorkspace]:
        with self._lock:
            payload = self._read()
            return [
                TaskWorkspace.model_validate(workspace)
                for workspace in payload.get("workspaces", [])
            ]

    def save_workspaces(self, workspaces: list[TaskWorkspace]) -> None:
        with self._lock:
            payload = self._read()
            payload["workspaces"] = [workspace.model_dump(mode="json") for workspace in workspaces]
            self._write(payload)

    def list_agent_messages(self, task_id: str, agent_id: str) -> list[AgentMessage]:
        with self._lock:
            task_local_messages = self._files.read_agent_conversation(task_id, agent_id)
            if task_local_messages is not None:
                return [
                    AgentMessage.model_validate(message)
                    for message in task_local_messages
                ]
            payload = self._read()
            key = f"{task_id}:{agent_id}"
            return [
                AgentMessage.model_validate(message)
                for message in payload.get("agent_messages", {}).get(key, [])
            ]

    def save_agent_messages(
        self,
        task_id: str,
        agent_id: str,
        messages: list[AgentMessage],
        *,
        agent_name: str | None = None,
    ) -> None:
        with self._lock:
            self._files.write_agent_conversation(
                task_id,
                agent_id=agent_id,
                agent_name=agent_name,
                messages=[message.model_dump(mode="json") for message in messages],
            )
            payload = self._read()
            key = f"{task_id}:{agent_id}"
            if key in payload.get("agent_messages", {}):
                payload.setdefault("agent_messages", {}).pop(key, None)
            self._write(payload)

    def delete_workspace(self, task_id: str) -> bool:
        with self._lock:
            payload = self._read()
            workspaces = payload.get("workspaces", [])
            remaining_workspaces = [
                workspace for workspace in workspaces if workspace.get("task_id") != task_id
            ]
            agent_messages = payload.get("agent_messages", {})
            remaining_messages = {
                key: value
                for key, value in agent_messages.items()
                if not key.startswith(f"{task_id}:")
            }
            changed = (
                len(remaining_workspaces) != len(workspaces)
                or len(remaining_messages) != len(agent_messages)
            )
            if not changed:
                return False
            payload["workspaces"] = remaining_workspaces
            payload["agent_messages"] = remaining_messages
            self._write(payload)
            return True
