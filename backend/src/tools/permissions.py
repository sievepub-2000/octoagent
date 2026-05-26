from __future__ import annotations

from typing import Any, Literal

from langchain.tools import BaseTool

ToolPermissionScope = Literal["sandbox", "directory", "system"]
RuntimePermissionMode = Literal["approval", "directory", "system"]

PERMISSION_SCOPE_ORDER: dict[ToolPermissionScope, int] = {
    "sandbox": 0,
    "directory": 1,
    "system": 2,
}


def normalize_tool_permission_scope(value: str | None) -> ToolPermissionScope:
    if value in PERMISSION_SCOPE_ORDER:
        return value  # type: ignore[return-value]
    return "sandbox"


def normalize_runtime_permission_mode(value: str | None) -> RuntimePermissionMode:
    """Normalize legacy and UI permission names to the three operator modes.

    The UI exposes:
    - approval: default approval mode; no host/system tools are exposed.
    - directory: repo/task-directory operations are available; host/system tools stay hidden.
    - system: full host-level tool surface is available and traceable.
    """

    normalized = (value or "").strip().lower()
    if normalized in {"system", "yolo", "full"}:
        return "system"
    if normalized in {"directory", "workspace", "repo", "project"}:
        return "directory"
    return "approval"


def max_tool_permission_scope(scopes: list[ToolPermissionScope]) -> ToolPermissionScope:
    if not scopes:
        return "sandbox"
    return max(scopes, key=lambda scope: PERMISSION_SCOPE_ORDER[scope])


def tool_allowed_in_permission_mode(scope: ToolPermissionScope, mode: str | None) -> bool:
    permission_mode = normalize_runtime_permission_mode(mode)
    if scope == "system":
        return permission_mode == "system"
    if scope == "directory":
        return permission_mode in {"approval", "directory", "system"}
    return True


def tool_requires_confirmation(scope: ToolPermissionScope, mode: str | None) -> bool:
    permission_mode = normalize_runtime_permission_mode(mode)
    if scope == "system":
        return permission_mode != "system"
    if scope == "directory":
        return permission_mode == "approval"
    return False


def set_tool_permission_metadata(
    tool: BaseTool,
    scope: ToolPermissionScope,
    *,
    source: str,
    group: str | None = None,
    requires_confirmation: bool | None = None,
) -> BaseTool:
    metadata: dict[str, Any] = dict(getattr(tool, "metadata", None) or {})
    metadata["permission_scope"] = scope
    metadata["tool_source"] = source
    if requires_confirmation is not None:
        metadata["requires_confirmation"] = requires_confirmation
    if group:
        metadata["tool_group"] = group
    tool.metadata = metadata
    return tool


def get_tool_permission_scope(tool: BaseTool) -> ToolPermissionScope:
    metadata = getattr(tool, "metadata", None) or {}
    return normalize_tool_permission_scope(str(metadata.get("permission_scope") or "sandbox"))


def apply_runtime_permission_policy(tools: list[BaseTool], mode: str | None) -> list[BaseTool]:
    permission_mode = normalize_runtime_permission_mode(mode)
    filtered: list[BaseTool] = []
    for tool in tools:
        scope = get_tool_permission_scope(tool)
        if not tool_allowed_in_permission_mode(scope, permission_mode):
            continue
        metadata: dict[str, Any] = dict(getattr(tool, "metadata", None) or {})
        metadata["active_permission_mode"] = permission_mode
        metadata["requires_confirmation"] = tool_requires_confirmation(scope, permission_mode)
        tool.metadata = metadata
        filtered.append(tool)
    return filtered


def dedupe_tools_by_name(tools: list[BaseTool]) -> list[BaseTool]:
    deduped: list[BaseTool] = []
    seen_names: set[str] = set()
    for tool in tools:
        if tool.name in seen_names:
            continue
        seen_names.add(tool.name)
        deduped.append(tool)
    return deduped
