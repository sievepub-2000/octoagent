from __future__ import annotations

from typing import Any

from src.tools.permissions import get_tool_permission_scope

from .contracts import ToolRegistryBuiltinItem

_BUILTIN_CATEGORY_MAP: dict[str, str] = {
    "bash": "file-io",
    "file_read": "file-io",
    "file_write": "file-io",
    "edit_file": "file-io",
    "glob": "file-io",
    "grep": "file-io",
    "read_webpage": "web",
    "web_fetch": "web",
    "web_search": "web",
    "lsp": "code",
    "notebook_edit": "code",
    "task": "agents",
    "task_create": "agents",
    "task_get": "agents",
    "task_list": "agents",
    "task_output": "agents",
    "task_stop": "agents",
    "task_update": "agents",
    "agent": "agents",
    "send_message": "agents",
    "team_create": "agents",
    "team_delete": "agents",
    "mcp_tool": "mcp",
    "mcp_auth": "mcp",
    "list_mcp_resources": "mcp",
    "read_mcp_resource": "mcp",
    "cron_create": "schedule",
    "cron_list": "schedule",
    "cron_delete": "schedule",
    "cron_toggle": "schedule",
    "remote_trigger": "schedule",
    "skill": "meta",
    "config": "meta",
    "brief": "meta",
    "sleep": "meta",
    "tool_search": "meta",
    "ask_user_question": "meta",
    "ask_clarification": "meta",
    "enter_plan_mode": "meta",
    "exit_plan_mode": "meta",
    "enter_worktree": "meta",
    "exit_worktree": "meta",
    "todo_write": "meta",
    "codex_cli": "meta",
    "view_image": "media",
    "process_image": "media",
    "present_file": "media",
    "convert_document": "media",
    "integrated_project_catalog": "plugins",
    "integrated_workflow_run": "workflow",
    "awesome_selfhosted": "reference",
    "writing_toolchain_status": "writing",
    "novel_project_store": "writing",
    "writestory": "writing",
    "chapter_drafter": "writing",
    "chapter-drafter": "writing",
    "chapter_writer": "writing",
    "webnovel_write": "writing",
    "webnovel-write": "writing",
    "writing_review_suite": "writing-review",
    "writing_format_export": "writing-export",
    "human_approval_gate": "governance",
    "browser_publisher": "publishing",
    "publication_auditor": "publishing",
    "wp_cli_publish": "publishing",
}


def builtin_category(name: str) -> str:
    return _BUILTIN_CATEGORY_MAP.get(name, "builtin")


_SYSTEM_ARTIFACT_TOOLS = {
    "docker_status",
    "docker_ps",
    "docker_images",
    "docker_logs",
    "docker_inspect",
    "ssh_exec",
    "git_diff",
    "secret_scan",
    "static_security_scan",
    "bandit_scan",
    "trivy_scan",
    "pytest_run",
    "octo_doctor",
    "novel_project_store",
    "writestory",
    "chapter_drafter",
    "chapter-drafter",
    "chapter_writer",
    "webnovel_write",
    "webnovel-write",
    "writing_review_suite",
    "writing_format_export",
    "browser_publisher",
    "publication_auditor",
    "wp_cli_publish",
}
_DEFAULT_TIMEOUTS = {
    "docker_status": 10,
    "ssh_exec": 30,
    "db_query_readonly": 20,
    "secret_scan": 90,
    "static_security_scan": 120,
    "bandit_scan": 120,
    "trivy_scan": 300,
    "pytest_run": 300,
    "awesome_selfhosted": 5,
    "octo_doctor": 30,
    "writing_toolchain_status": 30,
    "writing_review_suite": 120,
    "writing_format_export": 180,
    "browser_publisher": 60,
    "publication_auditor": 60,
    "wp_cli_publish": 120,
}


def _tool_parameters(tool) -> dict[str, Any]:
    args = getattr(tool, "args", None)
    if isinstance(args, dict):
        return args
    schema = getattr(tool, "args_schema", None)
    if schema is not None and hasattr(schema, "model_json_schema"):
        raw = schema.model_json_schema()
        return raw.get("properties", {}) if isinstance(raw, dict) else {}
    return {}


def _risk_level(scope: str, name: str) -> str:
    if scope == "system" or name in {"ssh_exec", "docker_compose_apply", "git_fetch", "db_migration_plan"}:
        return "high"
    if scope == "directory" or name in _SYSTEM_ARTIFACT_TOOLS:
        return "medium"
    return "low"


def _failure_modes(name: str, scope: str) -> list[str]:
    modes = ["tool_runtime_error", "invalid_arguments"]
    if scope in {"directory", "system"}:
        modes.append("permission_or_confirmation_required")
    if name.startswith("docker"):
        modes.extend(["docker_daemon_unavailable", "docker_permission_denied"])
    if name.startswith("ssh"):
        modes.extend(["ssh_host_unreachable", "ssh_auth_failed"])
    if name.startswith("db_"):
        modes.extend(["database_unreachable", "read_only_policy_blocked"])
    if name in {"bandit_scan", "trivy_scan", "pytest_run", "static_security_scan"}:
        modes.append("tool_binary_missing_or_failed")
    if name in {"writing_review_suite", "writing_format_export", "browser_publisher", "publication_auditor", "wp_cli_publish"}:
        modes.extend(["tool_binary_missing_or_failed", "external_service_or_browser_unavailable"])
    return modes


class ToolRegistryBuiltinCatalog:
    def __init__(self, *, get_available_tools_fn):
        self._get_available_tools_fn = get_available_tools_fn

    def list_items(self) -> list[ToolRegistryBuiltinItem]:
        from src.tools.catalog import BUILTIN_PERMISSION_SCOPES, LAZY_LOAD_REGISTRY

        all_builtin = list(self._get_available_tools_fn(include_mcp=False, subagent_enabled=True, permission_mode="system"))
        for category_tools in LAZY_LOAD_REGISTRY.values():
            all_builtin.extend(category_tools)
        seen: set[str] = set()
        items: list[ToolRegistryBuiltinItem] = []
        for tool in sorted(all_builtin, key=lambda item: item.name):
            if tool.name in seen:
                continue
            seen.add(tool.name)
            scope = BUILTIN_PERMISSION_SCOPES.get(tool.name, get_tool_permission_scope(tool))
            items.append(
                ToolRegistryBuiltinItem(
                    name=tool.name,
                    description=getattr(tool, "description", "") or "",
                    category=builtin_category(tool.name),
                    permission_scope=scope,
                    parameters=_tool_parameters(tool),
                    timeout_seconds=_DEFAULT_TIMEOUTS.get(tool.name),
                    output_artifacts=["runtime/system_tools/<tool>/artifacts/<timestamp>.json"] if tool.name in _SYSTEM_ARTIFACT_TOOLS else [],
                    risk_level=_risk_level(scope, tool.name),
                    failure_modes=_failure_modes(tool.name, scope),
                )
            )
        return items
