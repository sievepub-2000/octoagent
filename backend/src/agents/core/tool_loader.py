"""Intent-based lazy loading of L2 tools.

When the narrow-waist core (5 always-loaded tools) is insufficient for a
task, this module detects which additional tool categories are needed and
loads them on demand.  Tools are loaded once per session and cached so
subsequent calls return the same instances without re-importing.

Intent detection uses keyword matching against the agent's current prompt /
goal string.  Each L2 category has a list of trigger keywords; if any match,
that category is loaded into the tool set.

Usage::

    from src.agents.core.tool_loader import load_tools_for_intent

    tools = load_tools_for_intent(
        goal="Deploy the Docker container on production",
        session_id="sess-abc123",
    )
    # Returns list[BaseTool] with system_ops, desktop_driver, etc. as needed
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.tools import BaseTool

from src.tools.catalog import LAZY_LOAD_REGISTRY, L3_MCP_PLUGIN_TOOLS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent-to-category trigger keywords
# ---------------------------------------------------------------------------

_INTENT_TRIGGERS: dict[str, list[str]] = {
    "system_ops": [
        "docker", "container", "shell", "bash", "ssh", "scp", "git",
        "systemctl", "service", "process", "cpu", "memory", "disk",
        "network", "firewall", "iptables", "kernel", "mount", "filesystem",
        "deploy", "infrastructure", "server", "host", "machine",
        "scan", "security", "vulnerability", "bandit", "trivy",
        "pytest", "test", "lint", "typecheck", "npm", "pip", "install",
    ],
    "system_extra": [
        "database", "db_", "sql", "migration", "schema", "query",
        "git_commit", "git_push", "git_branch", "git_diff",
        "python_package", "dependency", "audit",
    ],
    "desktop_driver": [
        "desktop", "screen", "screenshot", "click", "type text", "hotkey",
        "scroll", "mouse", "keyboard", "gui", "window", "application",
        "pyautogui", "xdotool",
    ],
    "ecosystem_workflow": [
        "project catalog", "workflow run", "integrated project",
        "selfhosted", "awesome", "novel", "writing", "chapter",
        "story", "book", "publication", "publishing", "wp-cli",
        "wordpress", "browser publish", "auditor",
    ],
    "publishing_workflow": [
        "publish", "publication", "browser", "wp_cli", "auditor",
        "deploy site", "push to production",
    ],
    "workflow_runtime": [
        "checkpoint", "subagent", "spawn", "workflow start", "workflow status",
        "resume", "pause", "handoff",
    ],
    "document_convert": [
        "convert", "pdf", "docx", "markdown", "html to", "format export",
        "document conversion", "file format",
    ],
    "image_processing": [
        "image", "photo", "picture", "canvas", "flipbook", "render",
        "screenshot", "thumbnail", "resize", "crop",
    ],
    "codex_cli": [
        "codex", "cli", "command line interface",
    ],
}

# L3 MCP/plugin triggers (loaded only when explicitly enabled)
_L3_TRIGGERS: dict[str, list[str]] = {
    "openharness_compat": ["openharness", "legacy compat"],
    "bytebot_compat": ["bytebot", "bytebot compat"],
    "software_interface": ["software interface", "authorize software"],
}

# ---------------------------------------------------------------------------
# Session-level cache
# ---------------------------------------------------------------------------

_loaded_sessions: dict[str, set[str]] = {}


def _detect_categories(goal_or_prompt: str) -> list[str]:
    """Return the list of L2 category keys whose triggers match the input."""
    text = (goal_or_prompt or "").lower()
    matched: list[str] = []
    for category, keywords in _INTENT_TRIGGERS.items():
        for kw in keywords:
            if kw in text:
                matched.append(category)
                break
    return matched


def _detect_l3_categories(goal_or_prompt: str) -> list[str]:
    """Return the list of L3 category keys whose triggers match the input."""
    text = (goal_or_prompt or "").lower()
    matched: list[str] = []
    for category, keywords in _L3_TRIGGERS.items():
        for kw in keywords:
            if kw in text:
                matched.append(category)
                break
    return matched


def load_tools_for_intent(
    goal_or_prompt: str,
    session_id: str | None = None,
    *,
    enable_l3: bool = False,
) -> list[BaseTool]:
    """Detect intent from the goal/prompt and load matching L2 tools.

    Args:
        goal_or_prompt: The agent's task description or current prompt text.
        session_id: Optional session identifier for caching loaded tools.
        enable_l3: If True, also attempt to load L3 MCP/plugin tools.

    Returns:
        List of BaseTool instances that should be added to the agent's tool set.
    """
    categories = _detect_categories(goal_or_prompt)
    if not categories:
        logger.debug("No L2 tool categories matched for intent detection")
        return []

    # Check session cache — avoid reloading tools already loaded this session.
    if session_id is not None:
        previously_loaded = _loaded_sessions.get(session_id, set())
        new_categories = [c for c in categories if c not in previously_loaded]
    else:
        new_categories = categories

    if not new_categories:
        logger.debug("All matched tool categories already loaded this session")
        return []

    tools: list[BaseTool] = []
    for category in new_categories:
        category_tools = LAZY_LOAD_REGISTRY.get(category, [])
        if category_tools:
            tool_names = [t.name for t in category_tools]
            tools.extend(category_tools)
            logger.info(
                "Lazy-loaded %d L2 tools for category '%s': %s",
                len(category_tools),
                category,
                ", ".join(tool_names[:5]) + ("..." if len(tool_names) > 5 else ""),
            )

    # Cache the loaded categories for this session.
    if session_id is not None:
        existing = _loaded_sessions.get(session_id, set())
        existing.update(new_categories)
        _loaded_sessions[session_id] = existing

    # L3 tools (only when explicitly enabled).
    if enable_l3:
        l3_cats = _detect_l3_categories(goal_or_prompt)
        for category in l3_cats:
            category_tools = L3_MCP_PLUGIN_TOOLS.get(category, [])
            if category_tools:
                tool_names = [t.name for t in category_tools]
                tools.extend(category_tools)
                logger.info(
                    "Loaded %d L3 tools for category '%s': %s",
                    len(category_tools),
                    category,
                    ", ".join(tool_names[:5]) + ("..." if len(tool_names) > 5 else ""),
                )

    return tools


def clear_session_cache(session_id: str | None = None) -> None:
    """Clear the loaded-tools cache for a session (or all sessions)."""
    if session_id is not None:
        _loaded_sessions.pop(session_id, None)
    else:
        _loaded_sessions.clear()


def get_loaded_categories(session_id: str | None = None) -> set[str]:
    """Return the set of categories loaded for a session."""
    if session_id is not None:
        return set(_loaded_sessions.get(session_id, set()))
    # Return union of all sessions.
    result: set[str] = set()
    for loaded in _loaded_sessions.values():
        result.update(loaded)
    return result


__all__ = [
    "load_tools_for_intent",
    "clear_session_cache",
    "get_loaded_categories",
    "_INTENT_TRIGGERS",
    "_L3_TRIGGERS",
]
