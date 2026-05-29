"""Persistent store for browser runtime sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from src.runtime.config.effective import RuntimeJsonStore
from src.runtime.config.paths import get_paths

from .contracts import BrowserExecutionSession


@dataclass
class BrowserRuntimeStore:
    _lock: RLock = field(default_factory=RLock)

    @property
    def _base_dir(self) -> Path:
        return get_paths().browser_runtime_dir

    @property
    def _store_path(self) -> Path:
        return self._base_dir / "sessions.json"

    def _read(self) -> dict:
        return RuntimeJsonStore(self._store_path, {"sessions": []}).read()

    def _write(self, payload: dict) -> None:
        RuntimeJsonStore(self._store_path, {"sessions": []}).write(payload)

    def list_sessions(self) -> list[BrowserExecutionSession]:
        with self._lock:
            payload = self._read()
            return [BrowserExecutionSession.model_validate(session) for session in payload.get("sessions", [])]

    def save_sessions(self, sessions: list[BrowserExecutionSession]) -> None:
        with self._lock:
            payload = {"sessions": [session.model_dump(mode="json") for session in sessions]}
            self._write(payload)
