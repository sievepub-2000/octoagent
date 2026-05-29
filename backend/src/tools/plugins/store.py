"""Persistent store for plugin registry state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from src.runtime.config.effective import RuntimeJsonStore
from src.runtime.config.paths import get_paths

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
        return RuntimeJsonStore(self._store_path, {"entries": []}).read()

    def _write(self, payload: dict) -> None:
        RuntimeJsonStore(self._store_path, {"entries": []}).write(payload)

    def list_entries(self) -> list[PluginRegistryEntry]:
        with self._lock:
            payload = self._read()
            return [PluginRegistryEntry.model_validate(entry) for entry in payload.get("entries", [])]

    def save_entries(self, entries: list[PluginRegistryEntry]) -> None:
        with self._lock:
            payload = {"entries": [entry.model_dump(mode="json") for entry in entries]}
            self._write(payload)
