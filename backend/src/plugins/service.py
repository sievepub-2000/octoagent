"""Contract-first service facade for plugin capabilities."""

from __future__ import annotations

from datetime import UTC, datetime

from .contracts import (
    PluginCapability,
    PluginCapabilityListResponse,
    PluginCommand,
    PluginInstallRequest,
    PluginManifest,
    PluginManifestListResponse,
    PluginRecommendationResponse,
    PluginRegistryEntry,
    PluginRegistryResponse,
    PluginToggleRequest,
)
from .store import PluginRegistryStore


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


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
        persisted_entries = {
            entry.plugin_id: entry
            for entry in self._store.list_entries()
        }
        self._registry = default_registry | persisted_entries
        self._persist_registry()

    def _seed_manifests(self) -> list[PluginManifest]:
        return [
            PluginManifest(
                plugin_id="compound-engineering-review",
                display_name="Compound Engineering Review",
                version="0.1.0",
                description=(
                    "Review-oriented engineering workflow plugin with explicit plan, work, "
                    "review, and compound capture stages."
                ),
                commands=[
                    PluginCommand(
                        command_id="ce:brainstorm",
                        title="Brainstorm",
                        stage="brainstorm",
                        summary="Refine problem framing before technical planning.",
                    ),
                    PluginCommand(
                        command_id="ce:plan",
                        title="Plan",
                        stage="plan",
                        summary="Produce an implementation plan with risks, interfaces, and sequencing.",
                    ),
                    PluginCommand(
                        command_id="ce:review",
                        title="Review",
                        stage="review",
                        summary="Run pre-merge review with artifact and policy awareness.",
                    ),
                ],
                installation_targets=["codex", "claude", "opencode"],
                review_flow=["brainstorm", "plan", "work", "review", "compound"],
            ),
            PluginManifest(
                plugin_id="workspace-runtime-bridge",
                display_name="Workspace Runtime Bridge",
                version="0.1.0",
                description="Bind task-workspace cards to runtime-facing command surfaces and approvals.",
                commands=[
                    PluginCommand(
                        command_id="wrb:bind",
                        title="Bind Runtime",
                        stage="runtime",
                        summary="Attach runtime bindings and policy labels to task cards.",
                    ),
                    PluginCommand(
                        command_id="wrb:review",
                        title="Review Runtime",
                        stage="review",
                        summary="Review runtime side effects and approval checkpoints before execution.",
                    ),
                ],
                installation_targets=["octoagent", "codex"],
                review_flow=["plan", "runtime", "review"],
            ),
        ]

    def list_manifests(self) -> PluginManifestListResponse:
        return PluginManifestListResponse(manifests=list(self._manifests))

    def list_plugins(self) -> PluginCapabilityListResponse:
        plugins: list[PluginCapability] = []
        for manifest in self._manifests:
            registry = self._registry.get(manifest.plugin_id)
            category = "engineering" if "review" in manifest.plugin_id else "runtime"
            permissions = (
                ["task_review", "artifact_review", "policy_review"]
                if category == "engineering"
                else ["runtime_bind", "approval_review", "task_graph_access"]
            )
            runtime_requirements = (
                ["task_workspace", "agent_transcript", "artifact_access"]
                if category == "engineering"
                else ["task_workspace", "orchestration_graph", "system_execution_policy"]
            )
            plugins.append(
                PluginCapability(
                    plugin_id=manifest.plugin_id,
                    display_name=manifest.display_name,
                    category=category,  # type: ignore[arg-type]
                    execution_mode="workflow",
                    manifest=manifest,
                    permissions=permissions,
                    runtime_requirements=runtime_requirements,
                    enabled=registry.enabled if registry is not None else False,
                )
            )
        return PluginCapabilityListResponse(plugins=plugins)

    def list_registry(self) -> PluginRegistryResponse:
        return PluginRegistryResponse(
            entries=sorted(self._registry.values(), key=lambda item: item.plugin_id)
        )

    def _persist_registry(self) -> None:
        self._store.save_entries(list(self._registry.values()))

    def recommend_plugins(
        self,
        *,
        mode: str,
        card_kinds: list[str],
    ) -> PluginRecommendationResponse:
        kinds = {kind for kind in card_kinds if kind}
        plugin_ids: list[str] = []

        review_entry = self._registry.get("compound-engineering-review")
        if review_entry and review_entry.enabled and (
            mode in {"branch", "group"} or "review" in kinds or "checkpoint" in kinds
        ):
            plugin_ids.append("compound-engineering-review")

        runtime_entry = self._registry.get("workspace-runtime-bridge")
        if runtime_entry and runtime_entry.enabled and (
            {"agent", "tooling", "research"} & kinds or mode in {"single", "branch", "group"}
        ):
            plugin_ids.append("workspace-runtime-bridge")

        return PluginRecommendationResponse(plugin_ids=plugin_ids)

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

    def set_plugin_enabled(
        self,
        plugin_id: str,
        request: PluginToggleRequest,
    ) -> PluginRegistryEntry | None:
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
