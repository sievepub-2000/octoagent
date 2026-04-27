"""Plugin registry state manager."""

from __future__ import annotations

from datetime import UTC, datetime

from .contracts import (
    PluginInstallRequest,
    PluginManifest,
    PluginRegistryEntry,
    PluginRegistryResponse,
    PluginToggleRequest,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class PluginRegistryManager:
    """Manage installed/enabled plugin registry state."""

    def __init__(self, *, store, manifests: list[PluginManifest]):
        self._store = store
        self._manifests = manifests
        default_registry = {
            manifest.plugin_id: PluginRegistryEntry(
                plugin_id=manifest.plugin_id,
                installed=True,
                enabled=True,
                installed_version=manifest.version,
                source="builtin",
                installed_at=_utc_now(),
            )
            for manifest in manifests
        }
        persisted_entries = {entry.plugin_id: entry for entry in self._store.list_entries()}
        self._registry = default_registry | persisted_entries
        self._persist_registry()

    def list_registry(self) -> PluginRegistryResponse:
        return PluginRegistryResponse(entries=sorted(self._registry.values(), key=lambda item: item.plugin_id))

    def get_entry(self, plugin_id: str) -> PluginRegistryEntry | None:
        return self._registry.get(plugin_id)

    def install_plugin(
        self,
        request: PluginInstallRequest,
        *,
        created_at: str | None = None,
    ) -> PluginRegistryEntry | None:
        manifest = next((item for item in self._manifests if item.plugin_id == request.plugin_id), None)
        if manifest is None:
            return None
        entry = PluginRegistryEntry(
            plugin_id=manifest.plugin_id,
            installed=True,
            enabled=request.enable_after_install,
            installed_version=manifest.version,
            source=request.source,
            installed_at=created_at or _utc_now(),
        )
        self._registry[manifest.plugin_id] = entry
        self._persist_registry()
        return entry

    def set_plugin_enabled(self, plugin_id: str, request: PluginToggleRequest) -> PluginRegistryEntry | None:
        entry = self._registry.get(plugin_id)
        if entry is None:
            return None
        entry.enabled = request.enabled
        self._persist_registry()
        return entry

    def uninstall_plugin(self, plugin_id: str) -> bool:
        if plugin_id not in self._registry:
            return False
        del self._registry[plugin_id]
        self._persist_registry()
        return True

    def _persist_registry(self) -> None:
        self._store.save_entries(list(self._registry.values()))
