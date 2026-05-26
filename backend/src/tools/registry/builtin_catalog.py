from __future__ import annotations

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
}


def builtin_category(name: str) -> str:
    return _BUILTIN_CATEGORY_MAP.get(name, "builtin")


class ToolRegistryBuiltinCatalog:
    def __init__(self, *, get_available_tools_fn):
        self._get_available_tools_fn = get_available_tools_fn

    def list_items(self) -> list[ToolRegistryBuiltinItem]:
        all_builtin = self._get_available_tools_fn(include_mcp=False, subagent_enabled=True)
        seen: set[str] = set()
        items: list[ToolRegistryBuiltinItem] = []
        for tool in sorted(all_builtin, key=lambda item: item.name):
            if tool.name in seen:
                continue
            seen.add(tool.name)
            items.append(
                ToolRegistryBuiltinItem(
                    name=tool.name,
                    description=getattr(tool, "description", "") or "",
                    category=builtin_category(tool.name),
                    permission_scope=get_tool_permission_scope(tool),
                )
            )
        return items
