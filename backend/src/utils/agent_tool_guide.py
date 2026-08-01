from __future__ import annotations

import asyncio
import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_agent_tool_guide_path() -> Path:
    if configured := os.getenv("OCTOAGENT_TOOL_GUIDE_PATH", "").strip():
        return Path(configured).expanduser().resolve()
    return _repo_root() / ".github" / "copilot-instructions.md"


def generate_agent_tool_guide() -> Path:
    """Generate the model-facing guide from the one public Harness registry."""
    from src.tools.registry.service import ToolRegistryService

    guide_path = get_agent_tool_guide_path()
    guide_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = ToolRegistryService().build_registry()
    summary = snapshot.summary
    lines = [
        "# OctoAgent Harness Tool Guide",
        "",
        "This file is generated from the same live registry exposed by `/api/harness` and `list_capabilities`.",
        "",
        "## Operating contract",
        "",
        "- Prefer an enabled Harness capability over an ad-hoc external search or installation.",
        "- Permission mode is enforced by the server at tool dispatch; unavailable tools are not callable.",
        "- Refresh Harness after adding, removing, enabling, disabling, or updating a tool source.",
        "- Install and remove operator-managed tools only through their lifecycle tools.",
        "",
        "## Summary",
        "",
        f"- Built-in tools: {summary.builtin_tools_total}",
        f"- MCP servers: {summary.mcp_total} total, {summary.mcp_enabled} enabled",
        f"- Skills: {summary.skills_total} total, {summary.skills_enabled} enabled",
        f"- Plugins: {summary.plugins_total} total, {summary.plugins_enabled} enabled",
        f"- Channels: {summary.channels_total} total, {summary.channels_enabled} enabled",
        f"- Managed tools: {summary.managed_tools_total} total, {summary.managed_tools_callable} callable",
        "",
        "## Built-in tools",
        "",
    ]
    for item in snapshot.builtin_tools:
        lines.append(f"- `{item.name}` [{item.permission_scope}/{item.category}]: {item.description}")

    lines.extend(["", "## MCP servers", ""])
    for item in snapshot.mcp:
        state = "enabled" if item.enabled else "disabled"
        lines.append(f"- `{item.name}` [{state}, {item.status}, {item.permission_scope}]: {item.description}")
        if item.tools:
            lines.append(f"  Tools: {', '.join(item.tools)}")

    lines.extend(["", "## Skills", ""])
    for item in snapshot.skills:
        state = "enabled" if item.enabled else "disabled"
        lines.append(f"- `{item.name}` [{state}, {item.category}]: {item.description}")

    lines.extend(["", "## Plugins", ""])
    for item in snapshot.plugins:
        state = "enabled" if item.enabled else "disabled"
        lines.append(f"- `{item.plugin_id}` [{state}, {item.category}]: {item.display_name}")

    lines.extend(["", "## Channels", ""])
    for item in snapshot.channels:
        state = "enabled" if item.enabled else "disabled"
        lines.append(f"- `{item.name}` [{state}]: {item.description}")

    lines.extend(["", "## Managed tools", ""])
    for item in snapshot.managed_tools:
        state = "callable" if item.callable else "not-callable"
        lines.append(f"- `{item.name}` [{state}]: {item.description}")
        lines.append(f"  Source: {item.source_type} {item.source}; invocation: {item.invocation or item.entrypoint}")

    guide_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return guide_path


async def async_refresh_agent_tool_guide() -> Path:
    return await asyncio.to_thread(generate_agent_tool_guide)
