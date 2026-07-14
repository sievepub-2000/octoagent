"""Dependency graph analyzer for tool call parallelization.

Parses tool call arguments to detect shared resources (file paths, database
tables, URLs) and builds a DAG that determines which calls can execute in
parallel versus which must wait for predecessors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolCategory(str, Enum):
    WRITE = "write"
    EXEC = "exec"
    READ = "read"
    QUERY = "query"


_WRITE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "file_write",
        "code_edit",
        "create_file",
        "update_file",
        "write_code",
        "edit_code",
        "save_file",
        "patch_file",
        "apply_patch",
        "mkdir",
        "rmdir",
        "rm",
        "delete_file",
        "rename_file",
    }
)

_EXEC_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "shell_exec",
        "run_command",
        "execute_command",
        "bash",
        "system_execute",
        "run_shell",
        "subprocess_run",
    }
)

_READ_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "file_read",
        "read_file",
        "grep",
        "search_files",
        "list_directory",
        "ls",
        "cat",
        "head",
        "tail",
        "find_files",
    }
)

_QUERY_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "database_query",
        "db_query",
        "sql_query",
        "web_search",
        "url_fetch",
        "web_fetch",
        "http_get",
        "search",
        "query_database",
    }
)


def classify_tool(tool_name: str) -> ToolCategory:
    name_lower = tool_name.lower().strip()
    if name_lower in _WRITE_TOOL_NAMES:
        return ToolCategory.WRITE
    if name_lower in _EXEC_TOOL_NAMES:
        return ToolCategory.EXEC
    if name_lower in _READ_TOOL_NAMES:
        return ToolCategory.READ
    if name_lower in _QUERY_TOOL_NAMES:
        return ToolCategory.QUERY
    return ToolCategory.READ


_PATH_PATTERN = re.compile(r'["\']([A-Za-z]:[/\\][^\s"\']+|/[^ \t"\']+)[ "\']')
_TABLE_PATTERN = re.compile(r'["\'](\w+\.table|\w+\.\w+)["\']', re.IGNORECASE)
_URL_PATTERN = re.compile(r'https?://[^\s"\'>]+')


def _extract_paths(args: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for value in args.values():
        if isinstance(value, str):
            found = _PATH_PATTERN.findall(value)
            paths.extend(found)
            # Also match direct path values (e.g. {"path": "/tmp/file.txt"})
            stripped = value.strip().strip('"').strip("'")
            if stripped and not any(c in stripped for c in " ,;|&$`") and (stripped.startswith("/") or ":" in stripped[:3]):
                if stripped not in paths:
                    paths.append(stripped)
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, str):
                    found = _PATH_PATTERN.findall(item)
                    paths.extend(found)
    return [p.replace(chr(92), "/") for p in paths]


def _extract_tables(args: dict[str, Any]) -> list[str]:
    tables: list[str] = []
    for value in args.values():
        if isinstance(value, str):
            found = _TABLE_PATTERN.findall(value)
            tables.extend(found)
    return [t.lower() for t in tables]


def _extract_urls(args: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for value in args.values():
        if isinstance(value, str):
            found = _URL_PATTERN.findall(value)
            urls.extend(found)
    return [u.lower() for u in urls]


def _get_directory(path: str) -> str:
    stripped = path.rstrip("/")
    idx = stripped.rfind("/")
    if idx > 0:
        return stripped[:idx]
    return stripped


@dataclass
class ToolCallRef:
    index: int
    tool_name: str
    args: dict[str, Any]
    category: ToolCategory
    paths: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)


@dataclass
class ExecutionLayer:
    layer_index: int
    calls: list[ToolCallRef] = field(default_factory=list)


def analyze_tool_calls(tool_calls: list[dict[str, Any]]) -> list[ExecutionLayer]:
    refs: list[ToolCallRef] = []
    for idx, call in enumerate(tool_calls):
        tool_name = str(call.get("tool", call.get("name", "")))
        args = dict(call.get("args", call.get("parameters", {})) or {})
        category = classify_tool(tool_name)
        paths = _extract_paths(args)
        tables = _extract_tables(args)
        urls = _extract_urls(args)
        refs.append(
            ToolCallRef(
                index=idx,
                tool_name=tool_name,
                args=args,
                category=category,
                paths=paths,
                tables=tables,
                urls=urls,
            )
        )

    n = len(refs)
    deps: list[set[int]] = [set() for _ in range(n)]

    for i in range(n):
        for j in range(i + 1, n):
            if _has_dependency(refs[i], refs[j]):
                deps[j].add(i)

    layers: list[ExecutionLayer] = []
    assigned: set[int] = set()
    remaining = set(range(n))

    while remaining:
        layer_calls: list[ToolCallRef] = []
        ready_at_start = set(assigned)
        for idx in sorted(remaining):
            if all(d in ready_at_start for d in deps[idx]):
                layer_calls.append(refs[idx])
                assigned.add(idx)
        if not layer_calls:
            for idx in sorted(remaining):
                layer_calls.append(refs[idx])
                assigned.add(idx)
        layers.append(ExecutionLayer(layer_index=len(layers), calls=layer_calls))
        remaining -= assigned - {c.index for c in layer_calls}
        remaining = remaining - assigned

    return layers


def _has_dependency(a: ToolCallRef, b: ToolCallRef) -> bool:
    if a.category == ToolCategory.WRITE:
        shared_paths = set(a.paths) & set(b.paths)
        if shared_paths:
            return True
        a_dirs = {_get_directory(p) for p in a.paths}
        b_dirs = {_get_directory(p) for p in b.paths}
        if a_dirs & b_dirs and len(a_dirs | b_dirs) > 0:
            return True

    if a.category == ToolCategory.WRITE and b.category == ToolCategory.WRITE:
        shared_paths = set(a.paths) & set(b.paths)
        if shared_paths:
            return True
        a_dirs = {_get_directory(p) for p in a.paths}
        b_dirs = {_get_directory(p) for p in b.paths}
        if a_dirs & b_dirs and len(a_dirs | b_dirs) > 0:
            return True

    if a.category == ToolCategory.EXEC and b.category == ToolCategory.EXEC:
        shared_paths = set(a.paths) & set(b.paths)
        if shared_paths:
            return True
        a_dirs = {_get_directory(p) for p in a.paths}
        b_dirs = {_get_directory(p) for p in b.paths}
        if a_dirs & b_dirs and len(a_dirs | b_dirs) > 0:
            return True

    shared_tables = set(a.tables) & set(b.tables)
    if shared_tables:
        return True

    shared_urls = set(a.urls) & set(b.urls)
    if shared_urls:
        return True

    return False


def group_calls_by_category(layers: list[ExecutionLayer]) -> dict[str, list[ToolCallRef]]:
    groups: dict[str, list[ToolCallRef]] = {}
    for layer in layers:
        for call_ref in layer.calls:
            cat_key = call_ref.category.value
            if cat_key not in groups:
                groups[cat_key] = []
            groups[cat_key].append(call_ref)
    return groups
