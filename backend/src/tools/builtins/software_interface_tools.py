"""Agent tools for Composio-compatible software interfaces."""

from __future__ import annotations

import json
from typing import Any

from langchain.tools import tool

from src.tools.software_interfaces.catalog import get_software_interface, list_software_interfaces, summarize_categories
from src.tools.software_interfaces.composio_gateway import (
    authorize,
    delete_connection,
    execute,
    gateway_config,
    get_user_scopes,
    list_connections,
    list_tools,
    set_user_scopes,
)


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _loads_object(value: str | None) -> dict[str, Any]:
    if not value or not value.strip():
        return {}
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("JSON value must be an object")
    return data


@tool("software_interface_catalog", parse_docstring=True)
def software_interface_catalog_tool(category: str | None = None, search: str | None = None, limit: int = 80) -> str:
    """List available Composio-compatible software interfaces.

    Args:
        category: Optional category id, such as communication, office, mail_calendar, docs_storage, development, crm_sales, commerce_payments, social_media, or automation.
        search: Optional case-insensitive text search over slug and display name.
        limit: Maximum number of interfaces to return.
    """

    normalized_category = (category or "").strip().lower()
    query = (search or "").strip().lower()
    safe_limit = max(1, min(int(limit or 80), 160))
    items = []
    for item in list_software_interfaces():
        if normalized_category and item.category != normalized_category:
            continue
        if query and query not in item.slug.lower() and query not in item.name.lower():
            continue
        items.append(item.as_dict())
        if len(items) >= safe_limit:
            break
    return _json({"status": "ok", "total_catalog_size": len(list_software_interfaces()), "categories": summarize_categories(), "interfaces": items})


@tool("software_interface_status", parse_docstring=True)
def software_interface_status_tool() -> str:
    """Return software-interface gateway status and configured connection count."""

    cfg = gateway_config()
    connections = list_connections() if cfg.base_url and cfg.api_key_configured else {"status": "not_configured"}
    return _json({
        "status": "ok",
        "enabled": cfg.enabled,
        "mode": cfg.mode,
        "base_url_configured": bool(cfg.base_url),
        "api_key_configured": cfg.api_key_configured,
        "catalog_total": len(list_software_interfaces()),
        "connections": connections,
    })


@tool("software_interface_list_connections", parse_docstring=True)
def software_interface_list_connections_tool(toolkit: str | None = None) -> str:
    """List Composio software-interface connections.

    Args:
        toolkit: Optional toolkit slug used to filter the returned connections.
    """

    result = list_connections()
    normalized = (toolkit or "").strip().lower()
    if normalized and isinstance(result.get("connections"), list):
        result = {
            **result,
            "connections": [
                connection
                for connection in result["connections"]
                if isinstance(connection, dict) and str(connection.get("toolkit", "")).strip().lower() == normalized
            ],
        }
    return _json(result)


@tool("software_interface_authorize", parse_docstring=True)
def software_interface_authorize_tool(toolkit: str, extra_params_json: str | None = None) -> str:
    """Start an OAuth handoff for a software interface toolkit.

    Args:
        toolkit: Toolkit slug such as gmail, notion, slack, github, or googlecalendar.
        extra_params_json: Optional JSON object with provider-specific OAuth fields. Reserved fields cannot override toolkit/client identifiers.
    """

    item = get_software_interface(toolkit)
    if item is None:
        return _json({"success": False, "status": "unknown_toolkit", "toolkit": toolkit})
    extra = _loads_object(extra_params_json)
    result = authorize(item.slug, extra)
    return _json({"toolkit": item.slug, "name": item.name, "result": result})


@tool("software_interface_logout", parse_docstring=True)
def software_interface_logout_tool(toolkit: str | None = None, connection_id: str | None = None) -> str:
    """Disconnect an Composio software-interface account.

    Args:
        toolkit: Optional toolkit slug to find the first matching connection.
        connection_id: Optional explicit connection id returned by software_interface_list_connections.
    """

    if connection_id and connection_id.strip():
        return _json(delete_connection(connection_id.strip()))
    normalized = (toolkit or "").strip().lower()
    if not normalized:
        return _json({"success": False, "status": "missing_connection", "detail": "Pass either toolkit or connection_id."})
    connections = list_connections()
    if connections.get("status") == "not_configured":
        return _json(connections)
    for connection in connections.get("connections", []):
        if not isinstance(connection, dict):
            continue
        if str(connection.get("toolkit", "")).strip().lower() == normalized and connection.get("id"):
            return _json(delete_connection(str(connection["id"])))
    return _json({"success": False, "status": "not_connected", "toolkit": normalized})


@tool("software_interface_list_tools", parse_docstring=True)
def software_interface_list_tools_tool(toolkits_csv: str | None = None) -> str:
    """List action schemas for connected software-interface toolkits.

    Args:
        toolkits_csv: Optional comma-separated toolkit slugs. Omit to request all connected toolkit actions from the gateway.
    """

    toolkits = [part.strip().lower() for part in (toolkits_csv or "").split(",") if part.strip()] or None
    result = list_tools(toolkits)
    return _json({"requested_toolkits": toolkits, "result": result})


@tool("software_interface_scopes", parse_docstring=True)
def software_interface_scopes_tool(toolkit: str, pref_json: str | None = None) -> str:
    """Read or update per-toolkit read/write/admin scope preferences.

    Args:
        toolkit: Toolkit slug such as gmail, slack, or notion.
        pref_json: Optional JSON object with boolean read, write, and admin keys. Omit to read current scopes.
    """

    item = get_software_interface(toolkit)
    if item is None:
        return _json({"success": False, "status": "unknown_toolkit", "toolkit": toolkit})
    pref = _loads_object(pref_json)
    if pref:
        return _json(set_user_scopes(item.slug, pref))
    return _json(get_user_scopes(item.slug))


@tool("software_interface_execute", parse_docstring=True)
def software_interface_execute_tool(action: str, arguments_json: str | None = None) -> str:
    """Execute a Composio/Composio software-interface action.

    Args:
        action: Action slug returned by software_interface_list_tools, for example GMAIL_SEND_EMAIL.
        arguments_json: JSON object containing action arguments.
    """

    arguments = _loads_object(arguments_json)
    return _json(execute(action, arguments))


SOFTWARE_INTERFACE_TOOLS = [
    software_interface_catalog_tool,
    software_interface_status_tool,
    software_interface_list_connections_tool,
    software_interface_authorize_tool,
    software_interface_logout_tool,
    software_interface_list_tools_tool,
    software_interface_scopes_tool,
    software_interface_execute_tool,
]

__all__ = ["SOFTWARE_INTERFACE_TOOLS"]
