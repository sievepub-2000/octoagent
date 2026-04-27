"""Persistent store for plugin registry state."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from src.config.paths import get_paths

from .contracts import PluginRegistryEntry


@dataclass
class PluginRegistryStore:
    _lock: RLock = field(default_factory=RLock)

    @property
    def _base_dir(self) -> Path:
        return get_paths().plugin_registry_dir

    @property
    def _store_path(self) -> Path:
        return self._base_dir / "registry.json"

    def _read(self) -> dict:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        if not self._store_path.exists():
            return {"entries": []}
        try:
            with self._store_path.open(encoding="utf-8") as fh:
                raw = fh.read().strip()
            if not raw:
                return {"entries": []}
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return {"entries": []}
            return payload
        except json.JSONDecodeError:
            backup = self._store_path.with_suffix(".corrupted.json")
            self._store_path.replace(backup)
            return {"entries": []}

    def _write(self, payload: dict) -> None:
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._store_path.with_name(f".{self._store_path.name}.{os.getpid()}.{id(self)}.tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.flush()
            tmp_path.replace(self._store_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def list_entries(self) -> list[PluginRegistryEntry]:
        with self._lock:
            payload = self._read()
            return [
                PluginRegistryEntry.model_validate(entry)
                for entry in payload.get("entries", [])
            ]

    def save_entries(self, entries: list[PluginRegistryEntry]) -> None:
        with self._lock:
            payload = {"entries": [entry.model_dump(mode="json") for entry in entries]}
            self._write(payload)
