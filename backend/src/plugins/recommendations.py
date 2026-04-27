"""Plugin capability and recommendation helpers."""

from __future__ import annotations

from .contracts import (
    PluginCapability,
    PluginCapabilityListResponse,
    PluginManifest,
    PluginRecommendationResponse,
)


class PluginRecommendationPolicy:
    """Build plugin capabilities and runtime recommendations."""

    def __init__(self, *, manifests: list[PluginManifest], registry_manager):
        self._manifests = manifests
        self._registry = registry_manager

    def list_plugins(self) -> PluginCapabilityListResponse:
        plugins: list[PluginCapability] = []
        for manifest in self._manifests:
            registry = self._registry.get_entry(manifest.plugin_id)
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

    def recommend_plugins(self, *, mode: str, card_kinds: list[str]) -> PluginRecommendationResponse:
        kinds = {kind for kind in card_kinds if kind}
        plugin_ids: list[str] = []
        review_entry = self._registry.get_entry("compound-engineering-review")
        if review_entry and review_entry.enabled and (mode in {"branch", "group"} or "review" in kinds or "checkpoint" in kinds):
            plugin_ids.append("compound-engineering-review")
        runtime_entry = self._registry.get_entry("workspace-runtime-bridge")
        if runtime_entry and runtime_entry.enabled and ({"agent", "tooling", "research"} & kinds or mode in {"single", "branch", "group"}):
            plugin_ids.append("workspace-runtime-bridge")
        return PluginRecommendationResponse(plugin_ids=plugin_ids)
