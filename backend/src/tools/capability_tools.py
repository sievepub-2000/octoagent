from __future__ import annotations

import json
from typing import Literal

from langchain_core.tools import tool

CapabilityKind = Literal[
    "skill",
    "plugin",
    "mcp_server",
    "hook",
    "channel",
    "command",
    "agent_persona",
    "reference",
]
CAPABILITY_KINDS = {
    "skill",
    "plugin",
    "mcp_server",
    "hook",
    "channel",
    "command",
    "agent_persona",
    "reference",
}


def _normalize_capability_kind(kind: str | None) -> str | None:
    """Normalize loose model-supplied kind values.

    Some models emit optional tool arguments as JSON null, an empty string, or
    the literal text "null". Keep the public tool schema permissive and do the
    validation here so discovery never fails before the agent can recover.
    """

    if kind is None:
        return None
    normalized = str(kind).strip().lower()
    if normalized in {"", "all", "any", "none", "null"}:
        return None
    if normalized not in CAPABILITY_KINDS:
        raise ValueError(f"Unsupported capability kind {kind!r}. Expected one of: {', '.join(sorted(CAPABILITY_KINDS))}.")
    return normalized


@tool("list_capabilities", parse_docstring=True)
def list_capabilities_tool(
    kind: str | None = None,
    enabled_only: bool = True,
    max_items: int = 80,
) -> str:
    """List installed runtime capabilities such as skills, plugins, MCP servers, and hooks.

    Use this before selecting a managed skill/plugin/MCP/hook so the agent can
    choose installed capabilities instead of guessing from stale prompt text.

    Args:
        kind: Optional capability kind filter.
        enabled_only: Whether to include only enabled capabilities.
        max_items: Maximum number of capability items to return.
    """

    from src.tools.capability.registry import build_capability_registry_snapshot

    normalized_kind = _normalize_capability_kind(kind)
    snapshot = build_capability_registry_snapshot()
    items = snapshot.items
    if normalized_kind:
        items = [item for item in items if item.kind == normalized_kind]
    if enabled_only:
        items = [item for item in items if item.enabled]

    limited_items = items[: max(1, min(max_items, 200))]
    payload = {
        "generated_at": snapshot.generated_at,
        "summary": snapshot.summary.model_dump(),
        "returned": len(limited_items),
        "truncated": len(items) > len(limited_items),
        "items": [
            {
                "capability_id": item.capability_id,
                "kind": item.kind,
                "name": item.name,
                "display_name": item.display_name,
                "description": item.description,
                "installed": item.installed,
                "enabled": item.enabled,
                "source": item.source,
                "provides": item.provides,
                "requires": item.requires,
                "activation_blockers": item.activation_blockers,
                "metadata": item.metadata,
            }
            for item in limited_items
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool("load_skill", parse_docstring=True)
def load_skill_tool(skill_name: str, category: str | None = None) -> str:
    """Load an enabled skill's SKILL.md content by name.

    Use this when a user request matches an installed skill and you need the
    skill workflow before acting.

    Args:
        skill_name: Skill name to load.
        category: Optional category filter, usually public or custom.
    """

    from src.storage.skills import load_skills

    normalized_name = skill_name.strip()
    normalized_category = category.strip() if category else None
    for skill in load_skills(enabled_only=True):
        if skill.name != normalized_name:
            continue
        if normalized_category and skill.category != normalized_category:
            continue
        content = skill.skill_file.read_text(encoding="utf-8")
        return f"# Skill: {skill.name}\nCategory: {skill.category}\nDescription: {skill.description}\nPath: {skill.skill_file}\n\n{content}"
    return f"Error: enabled skill not found: {skill_name}"


@tool("get_plugin_command", parse_docstring=True)
def get_plugin_command_tool(command_id: str) -> str:
    """Get the manifest details for an installed plugin command.

    Plugins in this system are workflow/advisory capabilities. Use this tool to
    resolve a command ID such as ce:plan or wrb:review before following it.

    Args:
        command_id: Plugin command ID to resolve.
    """

    from src.tools.plugins import get_plugin_service

    service = get_plugin_service()
    plugins = {plugin.plugin_id: plugin for plugin in service.list_plugins().plugins}
    for manifest in service.list_manifests().manifests:
        plugin = plugins.get(manifest.plugin_id)
        if plugin is not None and not plugin.enabled:
            continue
        for command in manifest.commands:
            if command.command_id != command_id:
                continue
            payload = {
                "plugin_id": manifest.plugin_id,
                "display_name": manifest.display_name,
                "description": manifest.description,
                "command": command.model_dump(),
                "review_flow": manifest.review_flow,
                "permissions": plugin.permissions if plugin else [],
                "runtime_requirements": plugin.runtime_requirements if plugin else [],
                "usage": "Follow the command summary and plugin review flow as workflow guidance; this command is not a shell command.",
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)
    return f"Error: enabled plugin command not found: {command_id}"
