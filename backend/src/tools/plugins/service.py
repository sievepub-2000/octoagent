"""Contract-first service facade for plugin capabilities."""

from __future__ import annotations

from datetime import UTC, datetime

from .catalog import PluginCatalog
from src.utils.datetime import utc_now_iso as _utc_now
from .contracts import (
    PluginCapability,
    PluginCapabilityListResponse,
    PluginInstallRequest,
    PluginManifest,
    PluginManifestListResponse,
    PluginRecommendationResponse,
    PluginRegistryEntry,
    PluginRegistryResponse,
    PluginToggleRequest,
)
from .store import PluginRegistryStore




_PLUGIN_CATEGORY: dict[str, str] = {
    "compound-engineering-review": "engineering",
    "workspace-runtime-bridge": "runtime",
    "agent-rules-skill-pack": "engineering",
    "goalbuddy-workflow": "engineering",
    "content-experiment-workflow": "engineering",
    "diagram-generation-toolkit": "integration",
    "html-deck-generator": "integration",
    "ian-handdrawn-ppt": "integration",
    "mirage-vfs-bridge": "runtime",
    "peekaboo-vision-mcp": "integration",
    "lightseek-smg-gateway": "runtime",
    "tokenspeed-model-benchmark": "runtime",
    "witr-runtime-diagnostics": "runtime",
    "photo-agents-vision-workflow": "engineering",
    "cloakbrowser-controlled-automation": "integration",
    "lumibot-research-strategy": "integration",
}

_PLUGIN_EXECUTION_MODE: dict[str, str] = {
    "agent-rules-skill-pack": "advisory",
    "goalbuddy-workflow": "workflow",
    "content-experiment-workflow": "workflow",
    "diagram-generation-toolkit": "tooling",
    "html-deck-generator": "tooling",
    "ian-handdrawn-ppt": "tooling",
    "mirage-vfs-bridge": "tooling",
    "peekaboo-vision-mcp": "tooling",
    "lightseek-smg-gateway": "tooling",
    "tokenspeed-model-benchmark": "tooling",
    "witr-runtime-diagnostics": "tooling",
    "photo-agents-vision-workflow": "workflow",
    "cloakbrowser-controlled-automation": "tooling",
    "lumibot-research-strategy": "workflow",
}

_PLUGIN_REQUIREMENTS: dict[str, list[str]] = {
    "diagram-generation-toolkit": ["image_or_svg_output", "artifact_access"],
    "html-deck-generator": ["artifact_access", "webui_preview"],
    "ian-handdrawn-ppt": ["image_generation_model", "artifact_access"],
    "mirage-vfs-bridge": ["task_workspace", "filesystem_policy"],
    "peekaboo-vision-mcp": ["mcp_loader", "screen_capture_runtime"],
    "lightseek-smg-gateway": ["model_gateway", "routing_policy"],
    "tokenspeed-model-benchmark": ["gpu_runtime", "model_benchmark_policy"],
    "witr-runtime-diagnostics": ["process_snapshot", "system_execution_policy"],
    "cloakbrowser-controlled-automation": ["browser_runtime", "user_authorization"],
    "lumibot-research-strategy": ["market_data_config", "paper_trading_only"],
}


