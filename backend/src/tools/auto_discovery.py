"""AST-based auto-discovery of tool functions in the tools/ tree.

Scans ``tools/builtins/*.py`` and recurses into ``tools/**/*.py`` to find
tool definitions without importing them.  Detection rules:

1. Functions decorated with ``@tool``, ``@register_tool``, or any decorator
   whose keyword arguments contain ``name=``.
2. Classes that subclass a known tool base (e.g. ``BaseTool`` from
   langchain, or any class whose name ends in ``Tool`` and has a
   ``name`` attribute).
3. Module-level constants whose names match the pattern ``*_TOOLS`` or
   ``*_TOOL`` and whose value is a list of tool instances (heuristic only;
   AST cannot evaluate runtime values, so this produces metadata hints).

Discovered tools are registered into the existing registry system via
``register_discovered_tool()``.  Scanning is incremental: files whose mtime
or SHA-256 hash has not changed since last scan are skipped.

Lazy-load: only runs at startup when ``OCTOAGENT_AUTO_DISCOVER=1`` env var
is set.  The module can also be imported and invoked manually for testing.
"""

from __future__ import annotations

import ast
import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ToolMetadata:
    """Lightweight metadata extracted from AST without importing the tool."""

    name: str
    module: str  # dotted module path relative to tools/ root
    file_path: str  # absolute path to source file
    func_name: str | None = None
    class_name: str | None = None
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    return_type: str = ""
    is_class_based: bool = False
    detection_reason: str = ""


@dataclass
class ScanState:
    """Tracks which files have been scanned and their last-known hashes."""

    file_hashes: dict[str, str] = field(default_factory=dict)
    discovered_tools: list[ToolMetadata] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------


