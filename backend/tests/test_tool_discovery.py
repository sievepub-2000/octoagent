"""Tests for AST-based tool auto-discovery via builtin_catalog."""

from __future__ import annotations

import ast
import textwrap

import pytest

_TOOL_DECORATOR_SOURCE = textwrap.dedent('''\
    from langchain.tools import tool

    @tool("my_discovered_tool")
    def discovered_function(query: str) -> str:
        """A tool found via AST scanning."""
        return query

    @tool("another_tool")
    async def another_async_tool(path: str) -> str:
        """Another discovered async tool."""
        return path
''')


def _parse_tools(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "tool":
                if node.args and isinstance(node.args[0], ast.Constant):
                    names.append(str(node.args[0].value))
    return names


def test_ast_discovers_tools_with_string_name() -> None:
    names = _parse_tools(_TOOL_DECORATOR_SOURCE)
    assert "my_discovered_tool" in names
    assert "another_tool" in names


def test_ast_discovers_multiple_tools_in_one_file() -> None:
    extra = textwrap.dedent("""\
        from langchain.tools import tool

        @tool("tool_alpha")
        def alpha() -> str:
            return "a"

        @tool("tool_beta")
        def beta() -> str:
            return "b"

        @tool("tool_gamma")
        def gamma() -> str:
            return "c"
    """)
    names = _parse_tools(extra)
    assert sorted(names) == ["tool_alpha", "tool_beta", "tool_gamma"]


def test_ast_skips_non_tool_decorators() -> None:
    source = textwrap.dedent("""\
        def not_a_decorator(name):
            return name

        @not_a_decorator("skip_me")
        def ignored() -> str:
            return ""

        from langchain.tools import tool

        @tool("real_tool")
        def real() -> str:
            return "yes"
    """)
    names = _parse_tools(source)
    assert names == ["real_tool"]


def test_ast_handles_async_tool_definitions() -> None:
    source = textwrap.dedent("""\
        from langchain.tools import tool

        @tool("async_discovered")
        async def do_something(data: str) -> str:
            return data
    """)
    names = _parse_tools(source)
    assert "async_discovered" in names


def test_ast_handles_empty_source() -> None:
    assert _parse_tools("") == []


def test_builtin_catalog_lists_expected_categories() -> None:
    pytest.importorskip("langchain", reason="langchain not installed")
    from src.tools.registry.builtin_catalog import builtin_category

    assert builtin_category("bash") == "file-io"
    assert builtin_category("web_search") == "web"
    assert builtin_category("task") == "agents"
    assert builtin_category("mcp_tool") == "mcp"
    assert builtin_category("cron_create") == "schedule"
    assert builtin_category("skill") == "meta"


def test_risk_level_classification() -> None:
    pytest.importorskip("langchain", reason="langchain not installed")
    from src.tools.registry.builtin_catalog import _risk_level

    assert _risk_level("system", "ssh_exec") == "high"
    assert _risk_level("directory", "file_write") == "medium"
    assert _risk_level("user", "web_search") == "low"


def test_failure_modes_include_expected_entries() -> None:
    pytest.importorskip("langchain", reason="langchain not installed")
    from src.tools.registry.builtin_catalog import _failure_modes

    modes = _failure_modes("ssh_exec", "system")
    assert "ssh_host_unreachable" in modes
    assert "ssh_auth_failed" in modes

    modes = _failure_modes("docker_status", "directory")
    assert "docker_daemon_unavailable" in modes