class PluginService:
    """Expose plugin manifests plus registry/install state."""

    def __init__(self):
        self._manifests = self._seed_manifests()
        self._store = PluginRegistryStore()
        default_registry: dict[str, PluginRegistryEntry] = {
            manifest.plugin_id: PluginRegistryEntry(
                plugin_id=manifest.plugin_id,
                installed=True,
                enabled=True,
                installed_version=manifest.version,
                source="builtin",
                installed_at=_utc_now(),
            )
            for manifest in self._manifests
        }
        persisted_entries = {entry.plugin_id: entry for entry in self._store.list_entries()}
        self._registry = default_registry | persisted_entries
        self._persist_registry()

    def _seed_manifests(self) -> list[PluginManifest]:
        return PluginCatalog().seed_manifests()

    def list_manifests(self) -> PluginManifestListResponse:
        return PluginManifestListResponse(manifests=list(self._manifests))

    def list_plugins(self) -> PluginCapabilityListResponse:
        plugins: list[PluginCapability] = []
        for manifest in self._manifests:
            registry = self._registry.get(manifest.plugin_id)
            category = _PLUGIN_CATEGORY.get(manifest.plugin_id, "runtime")
            execution_mode = _PLUGIN_EXECUTION_MODE.get(manifest.plugin_id, "workflow")
            if category == "engineering":
                permissions = ["task_review", "artifact_review", "policy_review"]
                runtime_requirements = ["task_workspace", "agent_transcript", "artifact_access"]
            elif category == "integration":
                permissions = ["tool_invocation", "artifact_write", "policy_review"]
                runtime_requirements = ["task_workspace", "tool_registry", "approval_policy"]
            else:
                permissions = ["runtime_bind", "approval_review", "task_graph_access"]
                runtime_requirements = ["task_workspace", "orchestration_graph", "system_execution_policy"]
            runtime_requirements.extend(_PLUGIN_REQUIREMENTS.get(manifest.plugin_id, []))
            plugins.append(
                PluginCapability(
                    plugin_id=manifest.plugin_id,
                    display_name=manifest.display_name,
                    category=category,  # type: ignore[arg-type]
                    execution_mode=execution_mode,  # type: ignore[arg-type]
                    manifest=manifest,
                    permissions=permissions,
                    runtime_requirements=runtime_requirements,
                    enabled=registry.enabled if registry is not None else False,
                )
            )
        return PluginCapabilityListResponse(plugins=plugins)

    def list_registry(self) -> PluginRegistryResponse:
        return PluginRegistryResponse(entries=sorted(self._registry.values(), key=lambda item: item.plugin_id))

    def _persist_registry(self) -> None:
        self._store.save_entries(list(self._registry.values()))

    def recommend_plugins(self, *, mode: str, card_kinds: list[str]) -> PluginRecommendationResponse:
        kinds = {kind for kind in card_kinds if kind}
        plugin_ids: list[str] = []

        review_entry = self._registry.get("compound-engineering-review")
        if review_entry and review_entry.enabled and (mode in {"branch", "group"} or "review" in kinds or "checkpoint" in kinds):
            plugin_ids.append("compound-engineering-review")

        runtime_entry = self._registry.get("workspace-runtime-bridge")
        if runtime_entry and runtime_entry.enabled and ({"agent", "tooling", "research"} & kinds or mode in {"single", "branch", "group"}):
            plugin_ids.append("workspace-runtime-bridge")

        if {"diagram", "report", "artifact"} & kinds:
            plugin_ids.extend(["diagram-generation-toolkit", "html-deck-generator", "ian-handdrawn-ppt"])
        if {"agent", "workflow", "planning"} & kinds:
            plugin_ids.extend(["goalbuddy-workflow", "agent-rules-skill-pack", "photo-agents-vision-workflow"])
        if {"runtime", "diagnostics", "tooling"} & kinds:
            plugin_ids.extend(["witr-runtime-diagnostics", "mirage-vfs-bridge"])
        if {"model", "gateway", "benchmark"} & kinds:
            plugin_ids.extend(["lightseek-smg-gateway", "tokenspeed-model-benchmark"])

        return PluginRecommendationResponse(plugin_ids=list(dict.fromkeys(plugin_ids)))

    def install_plugin(self, request: PluginInstallRequest, *, created_at: str | None = None) -> PluginRegistryEntry | None:
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
        """Remove a plugin from the registry."""
        if plugin_id not in self._registry:
            return False
        del self._registry[plugin_id]
        self._persist_registry()
        return True


_service = PluginService()


def get_plugin_service() -> PluginService:
    return _service
