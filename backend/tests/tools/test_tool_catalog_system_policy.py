"""System tools follow the narrow-waist, intent-loaded catalog contract."""

from __future__ import annotations

from src.agents.core.tool_loader import clear_session_cache, load_tools_for_intent
from src.tools import get_available_tools
from src.tools.catalog import BUILTIN_TOOLS, LAZY_LOAD_REGISTRY
from src.tools.registry.builtin_catalog import ToolRegistryBuiltinCatalog

SYSTEM_TOOL_NAMES = {
    "flipbook",
    "host_shell",
    "host_file_manage",
    "html_to_canvas",
    "tcp_connect",
    "http_transfer",
    "python_package_install",
    "github_tool_install",
    "managed_tool_uninstall",
    "process_manage",
}


def test_default_catalog_keeps_system_tools_out_of_every_prompt() -> None:
    names = {tool.name for tool in BUILTIN_TOOLS}
    assert names.isdisjoint(SYSTEM_TOOL_NAMES)


def test_system_tools_remain_available_through_the_lazy_registry() -> None:
    names = {tool.name for tool in LAZY_LOAD_REGISTRY["system_ops"]}
    assert {"host_shell", "process_manage"} <= names


def test_system_intent_loads_system_tools_on_demand() -> None:
    clear_session_cache("system-policy-test")
    tools = load_tools_for_intent("inspect server cpu and process state", session_id="system-policy-test")
    names = {tool.name for tool in tools}
    assert {"host_shell", "process_manage"} <= names


def test_install_and_delete_require_system_permission() -> None:
    clear_session_cache("tool-permission-test")
    directory_names = {
        tool.name
        for tool in load_tools_for_intent("install a github tool", session_id="tool-permission-test", permission_mode="directory")
    }
    clear_session_cache("tool-permission-test")
    system_names = {
        tool.name
        for tool in load_tools_for_intent("install a github tool", session_id="tool-permission-test", permission_mode="system")
    }
    assert "github_tool_install" not in directory_names
    assert "managed_tool_uninstall" not in directory_names
    assert {"github_tool_install", "managed_tool_uninstall"} <= system_names


def test_permission_mode_does_not_bypass_intent_loading() -> None:
    names = {tool.name for tool in get_available_tools(include_mcp=False, permission_mode="system")}
    assert names.isdisjoint(SYSTEM_TOOL_NAMES)


def test_tools_hub_catalog_includes_lazy_lifecycle_tools() -> None:
    names = {item.name for item in ToolRegistryBuiltinCatalog(get_available_tools_fn=get_available_tools).list_items()}
    assert {"github_tool_install", "managed_tool_list", "managed_tool_execute", "managed_tool_uninstall", "artifact_cleanup"} <= names
