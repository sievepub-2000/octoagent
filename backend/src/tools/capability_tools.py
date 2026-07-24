from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener

from langchain_core.tools import tool

CapabilityKind = Literal[
    "skill",
    "plugin",
    "mcp_server",
    "hook",
    "channel",
    "command",
    "agent_persona",
    "reference",
    "builtin_tool",
    "managed_tool",
    "desktop_tool",
]
CAPABILITY_KINDS = {
    "skill",
    "plugin",
    "mcp_server",
    "hook",
    "channel",
    "command",
    "agent_persona",
    "reference",
    "builtin_tool",
    "managed_tool",
    "desktop_tool",
}


def _read_internal_json(url: str) -> dict | None:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "OctoAgent-capability-registry"})
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=4) as response:
            payload = json.loads(response.read(2_000_000).decode("utf-8"))
            return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _harness_items() -> tuple[dict, list[dict]]:
    """Build the authoritative inventory owned by the Harness."""

    from src.harness.hook_core import get_hook_core_service
    from src.harness.hooks import get_hook_registry
    from src.tools.builtins.bytebot_compat_tools import BYTEBOT_COMPAT_TOOLS
    from src.tools.builtins.desktop_driver_tools import DESKTOP_DRIVER_TOOLS, desktop_driver_status
    from src.tools.registry.service import ToolRegistryService

    registry = ToolRegistryService().build_registry()
    items: list[dict] = []
    items.extend(
        {
            "capability_id": f"skill:{item.name}",
            "kind": "skill",
            "name": item.name,
            "display_name": item.name,
            "description": item.description,
            "enabled": item.enabled,
            "source": "/api/skills",
            "metadata": {"category": item.category},
        }
        for item in registry.skills
    )
    items.extend(
        {
            "capability_id": f"mcp:{item.name}",
            "kind": "mcp_server",
            "name": item.name,
            "display_name": item.name,
            "description": item.description,
            "enabled": item.enabled,
            "source": "/api/mcp/config",
            "metadata": {
                "transport": item.transport,
                "status": item.status,
                "failure_reason": item.failure_reason,
                "tool_count": item.tool_count,
                "tools": item.tools,
                "permission_scope": item.permission_scope,
            },
        }
        for item in registry.mcp
    )
    items.extend(
        {
            "capability_id": f"plugin:{item.plugin_id}",
            "kind": "plugin",
            "name": item.plugin_id,
            "display_name": item.display_name,
            "description": "",
            "enabled": item.enabled,
            "source": "/api/plugins/registry",
            "metadata": {"category": item.category},
        }
        for item in registry.plugins
    )
    items.extend(
        {
            "capability_id": f"channel:{item.name}",
            "kind": "channel",
            "name": item.name,
            "display_name": item.name,
            "description": item.description,
            "enabled": item.enabled,
            "source": "/api/channels/",
            "metadata": {},
        }
        for item in registry.channels
    )
    items.extend(
        {
            "capability_id": f"builtin:{item.name}",
            "kind": "builtin_tool",
            "name": item.name,
            "display_name": item.name,
            "description": item.description,
            "enabled": True,
            "source": "/api/harness",
            "metadata": {
                "category": item.category,
                "permission_scope": item.permission_scope,
                "risk_level": item.risk_level,
                "parameters": item.parameters,
                "timeout_seconds": item.timeout_seconds,
                "failure_modes": item.failure_modes,
            },
        }
        for item in registry.builtin_tools
    )
    items.extend(
        {
            "capability_id": f"managed:{item.name}",
            "kind": "managed_tool",
            "name": item.name,
            "display_name": item.name,
            "description": item.description,
            "enabled": item.installed and item.callable,
            "source": "/api/harness",
            "metadata": {
                "source_type": item.source_type,
                "version": item.version,
                "installed": item.installed,
                "callable": item.callable,
            },
        }
        for item in registry.managed_tools
    )

    gateway_base = os.getenv("OCTOAGENT_GATEWAY_INTERNAL_URL", "").rstrip("/")
    hooks_payload = _read_internal_json(f"{gateway_base}/api/hooks") if gateway_base else None
    if hooks_payload is not None and isinstance(hooks_payload.get("hooks"), list):
        hook_rows = [row for row in hooks_payload["hooks"] if isinstance(row, dict)]
    else:
        hook_rows = list(get_hook_core_service().list_available_hooks())
        runtime_hooks: dict[str, list[str]] = {}
        for name, event in get_hook_registry().list_registered():
            runtime_hooks.setdefault(name, []).append(event)
        hook_names = {str(row.get("name", "")) for row in hook_rows}
        hook_rows.extend(
            {"name": name, "description": "OctoAgent runtime hook", "enabled": True, "triggers": events}
            for name, events in runtime_hooks.items()
            if name not in hook_names
        )
    items.extend(
        {
            "capability_id": f"hook:{row.get('name', '')}",
            "kind": "hook",
            "name": str(row.get("name", "")),
            "display_name": str(row.get("name", "")),
            "description": str(row.get("description", "")),
            "enabled": bool(row.get("enabled", True)),
            "source": "/api/hooks",
            "metadata": {"triggers": row.get("triggers", [])},
        }
        for row in hook_rows
        if row.get("name")
    )

    desktop_payload = _read_internal_json(f"{gateway_base}/api/harness/desktop-control/status") if gateway_base else None
    if desktop_payload is not None and isinstance(desktop_payload.get("tools"), list):
        desktop_enabled = bool(desktop_payload.get("enabled"))
        desktop_rows = [row for row in desktop_payload["tools"] if isinstance(row, dict) and row.get("name")]
    else:
        desktop_status = desktop_driver_status()
        desktop_enabled = bool(desktop_status.get("available"))
        desktop_rows = [
            {"name": tool.name, "description": (tool.description or "").split("\n", 1)[0]}
            for tool in [*DESKTOP_DRIVER_TOOLS, *BYTEBOT_COMPAT_TOOLS]
        ]
    items.extend(
        {
            "capability_id": f"desktop:{row['name']}",
            "kind": "desktop_tool",
            "name": str(row["name"]),
            "display_name": str(row["name"]),
            "description": str(row.get("description", "")),
            "enabled": desktop_enabled,
            "source": "/api/harness/desktop-control/status",
            "metadata": {"driver_available": desktop_enabled},
        }
        for row in desktop_rows
    )

    summary = registry.summary.model_dump()
    summary.update(
        {
            "hooks_total": len(hook_rows),
            "hooks_enabled": sum(1 for row in hook_rows if row.get("enabled", True)),
            "desktop_tools_total": len(desktop_rows),
            "desktop_tools_enabled": len(desktop_rows) if desktop_enabled else 0,
            "harness_total": len(items),
        }
    )
    return {"summary": summary, "runtime": registry.runtime.model_dump()}, items


