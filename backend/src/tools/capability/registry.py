"""Unified runtime capability registry for skills, plugins, MCP, hooks, and channels."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.tools.capability.agent_skills_compat import (
    build_agent_skills_compat_entries,
    compat_item_toggleable,
)
from src.runtime.config.extensions_config import ExtensionsConfig, get_extensions_config
from src.harness.hook_core import get_hook_core_service
from src.tools.plugins import get_plugin_service
from src.storage.skills import load_skills

UnifiedCapabilityKind = Literal[
    "skill",
    "plugin",
    "mcp_server",
    "hook",
    "channel",
    "command",
    "agent_persona",
    "reference",
]


class UnifiedCapabilityItem(BaseModel):
    """Normalized manifest for a runtime-managed capability."""

    capability_id: str
    kind: UnifiedCapabilityKind
    name: str
    display_name: str
    description: str = ""
    provider: str = "octoagent"
    source: str = ""
    installed: bool = True
    enabled: bool = True
    version: str | None = None
    provides: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    configurable: bool = False
    configured_enabled: bool | None = None
    activation_blockers: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UnifiedCapabilitySummary(BaseModel):
    """Aggregated counts for a capability registry snapshot."""

    total_items: int = 0
    enabled_items: int = 0
    installed_items: int = 0
    by_kind: dict[UnifiedCapabilityKind, int] = Field(default_factory=dict)
    enabled_by_kind: dict[UnifiedCapabilityKind, int] = Field(default_factory=dict)
    installed_by_kind: dict[UnifiedCapabilityKind, int] = Field(default_factory=dict)


class UnifiedCapabilityRegistrySnapshot(BaseModel):
    """Serializable snapshot of all runtime-managed capabilities."""

    generated_at: str
    items: list[UnifiedCapabilityItem] = Field(default_factory=list)
    summary: UnifiedCapabilitySummary


def _inventory_names(
    inventory: dict[str, Any] | None,
    section: str,
    key: str,
) -> set[str]:
    if not isinstance(inventory, dict):
        return set()
    bucket = inventory.get(section)
    if not isinstance(bucket, dict):
        return set()
    values = bucket.get(key)
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values if isinstance(value, str)}


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _skill_items(
    inventory: dict[str, Any] | None,
    extensions_config: ExtensionsConfig,
) -> list[UnifiedCapabilityItem]:
    loaded_skills = load_skills(enabled_only=False)
    items: list[UnifiedCapabilityItem] = []

    for skill in loaded_skills:
        source_path = skill.skill_path or skill.name
        items.append(
            UnifiedCapabilityItem(
                capability_id=f"skill:{skill.category}:{skill.name}",
                kind="skill",
                name=skill.name,
                display_name=skill.name,
                description=skill.description,
                provider="octoagent",
                source=f"skills/{skill.category}/{source_path}",
                installed=True,
                enabled=skill.enabled,
                configurable=True,
                configured_enabled=skill.enabled,
                provides=[f"skill:{skill.name}"],
                metadata={
                    "category": skill.category,
                    "relative_path": skill.relative_path.as_posix(),
                    "container_path": skill.get_container_path(),
                },
            )
        )

    if items:
        return items

    fallback_installed = _inventory_names(inventory, "installed", "skills")
    for skill_name in sorted(fallback_installed):
        items.append(
            UnifiedCapabilityItem(
                capability_id=f"skill:custom:{skill_name}",
                kind="skill",
                name=skill_name,
                display_name=skill_name,
                description="",
                provider="octoagent",
                source=f"skills/custom/{skill_name}",
                installed=True,
                enabled=extensions_config.is_skill_enabled(skill_name, "custom"),
                configurable=True,
                configured_enabled=extensions_config.is_skill_enabled(skill_name, "custom"),
                provides=[f"skill:{skill_name}"],
                metadata={"category": "custom", "fallback": True},
            )
        )
    return items


def _plugin_items() -> list[UnifiedCapabilityItem]:
    service = get_plugin_service()
    capabilities = {item.plugin_id: item for item in service.list_plugins().plugins}
    manifests = {item.plugin_id: item for item in service.list_manifests().manifests}
    registry_entries = {item.plugin_id: item for item in service.list_registry().entries}

    items: list[UnifiedCapabilityItem] = []
    for plugin_id in sorted(set(capabilities) | set(manifests) | set(registry_entries)):
        capability = capabilities.get(plugin_id)
        manifest = manifests.get(plugin_id)
        registry_entry = registry_entries.get(plugin_id)
        command_ids = manifest.commands if manifest is not None else []
        provides = [command.command_id for command in command_ids]
        requires: list[str] = []
        if capability is not None:
            requires.extend(capability.permissions)
            requires.extend(capability.runtime_requirements)
        items.append(
            UnifiedCapabilityItem(
                capability_id=f"plugin:{plugin_id}",
                kind="plugin",
                name=plugin_id,
                display_name=(capability.display_name if capability is not None else manifest.display_name if manifest is not None else plugin_id),
                description=manifest.description if manifest is not None else "",
                provider=manifest.provider if manifest is not None else "octoagent",
                source=(registry_entry.source if registry_entry is not None else "builtin"),
                installed=(registry_entry.installed if registry_entry is not None else False),
                enabled=(capability.enabled if capability is not None else False),
                version=(registry_entry.installed_version if registry_entry is not None else manifest.version if manifest is not None else None),
                provides=provides,
                requires=_dedupe_preserve_order(requires),
                configurable=False,
                configured_enabled=(capability.enabled if capability is not None else False),
                metadata={
                    "execution_mode": (capability.execution_mode if capability is not None else None),
                    "category": capability.category if capability is not None else None,
                    "installation_targets": (manifest.installation_targets if manifest is not None else []),
                    "review_flow": manifest.review_flow if manifest is not None else [],
                },
            )
        )
    return items


def _mcp_items(extensions_config: ExtensionsConfig) -> list[UnifiedCapabilityItem]:
    items: list[UnifiedCapabilityItem] = []
    for server_name, server_config in sorted(extensions_config.mcp_servers.items()):
        source = server_config.type or "stdio"
        provides = [f"mcp_server:{server_name}"]
        metadata = {
            "transport": server_config.type,
            "args": list(server_config.args),
            "command": server_config.command,
            "url": server_config.url,
            "header_names": sorted(server_config.headers.keys()),
            "oauth_enabled": bool(server_config.oauth and server_config.oauth.enabled),
        }
        items.append(
            UnifiedCapabilityItem(
                capability_id=f"mcp_server:{server_name}",
                kind="mcp_server",
                name=server_name,
                display_name=server_name,
                description=server_config.description,
                provider="mcp",
                source=source,
                installed=True,
                enabled=server_config.enabled,
                configurable=True,
                configured_enabled=server_config.enabled,
                provides=provides,
                metadata=metadata,
            )
        )
    return items


def _channel_items() -> list[UnifiedCapabilityItem]:
    try:
        from src.gateway.channels.service import ChannelService, get_channel_service

        channel_service = get_channel_service() or ChannelService.from_app_config()
        status = channel_service.get_status()
    except Exception as exc:  # pragma: no cover - defensive runtime boundary
        return [
            UnifiedCapabilityItem(
                capability_id="channel:registry",
                kind="channel",
                name="registry",
                display_name="Channel Registry",
                description="Channel registry unavailable",
                provider="octoagent",
                source="channels",
                installed=False,
                enabled=False,
                activation_blockers=["channel_registry_unavailable"],
                metadata={"error": str(exc)[:400]},
            )
        ]

    service_running = bool(status.get("service_running"))
    channels = status.get("channels")
    if not isinstance(channels, dict):
        return []

    items: list[UnifiedCapabilityItem] = []
    for name, raw_channel in sorted(channels.items()):
        if not isinstance(raw_channel, dict):
            continue
        channel_name = str(name)
        enabled = bool(raw_channel.get("enabled"))
        configured = bool(raw_channel.get("configured"))
        running = bool(raw_channel.get("running"))
        healthy = bool(raw_channel.get("healthy"))
        fields = [field for field in raw_channel.get("fields") or [] if isinstance(field, dict)]
        required_fields = [str(field.get("name")) for field in fields if field.get("required") and str(field.get("name") or "").strip()]

        activation_blockers: list[str] = []
        if enabled and not configured:
            activation_blockers.append("channel_config_missing")
        if enabled and service_running and configured and not running:
            activation_blockers.append("channel_not_running")

        transport = str(raw_channel.get("transport") or "unknown")
        integration_mode = str(raw_channel.get("integration_mode") or "native")
        provides = _dedupe_preserve_order(
            [
                f"channel:{channel_name}",
                f"transport:{transport}",
                f"integration:{integration_mode}",
                str(raw_channel.get("ingest_path") or ""),
            ]
        )

        items.append(
            UnifiedCapabilityItem(
                capability_id=f"channel:{channel_name}",
                kind="channel",
                name=channel_name,
                display_name=str(raw_channel.get("platform_label") or channel_name),
                description=str(raw_channel.get("description") or ""),
                provider="octoagent",
                source=integration_mode,
                installed=True,
                enabled=enabled,
                configurable=True,
                configured_enabled=enabled,
                provides=provides,
                requires=[f"config:{field_name}" for field_name in required_fields],
                activation_blockers=activation_blockers,
                metadata={
                    "configured": configured,
                    "running": running,
                    "healthy": healthy,
                    "service_running": service_running,
                    "integration_mode": integration_mode,
                    "transport": transport,
                    "config_path": raw_channel.get("config_path"),
                    "handler_path": raw_channel.get("handler_path"),
                    "bridge_project": raw_channel.get("bridge_project"),
                    "bridge_project_url": raw_channel.get("bridge_project_url"),
                    "ingest_path": raw_channel.get("ingest_path"),
                    "outbound_configured": bool(raw_channel.get("outbound_configured")),
                    "required_fields": required_fields,
                },
            )
        )

    return items


def _hook_items(
    inventory: dict[str, Any] | None,
    extensions_config: ExtensionsConfig,
) -> list[UnifiedCapabilityItem]:
    hook_service = get_hook_core_service()
    source_hooks = _inventory_names(inventory, "source", "hooks")
    installed_hooks = _inventory_names(inventory, "installed", "hooks")

    binding_events: dict[str, list[str]] = defaultdict(list)
    binding_enabled: dict[str, bool] = defaultdict(bool)
    for binding in hook_service.list_runtime_hooks():
        binding_events[binding.hook_id].append(binding.event)
        binding_enabled[binding.hook_id] = binding_enabled[binding.hook_id] or binding.enabled

    webhook_events: dict[str, list[str]] = {}
    webhook_enabled: dict[str, bool] = {}
    for webhook in hook_service.list_webhooks():
        webhook_events[webhook.webhook_id] = list(webhook.events)
        webhook_enabled[webhook.webhook_id] = webhook.enabled

    hook_names = sorted(source_hooks | installed_hooks | set(binding_events.keys()) | set(webhook_events.keys()))

    items: list[UnifiedCapabilityItem] = []
    for hook_name in hook_names:
        repo_known = hook_name in source_hooks or hook_name in installed_hooks
        runtime_known = hook_name in binding_events
        webhook_known = hook_name in webhook_events
        if repo_known:
            enabled = extensions_config.is_hook_enabled(hook_name)
        else:
            enabled = binding_enabled.get(hook_name, False) or webhook_enabled.get(hook_name, False)
        provides = _dedupe_preserve_order(binding_events.get(hook_name, []) + webhook_events.get(hook_name, []))
        source = "repo"
        if webhook_known and not repo_known and not runtime_known:
            source = "webhook"
        elif runtime_known and not repo_known:
            source = "runtime"

        items.append(
            UnifiedCapabilityItem(
                capability_id=f"hook:{hook_name}",
                kind="hook",
                name=hook_name,
                display_name=hook_name,
                description="Runtime hook binding" if runtime_known else "Repository hook package",
                provider="octoagent",
                source=source,
                installed=repo_known or runtime_known or webhook_known,
                enabled=enabled,
                configurable=repo_known,
                configured_enabled=enabled if repo_known else None,
                provides=provides or [f"hook:{hook_name}"],
                metadata={
                    "in_source": hook_name in source_hooks,
                    "installed_in_repo": hook_name in installed_hooks,
                    "runtime_binding_count": len(binding_events.get(hook_name, [])),
                    "webhook_registered": webhook_known,
                },
            )
        )

    return items


def _agent_skills_items(extensions_config: ExtensionsConfig) -> list[UnifiedCapabilityItem]:
    compat_config = getattr(extensions_config, "agent_skills_compat", None)
    if compat_config is None or not getattr(compat_config, "enabled", False):
        return []

    items: list[UnifiedCapabilityItem] = []
    for entry in build_agent_skills_compat_entries(compat_config):
        configured_enabled = extensions_config.get_agent_skills_item_configured_enabled(
            entry.capability_id,
            entry.kind,
        )
        effective_enabled = extensions_config.is_agent_skills_item_enabled(
            entry.capability_id,
            entry.kind,
        )
        trust_allowed = extensions_config.is_agent_skills_kind_trusted(entry.kind)
        blockers = [] if trust_allowed else [f"trust:{entry.kind}"]
        items.append(
            UnifiedCapabilityItem(
                capability_id=entry.capability_id,
                kind=entry.kind,
                name=entry.name,
                display_name=entry.display_name,
                description=entry.description,
                provider="agent-skills",
                source=entry.source,
                installed=True,
                enabled=effective_enabled,
                configurable=compat_item_toggleable(entry.kind),
                configured_enabled=configured_enabled,
                activation_blockers=blockers,
                provides=list(entry.provides),
                metadata={
                    **dict(entry.metadata),
                    "compat_trust_allowed": trust_allowed,
                    "compat_trust_level": compat_config.trust_level,
                },
            )
        )
    return items


def _build_summary(items: list[UnifiedCapabilityItem]) -> UnifiedCapabilitySummary:
    by_kind = Counter(item.kind for item in items)
    enabled_by_kind = Counter(item.kind for item in items if item.enabled)
    installed_by_kind = Counter(item.kind for item in items if item.installed)
    return UnifiedCapabilitySummary(
        total_items=len(items),
        enabled_items=sum(1 for item in items if item.enabled),
        installed_items=sum(1 for item in items if item.installed),
        by_kind=dict(by_kind),
        enabled_by_kind=dict(enabled_by_kind),
        installed_by_kind=dict(installed_by_kind),
    )


def build_capability_registry_snapshot(
    *,
    inventory: dict[str, Any] | None = None,
    extensions_config: ExtensionsConfig | None = None,
) -> UnifiedCapabilityRegistrySnapshot:
    """Build a unified capability manifest snapshot across runtime planes."""

    effective_config = extensions_config or get_extensions_config()
    items = [
        *_skill_items(inventory, effective_config),
        *_plugin_items(),
        *_mcp_items(effective_config),
        *_channel_items(),
        *_hook_items(inventory, effective_config),
        *_agent_skills_items(effective_config),
    ]
    items.sort(key=lambda item: (item.kind, item.name))
    return UnifiedCapabilityRegistrySnapshot(
        generated_at=datetime.now(UTC).isoformat(),
        items=items,
        summary=_build_summary(items),
    )
