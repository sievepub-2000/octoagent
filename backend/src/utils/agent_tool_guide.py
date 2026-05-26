from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tools.capability.registry import UnifiedCapabilityItem


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _guide_path() -> Path:
    return _repo_root() / ".github" / "copilot-instructions.md"


def _kind_title(kind: str) -> str:
    return {
        "skill": "Skills",
        "plugin": "Plugins",
        "mcp_server": "MCP Servers",
        "hook": "Hooks",
        "command": "Commands",
        "agent_persona": "Agent Personas",
        "reference": "References",
    }.get(kind, kind.replace("_", " ").title())


def _format_state(item: UnifiedCapabilityItem) -> str:
    installed = "installed" if item.installed else "not-installed"
    enabled = "enabled" if item.enabled else "disabled"
    return f"{installed}, {enabled}"


def _format_metadata_lines(item: UnifiedCapabilityItem) -> list[str]:
    metadata = item.metadata or {}
    lines: list[str] = []
    if item.kind == "skill":
        if metadata.get("category"):
            lines.append(f"Category: {metadata['category']}")
        if metadata.get("relative_path"):
            lines.append(f"Skill file: {metadata['relative_path']}")
    elif item.kind == "plugin":
        if metadata.get("category"):
            lines.append(f"Category: {metadata['category']}")
        if metadata.get("execution_mode"):
            lines.append(f"Execution mode: {metadata['execution_mode']}")
        review_flow = metadata.get("review_flow") or []
        if review_flow:
            lines.append(f"Review flow: {', '.join(str(step) for step in review_flow)}")
    elif item.kind == "mcp_server":
        if metadata.get("transport"):
            lines.append(f"Transport: {metadata['transport']}")
        if metadata.get("command"):
            lines.append(f"Command: {metadata['command']}")
        if metadata.get("url"):
            lines.append(f"URL: {metadata['url']}")
        if metadata.get("oauth_enabled"):
            lines.append("OAuth: enabled")
    elif item.kind == "hook":
        if metadata.get("runtime_binding_count"):
            lines.append(f"Runtime bindings: {metadata['runtime_binding_count']}")
        if metadata.get("webhook_registered"):
            lines.append("Webhook registration: present")
        if metadata.get("installed_in_repo"):
            lines.append("Repository package: installed")
    blockers = item.activation_blockers or []
    if blockers:
        lines.append(f"Activation blockers: {', '.join(blockers)}")
    return lines


def _format_usage_lines(item: UnifiedCapabilityItem) -> list[str]:
    provides = ", ".join(item.provides) if item.provides else "none"
    requires = ", ".join(item.requires) if item.requires else "none"
    lines = [f"Provides: {provides}", f"Requires: {requires}"]
    if item.kind == "skill":
        lines.extend(
            [
                "When to use: the user task clearly matches this domain or workflow.",
                "How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.",
            ]
        )
    elif item.kind == "plugin":
        lines.extend(
            [
                "When to use: the requested capability already exists as an installed plugin or command set.",
                "How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.",
            ]
        )
    elif item.kind == "mcp_server":
        lines.extend(
            [
                "When to use: external systems, hosted tools, or remote resources are required.",
                "How to use: verify server is enabled, authenticate if required, then call the server's tools/resources instead of ad-hoc HTTP requests.",
            ]
        )
    elif item.kind == "hook":
        lines.extend(
            [
                "When to use: event-driven automation, webhooks, or runtime listener orchestration is needed.",
                "How to use: manage via hook runtime APIs and keep hook state synchronized with repository/runtime configuration.",
            ]
        )
    return lines


def _format_capability_item(item: UnifiedCapabilityItem) -> list[str]:
    lines = [f"- {item.display_name} ({item.capability_id})"]
    lines.append(f"  State: {_format_state(item)}")
    if item.description:
        lines.append(f"  Description: {item.description}")
    lines.append(f"  Source: {item.source or 'builtin'}")
    for meta_line in _format_metadata_lines(item):
        lines.append(f"  {meta_line}")
    for usage_line in _format_usage_lines(item):
        lines.append(f"  {usage_line}")
    return lines


def generate_agent_tool_guide() -> Path:
    from src.tools.capability.registry import build_capability_registry_snapshot

    guide_path = _guide_path()
    guide_path.parent.mkdir(parents=True, exist_ok=True)

    snapshot = build_capability_registry_snapshot()
    grouped_items: dict[str, list[UnifiedCapabilityItem]] = defaultdict(list)
    for item in snapshot.items:
        grouped_items[item.kind].append(item)

    lines = [
        "# OctoAgent System Tool Guide",
        "",
        "This file is auto-generated from the current OctoAgent runtime state.",
        "Whenever skills, plugins, MCP servers, or hooks are added, removed, enabled, disabled, or reconfigured, this file must be regenerated immediately.",
        "",
        "## System Rules",
        "",
        "- Before using a specialized capability, prefer an installed skill/plugin/MCP server over ad-hoc behavior.",
        "- If a requested capability is already installed, use it instead of recreating it.",
        "- If a capability depends on runtime state, check installed/enabled state and activation blockers first.",
        "- Before using a managed capability category, read the relevant section in this file and follow the listed interface contract.",
        "- After any change to skills/plugins/MCP/hooks, regenerate this guide.",
        "",
        "## Registry Summary",
        "",
        f"- Generated at: {snapshot.generated_at}",
        f"- Total capabilities: {snapshot.summary.total_items}",
        f"- Enabled capabilities: {snapshot.summary.enabled_items}",
        f"- Installed capabilities: {snapshot.summary.installed_items}",
    ]

    for kind, count in sorted(snapshot.summary.by_kind.items()):
        enabled_count = snapshot.summary.enabled_by_kind.get(kind, 0)
        lines.append(f"- {_kind_title(kind)}: {count} total, {enabled_count} enabled")

    lines.extend(
        [
            "",
            "## Interface Contract",
            "",
            "- Skills: load the skill file first, then execute its prescribed workflow.",
            "- Plugins: prefer provided command IDs over recreating the same action manually.",
            "- MCP servers: verify server availability and authentication before using remote tools/resources.",
            "- Hooks: treat them as event-driven integration points; update runtime and repository state together.",
            "",
        ]
    )

    for kind in sorted(grouped_items.keys()):
        items = grouped_items[kind]
        lines.extend(
            [
                f"## {_kind_title(kind)} ({len(items)})",
                "",
            ]
        )
        for item in items:
            lines.extend(_format_capability_item(item))
            lines.append("")

    lines.extend(
        [
            "## Maintenance",
            "",
            "- Regeneration source: `backend/src/utils/agent_tool_guide.py`.",
            "- Snapshot source: `backend/src/capability_core/registry.py`.",
            "- Regenerate after install/uninstall/enable/disable/configuration changes of any managed capability.",
        ]
    )

    guide_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return guide_path


async def async_refresh_agent_tool_guide() -> Path:
    return await asyncio.to_thread(generate_agent_tool_guide)
