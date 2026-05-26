from __future__ import annotations

import importlib

SYSTEM_TOOL_NAMES = {
    "flipbook",
    "host_shell",
    "host_file_manage",
    "html_to_canvas",
    "tcp_connect",
    "http_transfer",
    "python_package_install",
    "process_manage",
}


def _reload_catalog(monkeypatch, **env: str):
    import src.tools.catalog as catalog

    for key in ("OCTOAGENT_SYSTEM_TOOLS_ENABLED", "OCTOAGENT_SYSTEM_TOOLS"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(catalog)


def test_system_tools_can_be_disabled(monkeypatch) -> None:
    catalog = _reload_catalog(monkeypatch, OCTOAGENT_SYSTEM_TOOLS_ENABLED="0")
    names = {tool.name for tool in catalog.BUILTIN_TOOLS}
    assert names.isdisjoint(SYSTEM_TOOL_NAMES)


def test_system_tools_allowlist(monkeypatch) -> None:
    catalog = _reload_catalog(monkeypatch, OCTOAGENT_SYSTEM_TOOLS="host_shell,process_manage")
    selected = {tool.name for tool in catalog.BUILTIN_TOOLS if tool.name in SYSTEM_TOOL_NAMES}
    assert selected == {"host_shell", "process_manage"}


def test_default_system_tool_policy_preserves_backwards_compatibility(monkeypatch) -> None:
    catalog = _reload_catalog(monkeypatch)
    names = {tool.name for tool in catalog.BUILTIN_TOOLS}
    assert "host_shell" in names
    assert "process_manage" in names


def test_runtime_permission_mode_hides_system_tools_by_default(monkeypatch) -> None:
    _reload_catalog(monkeypatch)
    from src.tools import get_available_tools

    names = {tool.name for tool in get_available_tools(include_mcp=False, permission_mode="approval")}
    assert names.isdisjoint(SYSTEM_TOOL_NAMES)


def test_runtime_permission_mode_allows_system_tools_only_in_system_mode(monkeypatch) -> None:
    _reload_catalog(monkeypatch)
    from src.tools import get_available_tools

    directory_names = {tool.name for tool in get_available_tools(include_mcp=False, permission_mode="directory")}
    system_names = {tool.name for tool in get_available_tools(include_mcp=False, permission_mode="system")}
    assert directory_names.isdisjoint(SYSTEM_TOOL_NAMES)
    assert "host_shell" in system_names
    assert "process_manage" in system_names