def _normalize_capability_kind(kind: str | None) -> str | None:
    """Normalize loose model-supplied kind values.

    Some models emit optional tool arguments as JSON null, an empty string, or
    the literal text "null". Keep the public tool schema permissive and do the
    validation here so discovery never fails before the agent can recover.
    """

    if kind is None:
        return None
    normalized = str(kind).strip().lower()
    if normalized in {"", "all", "any", "none", "null"}:
        return None
    if normalized not in CAPABILITY_KINDS:
        raise ValueError(f"Unsupported capability kind {kind!r}. Expected one of: {', '.join(sorted(CAPABILITY_KINDS))}.")
    return normalized


@tool("list_capabilities", parse_docstring=True)
def list_capabilities_tool(
    kind: str | None = None,
    enabled_only: bool = True,
    max_items: int = 80,
) -> str:
    """List installed runtime capabilities such as skills, plugins, MCP servers, and hooks.

    Use this before selecting a managed skill/plugin/MCP/hook so the agent can
    choose installed capabilities instead of guessing from stale prompt text.

    Args:
        kind: Optional capability kind filter.
        enabled_only: Whether to include only enabled capabilities.
        max_items: Maximum number of capability items to return.
    """

    normalized_kind = _normalize_capability_kind(kind)
    registry, items = _harness_items()
    if normalized_kind:
        items = [item for item in items if item["kind"] == normalized_kind]
    if enabled_only:
        items = [item for item in items if item["enabled"]]

    limited_items = items[: max(1, min(max_items, 200))]
    payload = {
        "source": "/api/harness",
        "summary": registry["summary"],
        "runtime": registry["runtime"],
        "returned": len(limited_items),
        "truncated": len(items) > len(limited_items),
        "items": limited_items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _public_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}{parsed.path or ''}"


