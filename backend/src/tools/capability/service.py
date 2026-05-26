"""CapabilityCore service for inventory and migration orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from src.runtime.config.extensions_config import (
    CompatCapabilityStateConfig,
    ExtensionsConfig,
    HookStateConfig,
    McpServerConfig,
    SkillStateConfig,
    get_extensions_config,
    reload_extensions_config,
)
from src.storage.skills import load_skills
from src.storage.skills.loader import get_skills_root_path, invalidate_skills_cache
from src.utils.agent_tool_guide import async_refresh_agent_tool_guide
from src.utils.json_atomic import write_json_atomic

from .agent_skills_compat import (
    build_agent_skills_compat_entries,
    compat_item_toggleable,
    compat_item_trust_allowed,
    resolve_agent_skills_source_root,
)
from .registry import build_capability_registry_snapshot

logger = logging.getLogger(__name__)

CapabilityCategory = Literal["skills", "agents", "instructions", "hooks", "mcp"]
CopyStatus = Literal["installed", "updated", "skipped"]


def _repo_root() -> Path:
    return get_skills_root_path().parent


def _source_root() -> Path:
    return Path(os.getenv("OCTO_AGENT_CAPABILITY_SOURCE", str(_repo_root()))).expanduser().resolve()


def _source_paths() -> dict[CapabilityCategory, Path]:
    root = _source_root()
    return {
        "skills": root / ".github" / "skills",
        "agents": root / ".github" / "agents",
        "instructions": root / ".github" / "instructions",
        "hooks": root / ".github" / "hooks",
        "mcp": root / ".vscode" / "mcp.json",
    }


def _repo_paths() -> dict[CapabilityCategory, Path]:
    root = _repo_root()
    return {
        "skills": root / "skills" / "custom",
        "agents": root / ".github" / "agents",
        "instructions": root / ".github" / "instructions",
        "hooks": root / ".github" / "hooks",
        "mcp": root / "extensions_config.json",
    }


def _list_dir_names(path: Path) -> list[str]:
    if not path.exists():
        return []
    return sorted(entry.name for entry in path.iterdir() if entry.is_dir())


def _list_file_names(path: Path, suffix: str) -> list[str]:
    if not path.exists():
        return []
    return sorted(entry.name for entry in path.iterdir() if entry.is_file() and entry.name.endswith(suffix))


def _load_source_mcp_servers(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    servers = payload.get("servers", {})
    return servers if isinstance(servers, dict) else {}


def _copy_directory(source: Path, target: Path) -> tuple[Literal["installed", "skipped"], str]:
    if target.exists():
        return "skipped", "already exists"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    return "installed", "copied"


def _copy_file(source: Path, target: Path) -> tuple[CopyStatus, str]:
    source_text = source.read_text(encoding="utf-8")
    if target.exists():
        if target.read_text(encoding="utf-8") == source_text:
            return "skipped", "already up to date"
        status: CopyStatus = "updated"
    else:
        status = "installed"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source_text, encoding="utf-8")
    return status, "copied"


def _parse_capability_id(capability_id: str) -> tuple[str, str, str | None]:
    if capability_id.startswith("agent_skills:"):
        _, kind, name = capability_id.split(":", 2)
        return "agent_skills", kind, name
    if capability_id.startswith("skill:"):
        _, category, name = capability_id.split(":", 2)
        return "skill", name, category
    if capability_id.startswith("hook:"):
        _, name = capability_id.split(":", 1)
        return "hook", name, None
    if capability_id.startswith("mcp_server:"):
        _, name = capability_id.split(":", 1)
        return "mcp_server", name, None
    if capability_id.startswith("plugin:"):
        _, name = capability_id.split(":", 1)
        return "plugin", name, None
    return "unknown", capability_id, None


class CapabilityCoreService:
    """Stable boundary for capability inventory and migration flows."""

    _cached_inventory: dict[str, object] | None = None

    def __init__(self) -> None:
        self._listeners_registered = False
        self._last_inventory_built_at: str | None = None
        self._last_migration_at: str | None = None
        self._last_migration_summary: dict[str, object] | None = None
        self._audit_events: list[dict[str, object]] = []

    def _record_audit(self, event: str, details: dict[str, object] | None = None) -> None:
        self._audit_events.insert(
            0,
            {
                "event": event,
                "created_at": datetime.now(UTC).isoformat(),
                "details": dict(details or {}),
            },
        )
        del self._audit_events[20:]

    def register_hook_listeners(self) -> None:
        """Wire HookCore listeners so inventory auto-refreshes on capability changes."""
        if self._listeners_registered:
            return
        from src.harness.hook_core import (
            EVENT_CAPABILITY_REFRESH,
            EVENT_WORKSPACE_CREATED,
            get_hook_core_service,
        )

        hook_svc = get_hook_core_service()
        hook_svc.on(EVENT_CAPABILITY_REFRESH, self._on_capability_refresh)
        hook_svc.on(EVENT_WORKSPACE_CREATED, self._on_workspace_created)
        self._listeners_registered = True
        self._record_audit("listeners.registered", {"source": "capability_core"})

    def _on_capability_refresh(self, payload: dict) -> None:
        self._cached_inventory = None
        self._record_audit(
            "inventory.invalidated",
            {
                "categories": list(payload.get("categories") or []),
                "changed_count": int(payload.get("changed_count") or 0),
            },
        )
        logger.info("CapabilityCore: inventory cache invalidated via hook event")

    def _on_workspace_created(self, payload: dict) -> None:
        # New workspace may need default capabilities — record for auditing
        self._record_audit("workspace.created", {"task_id": payload.get("task_id")})
        logger.debug("CapabilityCore: workspace created %s", payload.get("task_id", "?"))

    def _installed_snapshot(self) -> dict[CapabilityCategory, list[str]]:
        repo_paths = _repo_paths()
        config = ExtensionsConfig.from_file(str(repo_paths["mcp"])) if repo_paths["mcp"].exists() else ExtensionsConfig()
        return {
            "skills": _list_dir_names(repo_paths["skills"]),
            "agents": _list_file_names(repo_paths["agents"], ".agent.md"),
            "instructions": _list_file_names(repo_paths["instructions"], ".instructions.md"),
            "hooks": _list_dir_names(repo_paths["hooks"]),
            "mcp": sorted(config.mcp_servers.keys()),
        }

    def _source_snapshot(self) -> dict[CapabilityCategory, list[str]]:
        source_paths = _source_paths()
        return {
            "skills": _list_dir_names(source_paths["skills"]),
            "agents": _list_file_names(source_paths["agents"], ".agent.md"),
            "instructions": _list_file_names(source_paths["instructions"], ".instructions.md"),
            "hooks": _list_dir_names(source_paths["hooks"]),
            "mcp": sorted(_load_source_mcp_servers(source_paths["mcp"]).keys()),
        }

    def build_inventory(self) -> dict[str, object]:
        if self._cached_inventory is not None:
            return self._cached_inventory
        source = self._source_snapshot()
        installed = self._installed_snapshot()
        matched = {category: sorted(set(source[category]).intersection(installed[category])) for category in source}
        inventory = {
            "source_root": str(_source_root()),
            "target_root": str(_repo_root()),
            "source": source,
            "installed": installed,
            "matched": matched,
        }
        self._cached_inventory = inventory
        self._last_inventory_built_at = datetime.now(UTC).isoformat()
        return inventory

    def build_runtime_state(self) -> dict[str, object]:
        inventory = self.build_inventory()
        from src.harness.hook_core import get_hook_core_service

        hook_runtime = get_hook_core_service().runtime_state()
        extensions_config = get_extensions_config()
        compat_config = getattr(extensions_config, "agent_skills_compat", None)
        compat_root = resolve_agent_skills_source_root(compat_config, allow_disabled=True) if compat_config is not None else None
        return {
            "source_root": inventory["source_root"],
            "target_root": inventory["target_root"],
            "cache_state": "warm" if self._cached_inventory is not None else "cold",
            "listeners_registered": self._listeners_registered,
            "last_inventory_built_at": self._last_inventory_built_at,
            "last_migration_at": self._last_migration_at,
            "total_source_items": sum(len(items) for items in inventory["source"].values()),
            "total_installed_items": sum(len(items) for items in inventory["installed"].values()),
            "total_matched_items": sum(len(items) for items in inventory["matched"].values()),
            "hook_runtime": {
                "total_hooks": hook_runtime.get("total_hooks", 0),
                "enabled_hooks": hook_runtime.get("enabled_hooks", 0),
                "total_webhooks": hook_runtime.get("total_webhooks", 0),
                "enabled_webhooks": hook_runtime.get("enabled_webhooks", 0),
            },
            "agent_skills_compat": {
                "enabled": bool(getattr(compat_config, "enabled", False)),
                "source_root": str(compat_root) if compat_root is not None else None,
                "trust_level": getattr(compat_config, "trust_level", "untrusted"),
                "configured_items": len(getattr(compat_config, "item_states", {}) or {}),
            },
        }

    def _extensions_config_path(self) -> Path:
        return _repo_paths()["mcp"]

    def _persist_extensions_config(self, config: ExtensionsConfig) -> ExtensionsConfig:
        config_path = self._extensions_config_path()
        write_json_atomic(config_path, config.to_serializable_dict())
        return reload_extensions_config(str(config_path))

    async def _refresh_after_config_change(
        self,
        *,
        categories: list[str],
        refresh_skills: bool = False,
    ) -> None:
        if refresh_skills:
            invalidate_skills_cache()
            await asyncio.to_thread(load_skills)
        await async_refresh_agent_tool_guide()
        self._cached_inventory = None
        from src.harness.hook_core import get_hook_core_service

        get_hook_core_service().emit_capability_refresh(
            {
                "categories": categories,
                "changed_count": 1,
            }
        )

    def _registry_item_by_id(self, capability_id: str) -> dict[str, object] | None:
        snapshot = self.build_registry_snapshot()
        return next(
            (item for item in snapshot["items"] if item["capability_id"] == capability_id),
            None,
        )

    def build_agent_skills_compat_preview(self) -> dict[str, object]:
        extensions_config = get_extensions_config()
        compat_config = extensions_config.agent_skills_compat
        source_root = resolve_agent_skills_source_root(compat_config, allow_disabled=True)
        entries = build_agent_skills_compat_entries(compat_config, allow_disabled=True)

        base_config = extensions_config.model_copy(deep=True)
        base_config.agent_skills_compat.enabled = False
        inventory = self.build_inventory()
        existing_snapshot = build_capability_registry_snapshot(
            inventory=inventory,
            extensions_config=base_config,
        ).model_dump()
        existing_index: dict[tuple[str, str], list[dict[str, object]]] = {}
        for item in existing_snapshot["items"]:
            key = (str(item["kind"]), str(item["name"]))
            existing_index.setdefault(key, []).append(item)

        preview_items: list[dict[str, object]] = []
        conflict_count = 0
        blocked_count = 0
        configurable_count = 0

        for entry in entries:
            configured_enabled = extensions_config.get_agent_skills_item_configured_enabled(
                entry.capability_id,
                entry.kind,
            )
            trusted = compat_item_trust_allowed(entry.kind, compat_config)
            toggleable = compat_item_toggleable(entry.kind)
            conflicts = [
                {
                    "capability_id": str(item["capability_id"]),
                    "kind": str(item["kind"]),
                    "name": str(item["name"]),
                    "provider": str(item.get("provider") or "octoagent"),
                    "source": str(item.get("source") or ""),
                    "reason": "same_kind_and_name",
                }
                for item in existing_index.get((entry.kind, entry.name), [])
            ]
            activation_blockers: list[str] = []
            if not compat_config.enabled:
                activation_blockers.append("compat_disabled")
            if not trusted:
                activation_blockers.append("trust_required")
            if conflicts:
                activation_blockers.append("name_conflict")

            projected_enabled = configured_enabled and not activation_blockers
            if conflicts:
                conflict_count += 1
            if activation_blockers:
                blocked_count += 1
            if toggleable:
                configurable_count += 1

            preview_items.append(
                {
                    "capability_id": entry.capability_id,
                    "kind": entry.kind,
                    "name": entry.name,
                    "display_name": entry.display_name,
                    "description": entry.description,
                    "source": entry.source,
                    "configured_enabled": configured_enabled,
                    "projected_enabled": projected_enabled,
                    "trusted": trusted,
                    "toggleable": toggleable,
                    "activation_blockers": activation_blockers,
                    "conflicts": conflicts,
                    "metadata": dict(entry.metadata),
                }
            )

        return {
            "enabled": compat_config.enabled,
            "source_root": str(source_root) if source_root is not None else None,
            "trust_level": compat_config.trust_level,
            "total_items": len(preview_items),
            "conflict_count": conflict_count,
            "blocked_count": blocked_count,
            "configurable_count": configurable_count,
            "items": preview_items,
        }

    def build_audit_state(self) -> dict[str, object]:
        return {
            "event_count": len(self._audit_events),
            "recent_events": list(self._audit_events[:8]),
            "last_migration_summary": self._last_migration_summary,
            "last_migration_at": self._last_migration_at,
        }

    def build_registry_snapshot(self) -> dict[str, object]:
        """Return a normalized runtime registry across managed capabilities."""

        inventory = self.build_inventory()
        snapshot = build_capability_registry_snapshot(
            inventory=inventory,
            extensions_config=get_extensions_config(),
        )
        payload = snapshot.model_dump()
        compat_preview = self.build_agent_skills_compat_preview()
        compat_index = {item["capability_id"]: item for item in compat_preview.get("items", [])}
        for item in payload["items"]:
            preview_item = compat_index.get(item["capability_id"])
            if preview_item is None:
                continue
            item["activation_blockers"] = list(preview_item["activation_blockers"])
            item.setdefault("metadata", {})
            item["metadata"]["conflict_count"] = len(preview_item["conflicts"])
            item["metadata"]["projected_enabled"] = preview_item["projected_enabled"]
            item["metadata"]["trusted"] = preview_item["trusted"]
        return payload

    @staticmethod
    def _binding_targets_for_kind(kind: str) -> list[str]:
        targets_by_kind = {
            "skill": ["agent_runtime", "task_workspace"],
            "plugin": ["task_workspace", "workflow_review", "operator_surface"],
            "mcp_server": ["agent_runtime", "tool_registry"],
            "hook": ["event_dispatch", "operator_surface"],
            "channel": ["external_ingress", "agent_runtime", "operator_surface"],
            "command": ["tool_registry"],
            "agent_persona": ["agent_runtime"],
            "reference": ["knowledge_context"],
        }
        return list(targets_by_kind.get(kind, ["capability_registry"]))

    @staticmethod
    def _dispatch_contract_for_kind(kind: str, item: dict[str, object]) -> dict[str, object]:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        provides = list(item.get("provides") or [])
        if kind == "hook":
            return {
                "mode": "event",
                "events": provides,
                "entrypoint": item.get("source"),
            }
        if kind == "channel":
            return {
                "mode": "message_ingress",
                "transport": metadata.get("transport"),
                "ingest_path": metadata.get("ingest_path"),
                "handler_path": metadata.get("handler_path"),
            }
        if kind == "mcp_server":
            return {"mode": "mcp_tooling", "server": item.get("name"), "tools": provides}
        if kind == "plugin":
            return {"mode": "plugin_command", "commands": provides}
        if kind == "skill":
            return {"mode": "agent_instruction", "skills": provides}
        return {"mode": "registry_reference", "provides": provides}

    def build_binding_contract(self) -> dict[str, object]:
        """Return the runtime binding contract used by agents and operator surfaces."""

        snapshot = self.build_registry_snapshot()
        items: list[dict[str, object]] = []
        by_kind: dict[str, int] = {}
        enabled_count = 0
        blocked_count = 0

        from .policy import get_capability_policy_service

        policy_service = get_capability_policy_service()

        for raw_item in snapshot.get("items", []):
            if not isinstance(raw_item, dict):
                continue
            kind = str(raw_item.get("kind") or "unknown")
            capability_id = str(raw_item.get("capability_id") or "")
            policy_payload = policy_service.policy_payload_for(capability_id)
            blockers = list(raw_item.get("activation_blockers") or [])
            if policy_payload.get("decision") == "deny":
                blockers.append("operator_policy_denied")
            enabled = bool(raw_item.get("enabled"))
            by_kind[kind] = by_kind.get(kind, 0) + 1
            if enabled:
                enabled_count += 1
            if blockers:
                blocked_count += 1

            items.append(
                {
                    "capability_id": capability_id,
                    "kind": kind,
                    "name": str(raw_item.get("name") or ""),
                    "display_name": str(raw_item.get("display_name") or raw_item.get("name") or ""),
                    "provider": str(raw_item.get("provider") or "octoagent"),
                    "source": str(raw_item.get("source") or ""),
                    "enabled": enabled,
                    "installed": bool(raw_item.get("installed")),
                    "configurable": bool(raw_item.get("configurable")),
                    "bindable_targets": self._binding_targets_for_kind(kind),
                    "dispatch_contract": self._dispatch_contract_for_kind(kind, raw_item),
                    "audit_state": {
                        "activation_blockers": blockers,
                        "configured_enabled": raw_item.get("configured_enabled"),
                        "version": raw_item.get("version"),
                    },
                    "operator_policy": policy_payload,
                    "metadata": dict(raw_item.get("metadata") or {}),
                }
            )

        return {
            "generated_at": snapshot.get("generated_at"),
            "summary": {
                "total_items": len(items),
                "enabled_items": enabled_count,
                "blocked_items": blocked_count,
                "by_kind": by_kind,
            },
            "items": items,
        }

    async def update_agent_skills_compat_settings(
        self,
        *,
        enabled: bool | None = None,
        trust_level: str | None = None,
    ) -> dict[str, object]:
        config = get_extensions_config()
        compat_config = config.agent_skills_compat
        changed_fields: list[str] = []

        if enabled is not None and compat_config.enabled != enabled:
            compat_config.enabled = enabled
            changed_fields.append("enabled")
        if trust_level is not None and compat_config.trust_level != trust_level:
            compat_config.trust_level = trust_level
            changed_fields.append("trust_level")

        self._persist_extensions_config(config)
        await self._refresh_after_config_change(categories=["compat"])
        self._record_audit(
            "compat.settings.updated",
            {
                "enabled": compat_config.enabled,
                "trust_level": compat_config.trust_level,
                "changed_fields": changed_fields,
            },
        )
        return self.build_agent_skills_compat_preview()

    async def update_capability_enabled(
        self,
        capability_id: str,
        enabled: bool,
    ) -> dict[str, object]:
        current_item = self._registry_item_by_id(capability_id)
        if current_item is None:
            raise ValueError(f"Capability '{capability_id}' not found")
        if not bool(current_item.get("configurable")):
            raise ValueError(f"Capability '{capability_id}' does not support enable/disable")

        plane, name, extra = _parse_capability_id(capability_id)
        refresh_skills = False
        categories: list[str] = []

        if plane == "hook":
            from src.harness.hook_core import get_hook_core_service

            updated = get_hook_core_service().set_hook_enabled(name, enabled)
            if updated is None:
                raise ValueError(f"Hook '{name}' not found")
            self._cached_inventory = None
        else:
            config = get_extensions_config()
            if plane == "skill":
                config.skills[name] = SkillStateConfig(enabled=enabled)
                refresh_skills = True
                categories = ["skills"]
            elif plane == "mcp_server":
                server_config = config.mcp_servers.get(name)
                if server_config is None:
                    raise ValueError(f"MCP server '{name}' not found")
                server_config.enabled = enabled
                categories = ["mcp"]
            elif plane == "agent_skills":
                config.agent_skills_compat.item_states[capability_id] = CompatCapabilityStateConfig(enabled=enabled)
                categories = ["compat", str(name)]
            else:
                raise ValueError(f"Capability '{capability_id}' does not support enable/disable")

            self._persist_extensions_config(config)
            await self._refresh_after_config_change(categories=categories, refresh_skills=refresh_skills)

        updated_item = self._registry_item_by_id(capability_id)
        if updated_item is None:
            raise ValueError(f"Capability '{capability_id}' disappeared after update")

        self._record_audit(
            "capability.state.updated",
            {
                "capability_id": capability_id,
                "kind": updated_item.get("kind"),
                "provider": updated_item.get("provider"),
                "configured_enabled": updated_item.get("configured_enabled"),
                "effective_enabled": updated_item.get("enabled"),
                "activation_blockers": list(updated_item.get("activation_blockers") or []),
            },
        )
        return updated_item

    def _build_migration_summary(
        self,
        previous_inventory: dict[str, object],
        current_inventory: dict[str, object],
        results: list[dict[str, str]],
    ) -> dict[str, object]:
        previous_source = previous_inventory["source"]
        previous_installed = previous_inventory["installed"]
        previous_matched = previous_inventory["matched"]
        current_source = current_inventory["source"]
        current_installed = current_inventory["installed"]
        current_matched = current_inventory["matched"]
        categories: dict[str, dict[str, object]] = {}
        result_index: dict[str, list[dict[str, str]]] = {category: [] for category in previous_source}
        for result in results:
            result_index[result["category"]].append(result)

        for category in previous_source:
            source_total = len(current_source[category])
            installed_before = len(previous_installed[category])
            installed_after = len(current_installed[category])
            matched_before = len(previous_matched[category])
            matched_after = len(current_matched[category])
            category_results = result_index.get(category, [])
            categories[category] = {
                "category": category,
                "source_total": source_total,
                "installed_before": installed_before,
                "installed_after": installed_after,
                "matched_before": matched_before,
                "matched_after": matched_after,
                "pending_before": max(source_total - matched_before, 0),
                "pending_after": max(source_total - matched_after, 0),
                "installed_delta": installed_after - installed_before,
                "matched_delta": matched_after - matched_before,
                "installed_count": sum(1 for item in category_results if item["status"] == "installed"),
                "updated_count": sum(1 for item in category_results if item["status"] == "updated"),
                "skipped_count": sum(1 for item in category_results if item["status"] == "skipped"),
                "error_count": sum(1 for item in category_results if item["status"] == "error"),
            }

        return {
            "total_results": len(results),
            "changed_count": sum(1 for item in results if item["status"] in {"installed", "updated"}),
            "success_count": sum(1 for item in results if item["status"] != "error"),
            "error_count": sum(1 for item in results if item["status"] == "error"),
            "pending_after": sum(item["pending_after"] for item in categories.values()),
            "matched_delta": sum(item["matched_delta"] for item in categories.values()),
            "categories": categories,
        }

    async def migrate_capabilities(
        self,
        categories: list[CapabilityCategory] | None = None,
    ) -> dict[str, object]:
        selected = categories or ["skills", "agents", "instructions", "hooks", "mcp"]
        source_paths = _source_paths()
        repo_paths = _repo_paths()
        results: list[dict[str, str]] = []

        previous_inventory = self.build_inventory()
        config = get_extensions_config()

        for category in selected:
            if category == "skills":
                for skill_name in _list_dir_names(source_paths[category]):
                    status, message = _copy_directory(source_paths[category] / skill_name, repo_paths[category] / skill_name)
                    config.skills.setdefault(skill_name, SkillStateConfig(enabled=True))
                    results.append({"category": category, "name": skill_name, "status": status, "message": message})
            elif category == "agents":
                for file_name in _list_file_names(source_paths[category], ".agent.md"):
                    status, message = _copy_file(source_paths[category] / file_name, repo_paths[category] / file_name)
                    results.append({"category": category, "name": file_name, "status": status, "message": message})
            elif category == "instructions":
                for file_name in _list_file_names(source_paths[category], ".instructions.md"):
                    status, message = _copy_file(source_paths[category] / file_name, repo_paths[category] / file_name)
                    results.append({"category": category, "name": file_name, "status": status, "message": message})
            elif category == "hooks":
                for hook_name in _list_dir_names(source_paths[category]):
                    status, message = _copy_directory(source_paths[category] / hook_name, repo_paths[category] / hook_name)
                    config.hooks.setdefault(hook_name, HookStateConfig(enabled=True))
                    results.append({"category": category, "name": hook_name, "status": status, "message": message})
            elif category == "mcp":
                servers = _load_source_mcp_servers(source_paths[category])
                if not servers:
                    results.append({"category": category, "name": "mcp", "status": "error", "message": "source mcp.json not found or empty"})
                    continue
                for server_name, raw_server in sorted(servers.items()):
                    if not isinstance(raw_server, dict):
                        results.append({"category": category, "name": server_name, "status": "error", "message": "invalid source server payload"})
                        continue
                    status = "updated" if server_name in config.mcp_servers else "installed"
                    payload = dict(raw_server)
                    payload.setdefault("enabled", True)
                    config.mcp_servers[server_name] = McpServerConfig.model_validate(payload)
                    results.append({"category": category, "name": server_name, "status": status, "message": "merged into extensions_config.json"})

        write_json_atomic(repo_paths["mcp"], config.to_serializable_dict())

        reload_extensions_config(str(repo_paths["mcp"]))
        invalidate_skills_cache()
        await asyncio.to_thread(load_skills)
        self._cached_inventory = None
        current_inventory = self.build_inventory()
        self._last_migration_at = datetime.now(UTC).isoformat()
        summary = self._build_migration_summary(previous_inventory, current_inventory, results)
        self._last_migration_summary = summary
        self._record_audit(
            "migration.completed",
            {
                "categories": list(selected),
                "changed_count": int(summary["changed_count"]),
                "error_count": int(summary["error_count"]),
                "pending_after": int(summary["pending_after"]),
            },
        )
        from src.harness.hook_core import get_hook_core_service

        get_hook_core_service().emit_capability_refresh(
            {
                "categories": selected,
                "result_count": len(results),
                "changed_count": sum(1 for item in results if item["status"] in {"installed", "updated"}),
            }
        )
        return {
            "success": True,
            "results": results,
            "previous_inventory": previous_inventory,
            "inventory": current_inventory,
            "summary": summary,
        }


_service = CapabilityCoreService()


def get_capability_core_service() -> CapabilityCoreService:
    _service.register_hook_listeners()
    return _service


__all__ = ["CapabilityCategory", "CapabilityCoreService", "get_capability_core_service"]
