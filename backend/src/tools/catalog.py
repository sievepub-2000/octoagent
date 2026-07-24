"""Tool catalog — narrow-waist design.

Seven core tools are loaded into every tool-capable system prompt by default:

    1. task_tool          - Task management / subagent delegation
    2. ask_clarification  - Ask the user for clarification
    3. present_file       - Present file contents to the user
    4. setup_agent        - Agent configuration / role setup
    5. read_webpage       - Web content reading
    6. list_capabilities  - Authoritative Harness discovery
    7. inspect_octoagent_runtime - Sanitized deployment self-check

All other tools are registered in ``LAZY_LOAD_REGISTRY`` and loaded on
demand via :func:`tool_loader.load_tools_for_intent` when the agent's
intent indicates they are needed.  MCP/plugin tools (L3) are exposed only
when explicitly enabled through configuration or the auto-discovery
mechanism.

This file preserves all original imports so that existing code paths
(e.g. gateway routers, subagent catalogs) can still import tool constants
directly from ``src.tools.builtins``.  The default runtime profile is
simply narrower.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable

from langchain.tools import BaseTool

from src.harness.dynamic_import import resolve_variable
from src.runtime.config import get_app_config
from src.tools.builtins import (
    BYTEBOT_COMPAT_TOOLS,
    DESKTOP_DRIVER_TOOLS,
    ECOSYSTEM_WORKFLOW_TOOLS,
    OPENHARNESS_COMPAT_TOOLS,
    PUBLISHING_WORKFLOW_TOOLS,
    SOFTWARE_INTERFACE_TOOLS,
    SYSTEM_EXTRA_TOOLS,
    SYSTEM_OPS_TOOLS,
    WORKFLOW_RUNTIME_TOOLS,
    ask_clarification_tool,
    codex_cli_tool,
    convert_document_tool,
    inspect_octoagent_runtime_tool,
    list_capabilities_tool,
    present_file_tool,
    process_image_tool,
    read_webpage_tool,
    setup_agent,
    task_tool,
    view_image_tool,
)
from src.tools.permissions import ToolPermissionScope, set_tool_permission_metadata

logger = logging.getLogger(__name__)

_REMOVED_OPTIONAL_TOOL_MODULE_PREFIXES = ("src.community.firecrawl",)


def _is_removed_optional_tool(use_path: str) -> bool:
    return any(use_path.startswith(prefix) for prefix in _REMOVED_OPTIONAL_TOOL_MODULE_PREFIXES)


def _configured_tool_names(tools: Iterable[BaseTool]) -> set[str]:
    return {tool.name for tool in tools}


# ---------------------------------------------------------------------------
# Narrow-waist core: action primitives plus two authoritative discovery tools
# ---------------------------------------------------------------------------

BUILTIN_TOOLS_CORE: list[BaseTool] = [
    task_tool,
    ask_clarification_tool,
    present_file_tool,
    setup_agent,
    read_webpage_tool,
    list_capabilities_tool,
    inspect_octoagent_runtime_tool,
]


def _openharness_compat_enabled() -> bool:
    """Sprint-1 P0 optimization: OPENHARNESS_COMPAT_TOOLS adds ~1542 LOC of
    tool descriptions to every system prompt. Default to OFF; opt in with
    OCTOAGENT_OPENHARNESS_ENABLED=1 if a workflow requires the legacy shim."""
    value = os.environ.get("OCTOAGENT_OPENHARNESS_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _bytebot_compat_enabled() -> bool:
    """Return True when BYTEBOT_COMPAT_ENABLED env flag is truthy.

    Default is disabled to keep the default sandbox profile unchanged; the
    adapter is observation-only (returns ``not_implemented`` JSON payloads) so
    enabling it is safe, but we still opt-in explicitly per the
    self-optimization policy (observe/suggest/shadow only).
    """
    value = os.environ.get("BYTEBOT_COMPAT_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Lazy-load registry (L2 tools — loaded on intent detection)
# ---------------------------------------------------------------------------

LAZY_LOAD_REGISTRY: dict[str, list[BaseTool]] = {
    # L2: system operations (shell, docker, git, security scans, etc.)
    "system_ops": SYSTEM_OPS_TOOLS,
    # L2: system extras (lint, typecheck, playwright, db, etc.)
    "system_extra": SYSTEM_EXTRA_TOOLS,
    # L2: desktop driver tools
    "desktop_driver": DESKTOP_DRIVER_TOOLS,
    # L2: ecosystem workflow tools
    "ecosystem_workflow": ECOSYSTEM_WORKFLOW_TOOLS,
    # L2: publishing workflow tools
    "publishing_workflow": PUBLISHING_WORKFLOW_TOOLS,
    # L2: workflow runtime tools
    "workflow_runtime": WORKFLOW_RUNTIME_TOOLS,
    # L2: document conversion
    "document_convert": [convert_document_tool],
    # L2: image processing
    "image_processing": [process_image_tool],
    # L2: codex CLI
    "codex_cli": [codex_cli_tool],
}

# L3: MCP / plugin tools (loaded only when explicitly enabled)
L3_MCP_PLUGIN_TOOLS: dict[str, list[BaseTool]] = {
    "openharness_compat": OPENHARNESS_COMPAT_TOOLS,
    "bytebot_compat": BYTEBOT_COMPAT_TOOLS,
    "software_interface": SOFTWARE_INTERFACE_TOOLS,
}


# ---------------------------------------------------------------------------
# Backwards-compat alias
# ---------------------------------------------------------------------------

BUILTIN_TOOLS: list[BaseTool] = BUILTIN_TOOLS_CORE + (OPENHARNESS_COMPAT_TOOLS if _openharness_compat_enabled() else [])

SUBAGENT_TOOLS: list[BaseTool] = [task_tool]


# ---------------------------------------------------------------------------
# Permission scopes and confirmation rules (unchanged)
# ---------------------------------------------------------------------------

BUILTIN_PERMISSION_SCOPES: dict[str, ToolPermissionScope] = {
    "codex_cli": "system",
    "cron_create": "system",
    "cron_delete": "system",
    "cron_toggle": "system",
    "remote_trigger": "system",
    "team_delete": "system",
    "task_stop": "directory",
    "task_update": "directory",
    "task_create": "directory",
    "task": "directory",
    "agent": "directory",
    "send_message": "directory",
    "team_create": "directory",
    "runtime_health_report": "system",
    "security_audit_scan": "directory",
    "config_drift_snapshot": "directory",
    "config_drift_check": "directory",
    "media_probe": "directory",
    "html_to_canvas": "system",
    "flipbook": "system",
    "host_shell": "system",
    "host_file_manage": "system",
    "tcp_connect": "system",
    "http_transfer": "system",
    "python_package_install": "system",
    "github_tool_install": "system",
    "managed_tool_list": "sandbox",
    "managed_tool_execute": "system",
    "managed_tool_uninstall": "system",
    "artifact_governance_status": "sandbox",
    "artifact_cleanup": "system",
    "process_manage": "system",
    "integrated_project_catalog": "sandbox",
    "integrated_workflow_run": "directory",
    "workflow_start": "directory",
    "workflow_status": "directory",
    "spawn_subagent": "directory",
    "checkpoint": "directory",
    "desktop_driver_status": "system",
    "desktop_screenshot": "system",
    "desktop_click": "system",
    "desktop_type_text": "system",
    "desktop_hotkey": "system",
    "desktop_scroll": "system",
    "software_interface_catalog": "sandbox",
    "software_interface_status": "sandbox",
    "software_interface_authorize": "system",
    "software_interface_list_tools": "directory",
    "software_interface_execute": "system",
    "awesome_selfhosted": "sandbox",
    "octo_doctor": "system",
    "lint_run": "directory",
    "frontend_typecheck": "directory",
    "playwright_run": "directory",
    "pytest_run": "directory",
    "pytest_collect": "directory",
    "trivy_scan": "directory",
    "bandit_scan": "directory",
    "static_security_scan": "directory",
    "dependency_audit": "directory",
    "secret_scan": "directory",
    "db_migration_plan": "system",
    "db_explain": "system",
    "db_schema_introspect": "system",
    "db_query_readonly": "system",
    "db_connect_check": "system",
    "git_commit_prepare": "directory",
    "git_apply_patch": "system",
    "git_fetch": "system",
    "git_branch": "sandbox",
    "git_log": "sandbox",
    "git_diff": "sandbox",
    "git_status": "sandbox",
    "ssh_copy": "system",
    "ssh_exec": "system",
    "ssh_probe": "system",
    "ssh_hosts_list": "system",
    "docker_compose_apply": "system",
    "docker_compose_plan": "system",
    "docker_inspect": "system",
    "docker_logs": "system",
    "docker_images": "system",
    "docker_ps": "system",
    "docker_status": "system",
    "writing_toolchain_status": "sandbox",
    "novel_project_store": "directory",
    "writestory": "directory",
    "chapter_drafter": "directory",
    "chapter-drafter": "directory",
    "chapter_writer": "directory",
    "webnovel_write": "directory",
    "webnovel-write": "directory",
    "writing_review_suite": "directory",
    "writing_format_export": "directory",
    "human_approval_gate": "directory",
    "browser_publisher": "system",
    "publication_auditor": "system",
    "wp_cli_publish": "system",
}

DANGEROUS_CONFIRMATION_TOOLS = {
    "codex_cli",
    "host_shell",
    "host_file_manage",
    "tcp_connect",
    "http_transfer",
    "python_package_install",
    "github_tool_install",
    "managed_tool_uninstall",
    "artifact_cleanup",
    "process_manage",
    "desktop_screenshot",
    "desktop_click",
    "desktop_type_text",
    "desktop_hotkey",
    "desktop_scroll",
    "software_interface_authorize",
    "software_interface_execute",
    "octo_doctor",
    "db_migration_plan",
    "db_explain",
    "db_schema_introspect",
    "db_query_readonly",
    "db_connect_check",
    "git_apply_patch",
    "git_fetch",
    "ssh_copy",
    "ssh_exec",
    "docker_compose_apply",
    "browser_publisher",
    "wp_cli_publish",
}


def _builtin_permission_scope(tool_name: str) -> ToolPermissionScope:
    return BUILTIN_PERMISSION_SCOPES.get(tool_name, "sandbox")


def _builtin_requires_confirmation(tool_name: str) -> bool:
    return tool_name in DANGEROUS_CONFIRMATION_TOOLS


# ---------------------------------------------------------------------------
# ToolCatalog (unchanged behaviour — loads core + vision + bytebot compat)
# ---------------------------------------------------------------------------


class ToolCatalog:
    def __init__(self, *, app_config_getter=get_app_config, resolver=resolve_variable):
        self._app_config_getter = app_config_getter
        self._resolver = resolver

    def load_configured_tools(self, groups: list[str] | None = None) -> list[BaseTool]:
        config = self._app_config_getter()
        tools: list[BaseTool] = []
        for tool_config in config.tools:
            if groups is not None and tool_config.group not in groups:
                continue
            try:
                resolved_tool = self._resolver(tool_config.use, BaseTool)
            except ImportError:
                if _is_removed_optional_tool(tool_config.use):
                    logger.warning(
                        "Skipping removed optional tool '%s' (%s). Remove it from config.yaml when convenient.",
                        tool_config.name,
                        tool_config.use,
                    )
                    continue
                raise
            tools.append(
                set_tool_permission_metadata(
                    resolved_tool,
                    tool_config.permission_scope,
                    source="configured",
                    group=tool_config.group,
                    requires_confirmation=tool_config.permission_scope == "system",
                )
            )
        return tools

    def load_builtin_tools(
        self,
        *,
        model_name: str | None = None,
        subagent_enabled: bool = False,
    ) -> list[BaseTool]:
        config = self._app_config_getter()
        resolved_model_name = model_name
        builtin_tools = BUILTIN_TOOLS.copy()

        if subagent_enabled:
            builtin_tools.extend(SUBAGENT_TOOLS)
            logger.info("Including subagent tools (task)")

        if _bytebot_compat_enabled():
            builtin_tools.extend(BYTEBOT_COMPAT_TOOLS)
            logger.info(
                "Including bytebot_compat tools (observation-only, %d entries)",
                len(BYTEBOT_COMPAT_TOOLS),
            )

        if resolved_model_name is None and config.models:
            resolved_model_name = config.models[0].name

        model_config = config.get_model_config(resolved_model_name) if resolved_model_name else None
        if model_config is not None and model_config.supports_vision:
            configured_names = _configured_tool_names(builtin_tools)
            if view_image_tool.name not in configured_names:
                builtin_tools.append(view_image_tool)
                logger.info(
                    "Including view_image_tool for model '%s' (supports_vision=True)",
                    resolved_model_name,
                )

        return [
            set_tool_permission_metadata(
                tool,
                _builtin_permission_scope(tool.name),
                source="builtin",
                requires_confirmation=_builtin_requires_confirmation(tool.name),
            )
            for tool in builtin_tools
        ]


__all__ = [
    "BUILTIN_TOOLS_CORE",
    "BUILTIN_TOOLS",
    "SUBAGENT_TOOLS",
    "LAZY_LOAD_REGISTRY",
    "L3_MCP_PLUGIN_TOOLS",
    "BUILTIN_PERMISSION_SCOPES",
    "DANGEROUS_CONFIRMATION_TOOLS",
    "ToolCatalog",
]