def _sanitize_probe_body(name: str, body: object) -> object:
    if not isinstance(body, dict):
        return body if isinstance(body, (str, int, float, bool)) else None
    if name == "app_server":
        persistence = body.get("persistence") if isinstance(body.get("persistence"), dict) else {}
        return {
            "status": body.get("status"),
            "service": body.get("service"),
            "persistence": {key: persistence.get(key) for key in ("backend", "ok", "checkpoints", "threads")},
        }
    if name == "system_executor":
        return {key: body.get(key) for key in ("status", "token_ready", "docker_socket")}
    if name == "runtime_doctor":
        checks = body.get("checks") if isinstance(body.get("checks"), list) else []
        return {
            "overall_status": body.get("overall_status"),
            "checks": [
                {key: row.get(key) for key in ("id", "title", "status", "detail", "recommendation")}
                for row in checks
                if isinstance(row, dict)
            ],
        }
    return {key: body.get(key) for key in ("status", "ok", "service") if key in body}


def _probe_json(name: str, url: str, *, expected_status: str | None = None) -> dict:
    """Probe an internal URL without consulting HTTP(S)_PROXY."""

    request = Request(url, headers={"Accept": "application/json", "User-Agent": "OctoAgent-runtime-inspector"})
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=4) as response:
            raw = response.read(1_000_000).decode("utf-8", errors="replace")
            try:
                body: object = json.loads(raw)
            except json.JSONDecodeError:
                body = raw[:500]
            sanitized = _sanitize_probe_body(name, body)
            semantic_status = body.get("status") if isinstance(body, dict) else None
            healthy = 200 <= response.status < 400 and (expected_status is None or semantic_status == expected_status)
            return {
                "name": name,
                "url": _public_url(url),
                "reachable": True,
                "healthy": healthy,
                "http_status": response.status,
                "body": sanitized,
            }
    except HTTPError as exc:
        return {"name": name, "url": _public_url(url), "reachable": True, "healthy": False, "http_status": exc.code}
    except Exception as exc:
        return {
            "name": name,
            "url": _public_url(url),
            "reachable": False,
            "healthy": False,
            "error_type": type(exc).__name__,
        }


def _project_version() -> str:
    candidates = [
        Path(os.getenv("OCTOAGENT_BACKEND_PATH", "/app/backend")) / "pyproject.toml",
        Path(__file__).resolve().parents[2] / "pyproject.toml",
    ]
    for path in candidates:
        try:
            return str(tomllib.loads(path.read_text(encoding="utf-8"))["project"]["version"])
        except (FileNotFoundError, KeyError, TypeError, tomllib.TOMLDecodeError):
            continue
    return "unknown"


