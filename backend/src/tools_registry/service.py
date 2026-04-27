from __future__ import annotations

from src.config.app_config import get_app_config
from src.config.extensions_config import get_extensions_config
from src.config.paths import resolve_configured_default_model_name
from src.config.subagents_config import get_subagents_app_config
from src.plugins import get_plugin_service
from src.skills import load_skills
from src.subagents.executor import get_subagent_runtime_snapshot
from src.tools import get_available_tools

from .builtin_catalog import ToolRegistryBuiltinCatalog
from .channels import ToolRegistryChannelReader
from .contracts import (
    ToolCapabilityRegistryResponse,
    ToolRegistryMcpItem,
    ToolRegistryPluginItem,
    ToolRegistryRuntime,
    ToolRegistrySkillItem,
    ToolRegistrySummary,
)


class ToolRegistryService:
    def __init__(
        self,
        *,
        extensions_config_getter=get_extensions_config,
        plugin_service_getter=get_plugin_service,
        skills_loader=load_skills,
        app_config_getter=get_app_config,
        subagents_config_getter=get_subagents_app_config,
        runtime_snapshot_getter=get_subagent_runtime_snapshot,
        builtin_catalog: ToolRegistryBuiltinCatalog | None = None,
        channel_reader: ToolRegistryChannelReader | None = None,
    ):
        self._extensions_config_getter = extensions_config_getter
        self._plugin_service_getter = plugin_service_getter
        self._skills_loader = skills_loader
        self._app_config_getter = app_config_getter
        self._subagents_config_getter = subagents_config_getter
        self._runtime_snapshot_getter = runtime_snapshot_getter
        self._builtin_catalog = builtin_catalog or ToolRegistryBuiltinCatalog(
            get_available_tools_fn=get_available_tools
        )
        self._channel_reader = channel_reader or ToolRegistryChannelReader()

    def build_registry(self) -> ToolCapabilityRegistryResponse:
        extensions = self._extensions_config_getter()
        mcp_items = [
            ToolRegistryMcpItem(
                name=name,
                enabled=cfg.enabled,
                transport=cfg.type,
                description=cfg.description,
            )
            for name, cfg in sorted(extensions.mcp_servers.items(), key=lambda item: item[0])
        ]

        skill_items = [
            ToolRegistrySkillItem(
                name=skill.name,
                enabled=skill.enabled,
                category=skill.category,
                description=skill.description,
            )
            for skill in sorted(self._skills_loader(enabled_only=False), key=lambda item: item.name)
        ]

        plugin_items = [
            ToolRegistryPluginItem(
                plugin_id=plugin.plugin_id,
                display_name=plugin.display_name,
                enabled=plugin.enabled,
                category=plugin.category,
            )
            for plugin in sorted(
                self._plugin_service_getter().list_plugins().plugins,
                key=lambda item: item.plugin_id,
            )
        ]

        channel_items = self._channel_reader.read()
        try:
            builtin_items = self._builtin_catalog.list_items()
        except Exception:
            builtin_items = []

        app_config = self._app_config_getter()
        subagent_config = self._subagents_config_getter()
        runtime_snapshot = self._runtime_snapshot_getter()
        raw_active_subagents = runtime_snapshot.get("active_subagents", 0)
        active_subagents = (
            int(raw_active_subagents)
            if isinstance(raw_active_subagents, (int, float))
            else 0
        )

        summary = ToolRegistrySummary(
            mcp_total=len(mcp_items),
            mcp_enabled=sum(1 for item in mcp_items if item.enabled),
            skills_total=len(skill_items),
            skills_enabled=sum(1 for item in skill_items if item.enabled),
            plugins_total=len(plugin_items),
            plugins_enabled=sum(1 for item in plugin_items if item.enabled),
            channels_total=len(channel_items),
            channels_enabled=sum(1 for item in channel_items if item.enabled),
            builtin_tools_total=len(builtin_items),
        )
        default_model_name = resolve_configured_default_model_name(
            model.name for model in app_config.models
        )
        runtime = ToolRegistryRuntime(
            default_model=default_model_name,
            total_models=len(app_config.models),
            active_subagents=active_subagents,
            max_concurrent_subagents=subagent_config.max_concurrent_subagents,
        )
        return ToolCapabilityRegistryResponse(
            summary=summary,
            runtime=runtime,
            mcp=mcp_items,
            skills=skill_items,
            plugins=plugin_items,
            channels=channel_items,
            builtin_tools=builtin_items,
        )