def _file_hash(path: str) -> str:
    """Return SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _needs_rescan(filepath: str, state: ScanState) -> bool:
    """Return True if the file has changed since last scan."""
    current_hash = _file_hash(filepath)
    if not current_hash:
        return True
    previous = state.file_hashes.get(filepath)
    if previous is None:
        return True
    return current_hash != previous


# ---------------------------------------------------------------------------
# AST scanning
# ---------------------------------------------------------------------------

_TOOL_DECORATOR_NAMES = {"tool", "register_tool"}
_BASE_TOOL_CLASSNAMES = {"BaseTool", "StructuredTool"}


def _extract_docstring(node: ast.AST) -> str | None:
    """Extract the docstring from an expression statement node."""
    if isinstance(node, ast.Expr) and isinstance(node.value, (ast.Constant,)):
        val = node.value
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            return val.value.strip()
    return None


def _extract_decorator_name(dec: ast.expr) -> str | None:
    """Get the simple name of a decorator."""
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return dec.attr
    if isinstance(dec, ast.Call) and isinstance(dec.func, (ast.Name, ast.Attribute)):
        func = dec.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return None


def _extract_decorator_name_kwarg(call_node: ast.Call) -> str | None:
    """Extract ``name=`` keyword argument from a decorator call."""
    for kw in call_node.keywords:
        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


def _extract_func_parameters(func_node: ast.FunctionDef) -> dict[str, Any]:
    """Extract parameter names from a function definition."""
    params: dict[str, Any] = {}
    for arg in func_node.args.args:
        if arg.arg == "self":
            continue
        params[arg.arg] = {"type": "", "required": True}
    for arg in func_node.args.kwonlyargs:
        params[arg.arg] = {"type": "", "required": False}
    return params


def _extract_return_type(func_node: ast.FunctionDef) -> str:
    """Extract the return annotation string from a function."""
    if func_node.returns is not None:
        return ast.dump(func_node.returns)
    return ""


def _scan_function(
    node: ast.FunctionDef,
    module_name: str,
    filepath: str,
) -> ToolMetadata | None:
    """Check if a function definition represents a tool."""

    # Rule 1a: decorated with @tool or @register_tool
    for dec in node.decorator_list:
        dec_name = _extract_decorator_name(dec)
        if dec_name in _TOOL_DECORATOR_NAMES:
            name_kwarg = None
            if isinstance(dec, ast.Call):
                name_kwarg = _extract_decorator_name_kwarg(dec)
            return ToolMetadata(
                name=name_kwarg or node.name,
                module=module_name,
                file_path=filepath,
                func_name=node.name,
                description="",
                parameters=_extract_func_parameters(node),
                return_type=_extract_return_type(node),
                is_class_based=False,
                detection_reason=f"decorator @{dec_name}",
            )

    # Rule 1b: any decorator with name= keyword
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call):
            name_kwarg = _extract_decorator_name_kwarg(dec)
            if name_kwarg is not None:
                return ToolMetadata(
                    name=name_kwarg,
                    module=module_name,
                    file_path=filepath,
                    func_name=node.name,
                    description="",
                    parameters=_extract_func_parameters(node),
                    return_type=_extract_return_type(node),
                    is_class_based=False,
                    detection_reason="decorator with name= kwarg",
                )

    # Rule 3: function name contains "tool" or ends with "Tool" (heuristic)
    lower_name = node.name.lower()
    if ("_tool" in lower_name or node.name.endswith("Tool")) and not node.name.startswith("_"):
        return ToolMetadata(
            name=node.name,
            module=module_name,
            file_path=filepath,
            func_name=node.name,
            description="",
            parameters=_extract_func_parameters(node),
            return_type=_extract_return_type(node),
            is_class_based=False,
            detection_reason="name heuristic (contains 'tool')",
        )

    return None


def _scan_class(
    node: ast.ClassDef,
    module_name: str,
    filepath: str,
) -> ToolMetadata | None:
    """Check if a class definition represents a tool."""

    # Rule 2a: inherits from known base tool classes
    for base in node.bases:
        base_name = ""
        if isinstance(base, ast.Name):
            base_name = base.id
        elif isinstance(base, ast.Attribute):
            base_name = base.attr
        if base_name in _BASE_TOOL_CLASSNAMES:
            tool_name = node.name.rstrip("Tool") if node.name.endswith("Tool") else node.name
            return ToolMetadata(
                name=tool_name,
                module=module_name,
                file_path=filepath,
                class_name=node.name,
                description="",
                is_class_based=True,
                detection_reason=f"inherits from {base_name}",
            )

    # Rule 2b: class name ends with "Tool" (heuristic)
    if node.name.endswith("Tool") and not node.name.startswith("_"):
        return ToolMetadata(
            name=node.name.rstrip("Tool"),
            module=module_name,
            file_path=filepath,
            class_name=node.name,
            description="",
            is_class_based=True,
            detection_reason="class name heuristic (ends with 'Tool')",
        )

    return None


def _scan_module(
    tree: ast.Module,
    module_name: str,
    filepath: str,
) -> list[ToolMetadata]:
    """Scan a single AST module tree for tool definitions."""
    tools: list[ToolMetadata] = []

    # Scan top-level functions and classes
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            result = _scan_function(node, module_name, filepath)
            if result is not None:
                tools.append(result)
        elif isinstance(node, ast.ClassDef):
            result = _scan_class(node, module_name, filepath)
            if result is not None:
                tools.append(result)

    return tools


# ---------------------------------------------------------------------------
# File discovery and scanning
# ---------------------------------------------------------------------------


def _iter_tool_files(root_dir: Path) -> list[Path]:
    """Find all .py files under root_dir recursively."""
    files: list[Path] = []
    for path in sorted(root_dir.rglob("*.py")):
        rel = path.relative_to(root_dir)
        parts = rel.parts
        if "dynamic" in parts:
            continue
        files.append(path)
    return files


def _path_to_module_name(filepath: Path, root_dir: Path) -> str:
    """Convert a file path to a dotted module name relative to the tools root."""
    rel = filepath.relative_to(root_dir)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].replace(".py", "")
    return ".".join(parts)


def scan_tools_directory(
    tools_root: Path | str,
    state: ScanState | None = None,
) -> list[ToolMetadata]:
    """Scan the tools directory for tool definitions using AST analysis.

    Args:
        tools_root: Root directory containing tools/ (e.g. ``src/tools``).
        state: Optional previous scan state for incremental scanning.

    Returns:
        List of discovered ToolMetadata entries.
    """
    if isinstance(tools_root, str):
        tools_root = Path(tools_root)

    if not tools_root.is_dir():
        logger.warning("Tools root directory does not exist: %s", tools_root)
        return []

    # Scan both builtins/ and the full tools/ tree recursively.
    scan_roots: list[Path] = [tools_root / "builtins"]
    if tools_root != tools_root / "builtins":
        scan_roots.append(tools_root)

    state = state or ScanState()
    all_tools: list[ToolMetadata] = []
    seen_names: set[str] = set()

    for root_dir in scan_roots:
        if not root_dir.is_dir():
            continue
        files = _iter_tool_files(root_dir)
        for filepath in files:
            if not _needs_rescan(str(filepath), state):
                continue

            try:
                source_bytes = filepath.read_bytes()
                source = source_bytes.decode("utf-8", errors="replace")
                tree = ast.parse(source, filename=str(filepath))
            except SyntaxError as exc:
                logger.debug("Skipping %s due to syntax error: %s", filepath, exc)
                state.file_hashes[str(filepath)] = _file_hash(str(filepath))
                continue

            module_name = _path_to_module_name(filepath, tools_root)
            discovered = _scan_module(tree, module_name, str(filepath))

            for tool_meta in discovered:
                if tool_meta.name not in seen_names:
                    seen_names.add(tool_meta.name)
                    all_tools.append(tool_meta)

            state.file_hashes[str(filepath)] = _file_hash(str(filepath))

    logger.info(
        "AST auto-discovery found %d tool definitions across %d files",
        len(all_tools),
        len(state.file_hashes),
    )
    return all_tools


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

_discovered_registry: list[ToolMetadata] = []


def register_discovered_tool(metadata: ToolMetadata) -> None:
    """Register a single discovered tool into the in-memory registry."""
    _discovered_registry.append(metadata)


def get_discovered_tools() -> list[ToolMetadata]:
    """Return all tools registered via auto-discovery."""
    return list(_discovered_registry)


def clear_discovered_tools() -> None:
    """Clear the discovered tools registry (useful for testing)."""
    _discovered_registry.clear()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_last_scan_state: ScanState | None = None


def auto_discover_and_register(tools_root: Path | str | None = None) -> list[ToolMetadata]:
    """Run auto-discovery if the env flag is set, register results.

    Only executes when ``OCTOAGENT_AUTO_DISCOVER=1`` is in the environment.
    Returns the list of discovered ToolMetadata entries regardless of whether
    registration happened (useful for testing/logging).
    """
    global _last_scan_state

    env_value = os.environ.get("OCTOAGENT_AUTO_DISCOVER", "").strip().lower()
    if env_value not in {"1", "true", "yes", "on"}:
        logger.debug(
            "Auto-discovery skipped (OCTOAGENT_AUTO_DISCOVER=%r). Set to 1 to enable.",
            os.environ.get("OCTOAGENT_AUTO_DISCOVER"),
        )
        return []

    if tools_root is None:
        candidate = Path(__file__).resolve().parent.parent / "tools"
        if not candidate.is_dir():
            candidate = Path.cwd() / "src" / "tools"
        tools_root = candidate

    state = _last_scan_state or ScanState()
    discovered = scan_tools_directory(tools_root, state)
    _last_scan_state = state

    for tool_meta in discovered:
        register_discovered_tool(tool_meta)

    return discovered


__all__ = [
    "ToolMetadata",
    "ScanState",
    "scan_tools_directory",
    "register_discovered_tool",
    "get_discovered_tools",
    "clear_discovered_tools",
    "auto_discover_and_register",
]