@tool("inspect_octoagent_runtime", parse_docstring=True)
def inspect_octoagent_runtime_tool() -> str:
    """Inspect this OctoAgent deployment through authoritative, sanitized runtime sources.

    Use this for OctoAgent self-checks instead of enumerating environment
    variables, filesystem directories, processes, or guessed API routes.
    """

    from src.runtime.config import get_app_config
    from src.runtime.config.app_config import AppConfig

    app_config = get_app_config()
    registry, _items = _harness_items()
    gateway_base = os.getenv("OCTOAGENT_GATEWAY_INTERNAL_URL", "http://app-server:19802").rstrip("/")
    executor_base = os.getenv("OCTOAGENT_SYSTEM_EXECUTOR_URL", "http://system-executor:19808").rstrip("/")
    probes = {
        "app_server": _probe_json("app_server", f"{gateway_base}/health", expected_status="healthy"),
        "system_executor": _probe_json("system_executor", f"{executor_base}/health", expected_status="healthy"),
    }
    doctor = _probe_json("runtime_doctor", f"{gateway_base}/api/runtime/doctor")
    payload = {
        "status": "healthy" if all(item.get("healthy") for item in probes.values()) else "degraded",
        "version": _project_version(),
        "runtime_profile": os.getenv("OCTOAGENT_RUNTIME_PROFILE", "unknown"),
        "authoritative_sources": {
            "config": str(AppConfig.resolve_config_path()),
            "harness": "/api/harness",
            "hooks": "/api/hooks",
            "runtime_doctor": "/api/runtime/doctor",
            "langgraph_health": "/ok",
            "system_executor_health": "/health",
        },
        "services": probes,
        "runtime_doctor": doctor,
        "harness": registry,
        "inventory_semantics": {
            "harness_total": registry["summary"]["harness_total"],
            "note": (
                "Harness is the live inventory and dispatcher. Its private capability registry is the "
                "single source for model and operator capability discovery."
            ),
        },
        "models": [
            {
                "name": model.name,
                "display_name": model.display_name,
                "model": model.model,
                "provider_name": model.provider_name,
                "interface_type": model.resolved_interface_type(),
                "supports_thinking": model.supports_thinking,
                "supports_reasoning_effort": model.supports_reasoning_effort,
                "fallback_models": model.fallback_models,
            }
            for model in app_config.models
        ],
        "security": {
            "secrets_included": False,
            "note": "Credential values and raw environment variables are intentionally excluded.",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool("load_skill", parse_docstring=True)
def load_skill_tool(skill_name: str, category: str | None = None) -> str:
    """Load an enabled skill's SKILL.md content by name.

    Use this when a user request matches an installed skill and you need the
    skill workflow before acting.

    Args:
        skill_name: Skill name to load.
        category: Optional category filter, usually public or custom.
    """

    from src.storage.skills import load_skills

    normalized_name = skill_name.strip()
    normalized_category = category.strip() if category else None
    for skill in load_skills(enabled_only=True):
        if skill.name != normalized_name:
            continue
        if normalized_category and skill.category != normalized_category:
            continue
        content = skill.skill_file.read_text(encoding="utf-8")
        return f"# Skill: {skill.name}\nCategory: {skill.category}\nDescription: {skill.description}\nPath: {skill.skill_file}\n\n{content}"
    return f"Error: enabled skill not found: {skill_name}"


@tool("get_plugin_command", parse_docstring=True)
def get_plugin_command_tool(command_id: str) -> str:
    """Get the manifest details for an installed plugin command.

    Plugins in this system are workflow/advisory capabilities. Use this tool to
    resolve a command ID such as ce:plan or wrb:review before following it.

    Args:
        command_id: Plugin command ID to resolve.
    """

    from src.tools.plugins import get_plugin_service

    service = get_plugin_service()
    plugins = {plugin.plugin_id: plugin for plugin in service.list_plugins().plugins}
    for manifest in service.list_manifests().manifests:
        plugin = plugins.get(manifest.plugin_id)
        if plugin is not None and not plugin.enabled:
            continue
        for command in manifest.commands:
            if command.command_id != command_id:
                continue
            payload = {
                "plugin_id": manifest.plugin_id,
                "display_name": manifest.display_name,
                "description": manifest.description,
                "command": command.model_dump(),
                "review_flow": manifest.review_flow,
                "permissions": plugin.permissions if plugin else [],
                "runtime_requirements": plugin.runtime_requirements if plugin else [],
                "usage": "Follow the command summary and plugin review flow as workflow guidance; this command is not a shell command.",
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)
    return f"Error: enabled plugin command not found: {command_id}"
