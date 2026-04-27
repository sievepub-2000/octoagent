"""Persistent store for browser runtime sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from uuid import uuid4

from src.config.paths import get_paths

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
        self._base_dir.mkdir(parents=True, exist_ok=True)
        if not self._store_path.exists():
            return {"sessions": []}
        with self._store_path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def _write(self, payload: dict) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self._base_dir / f".sessions.{uuid4().hex}.tmp"
        with temp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        temp_path.replace(self._store_path)

    def list_sessions(self) -> list[BrowserExecutionSession]:
        with self._lock:
            payload = self._read()
            return [
                BrowserExecutionSession.model_validate(session)
                for session in payload.get("sessions", [])
            ]

    def save_sessions(self, sessions: list[BrowserExecutionSession]) -> None:
        with self._lock:
            payload = {"sessions": [session.model_dump(mode="json") for session in sessions]}
            self._write(payload)
