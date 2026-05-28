from __future__ import annotations

import logging
import os
from collections.abc import Iterable

from langchain.tools import BaseTool

from src.harness.reflection import resolve_variable
from src.runtime.config import get_app_config
from src.tools.builtins import (
    BYTEBOT_COMPAT_TOOLS,
    DESKTOP_DRIVER_TOOLS,
    ECOSYSTEM_WORKFLOW_TOOLS,
    OPENHARNESS_COMPAT_TOOLS,
    SOFTWARE_INTERFACE_TOOLS,
    SYSTEM_EXTRA_TOOLS,
    SYSTEM_OPS_TOOLS,
    archival_memory_insert_tool,
    archival_memory_search_tool,
    ask_clarification_tool,
    codex_cli_tool,
    convert_document_tool,
    get_plugin_command_tool,
    list_capabilities_tool,
    load_skill_tool,
    memory_block_list_tool,
    memory_block_upsert_tool,
    present_file_tool,
    process_image_tool,
    propose_self_evolution_tool,
    read_webpage_tool,
    search_memory_tool,
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


def _system_ops_tools_enabled() -> bool:
    """Gate host-level tools behind an operator-controlled flag.

    Default remains enabled for backwards compatibility, but production
    deployments can now run a least-privilege profile with
    ``OCTOAGENT_SYSTEM_TOOLS_ENABLED=0`` or provide a narrow allow-list via
    ``OCTOAGENT_SYSTEM_TOOLS=host_shell,process_manage``. This mirrors mature
    coding agents: shell/file/network surfaces are explicit operator policy,
    not an unchangeable prompt tax.
    """

    return _env_flag("OCTOAGENT_SYSTEM_TOOLS_ENABLED", default=True)


def _allowed_system_tool_names() -> set[str] | None:
    raw = os.environ.get("OCTOAGENT_SYSTEM_TOOLS", "").strip()
    if not raw:
        return None
    names = {part.strip() for part in raw.split(",") if part.strip()}
    return names or None


def _selected_system_ops_tools() -> list[BaseTool]:
    if not _system_ops_tools_enabled():
        logger.info("System operation tools disabled by OCTOAGENT_SYSTEM_TOOLS_ENABLED=0")
        return []
    allowlist = _allowed_system_tool_names()
    if allowlist is None:
        return list(SYSTEM_OPS_TOOLS)
    selected = [tool for tool in SYSTEM_OPS_TOOLS if tool.name in allowlist]
    missing = sorted(allowlist - {tool.name for tool in selected})
    if missing:
        logger.warning("Ignoring unknown OCTOAGENT_SYSTEM_TOOLS entries: %s", ", ".join(missing))
    logger.info("Including %d/%d system operation tools from OCTOAGENT_SYSTEM_TOOLS", len(selected), len(SYSTEM_OPS_TOOLS))
    return selected


BUILTIN_TOOLS_CORE: list[BaseTool] = [
    present_file_tool,
    ask_clarification_tool,
    list_capabilities_tool,
    load_skill_tool,
    get_plugin_command_tool,
    search_memory_tool,
    memory_block_upsert_tool,
    memory_block_list_tool,
    archival_memory_insert_tool,
    archival_memory_search_tool,
    propose_self_evolution_tool,
    codex_cli_tool,
    process_image_tool,
    read_webpage_tool,
    convert_document_tool,
]
BUILTIN_TOOLS_CORE.extend(_selected_system_ops_tools())
BUILTIN_TOOLS_CORE.extend(SYSTEM_EXTRA_TOOLS)
BUILTIN_TOOLS_CORE.extend(DESKTOP_DRIVER_TOOLS)
BUILTIN_TOOLS_CORE.extend(SOFTWARE_INTERFACE_TOOLS)
BUILTIN_TOOLS_CORE.extend(ECOSYSTEM_WORKFLOW_TOOLS)


def _openharness_compat_enabled() -> bool:
    """Sprint-1 P0 optimization: OPENHARNESS_COMPAT_TOOLS adds ~1542 LOC of
    tool descriptions to every system prompt. Default to OFF; opt in with
    OCTOAGENT_OPENHARNESS_ENABLED=1 if a workflow requires the legacy shim."""
    value = os.environ.get("OCTOAGENT_OPENHARNESS_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


# Backwards-compat alias: external imports of BUILTIN_TOOLS still resolve to a
# list — but now opt-in for the legacy compat shim. This shrinks the default
# system prompt by ~2.5 k tokens and keeps the shim available behind a flag.
def _load_dynamic_tools() -> list[BaseTool]:
    """Sprint-3: include any self-evolution-promoted dynamic tools."""
    try:
        from src.storage.self_evolution.dynamic_tools import list_dynamic_tools

        return list(list_dynamic_tools())
    except Exception:  # pragma: no cover — never block boot on dynamic tools
        return []


BUILTIN_TOOLS: list[BaseTool] = BUILTIN_TOOLS_CORE + (OPENHARNESS_COMPAT_TOOLS if _openharness_compat_enabled() else []) + _load_dynamic_tools()

SUBAGENT_TOOLS: list[BaseTool] = [task_tool]

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
    "process_manage": "system",
    "integrated_project_catalog": "sandbox",
    "integrated_workflow_run": "directory",
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
    "git_branch": "directory",
    "git_log": "directory",
    "git_diff": "directory",
    "git_status": "directory",
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
}

DANGEROUS_CONFIRMATION_TOOLS = {
    "codex_cli",
    "host_shell",
    "host_file_manage",
    "tcp_connect",
    "http_transfer",
    "python_package_install",
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
}


def _builtin_permission_scope(tool_name: str) -> ToolPermissionScope:
    return BUILTIN_PERMISSION_SCOPES.get(tool_name, "sandbox")


def _builtin_requires_confirmation(tool_name: str) -> bool:
    return tool_name in DANGEROUS_CONFIRMATION_TOOLS


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
