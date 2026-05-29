"""Persistent store for system execution sessions, snapshots, and audit entries."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from src.runtime.config.effective import RuntimeJsonStore
from src.runtime.config.paths import get_paths

from .contracts import (
    SystemExecutionAuditEntry,
    SystemExecutionDesktopSnapshot,
    SystemExecutionSession,
)


@dataclass
class SystemExecutionStore:
    _lock: RLock = field(default_factory=RLock)

    @property
    def _base_dir(self) -> Path:
        return get_paths().system_execution_dir

    @property
    def _store_path(self) -> Path:
        return self._base_dir / "store.json"

    def _default_payload(self) -> dict:
        return {"sessions": {}, "snapshots": {}, "audits": {}}

    def _read(self) -> dict:
        return RuntimeJsonStore(self._store_path, self._default_payload()).read()

    def _write(self, payload: dict) -> None:
        RuntimeJsonStore(self._store_path, self._default_payload()).write(payload)

    def save_session(self, session: SystemExecutionSession) -> None:
        with self._lock:
            payload = self._read()
            payload.setdefault("sessions", {})[session.session_id] = session.model_dump(mode="json")
            self._write(payload)

    def get_session(self, session_id: str) -> SystemExecutionSession | None:
        with self._lock:
            payload = self._read()
            data = payload.get("sessions", {}).get(session_id)
            return SystemExecutionSession.model_validate(data) if data is not None else None

    def list_sessions(
        self,
        *,
        target: str | None = None,
        related_task_id: str | None = None,
        limit: int = 20,
    ) -> list[SystemExecutionSession]:
        with self._lock:
            payload = self._read()
            sessions = [SystemExecutionSession.model_validate(entry) for entry in payload.get("sessions", {}).values()]

        if target is not None:
            sessions = [session for session in sessions if session.target == target]
        if related_task_id is not None:
            sessions = [session for session in sessions if session.related_task_id == related_task_id]

        sessions.sort(
            key=lambda session: session.updated_at or "",
            reverse=True,
        )
        return sessions[: max(1, limit)]

    def save_snapshot(self, snapshot: SystemExecutionDesktopSnapshot) -> None:
        with self._lock:
            payload = self._read()
            payload.setdefault("snapshots", {})[snapshot.session_id] = snapshot.model_dump(mode="json")
            self._write(payload)

    def get_snapshot(self, session_id: str) -> SystemExecutionDesktopSnapshot | None:
        with self._lock:
            payload = self._read()
            data = payload.get("snapshots", {}).get(session_id)
            return SystemExecutionDesktopSnapshot.model_validate(data) if data is not None else None

    def append_audits(
        self,
        session_id: str,
        entries: list[SystemExecutionAuditEntry],
    ) -> None:
        with self._lock:
            payload = self._read()
            existing = payload.setdefault("audits", {}).setdefault(session_id, [])
            existing.extend(entry.model_dump(mode="json") for entry in entries)
            self._write(payload)

    def get_audits(self, session_id: str) -> list[SystemExecutionAuditEntry]:
        with self._lock:
            payload = self._read()
            return [SystemExecutionAuditEntry.model_validate(entry) for entry in payload.get("audits", {}).get(session_id, [])]
