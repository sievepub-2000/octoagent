"""Small Composio-compatible Composio gateway client."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SoftwareInterfaceGatewayConfig:
    enabled: bool
    base_url: str
    api_key_configured: bool
    mode: str


def _truthy(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def gateway_config() -> SoftwareInterfaceGatewayConfig:
    base_url = os.environ.get("OCTOAGENT_COMPOSIO_BASE_URL", "").strip().rstrip("/")
    return SoftwareInterfaceGatewayConfig(
        enabled=_truthy(os.environ.get("OCTOAGENT_SOFTWARE_INTERFACES_ENABLED"), default=True),
        base_url=base_url,
        api_key_configured=bool(os.environ.get("OCTOAGENT_COMPOSIO_API_KEY", "").strip()),
        mode=os.environ.get("OCTOAGENT_COMPOSIO_MODE", "composio-compatible").strip() or "composio-compatible",
    )


def _not_configured(action: str) -> dict[str, Any]:
    cfg = gateway_config()
    return {
        "success": False,
        "status": "not_configured",
        "action": action,
        "detail": "Set OCTOAGENT_COMPOSIO_BASE_URL and OCTOAGENT_COMPOSIO_API_KEY to enable live software-interface OAuth and execution.",
        "enabled": cfg.enabled,
        "mode": cfg.mode,
    }


def _unwrap_gateway_envelope(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"success": True, "data": data}
    if "result" in data and "logs" in data and isinstance(data.get("logs"), list):
        result = data.get("result")
        return result if isinstance(result, dict) else {"success": True, "data": result}
    if "data" in data and isinstance(data.get("data"), dict):
        result = dict(data["data"])
        if "success" in data and "success" not in result:
            result["success"] = bool(data["success"])
        return result
    data.setdefault("success", True)
    return data


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = gateway_config()
    if not cfg.enabled:
        return {"success": False, "status": "disabled", "detail": "Software interfaces are disabled by OCTOAGENT_SOFTWARE_INTERFACES_ENABLED=0."}
    if not cfg.base_url or not cfg.api_key_configured:
        return _not_configured(path)

    url = f"{cfg.base_url}{path}"
    if query:
        clean_query = {key: value for key, value in query.items() if value not in (None, "", [])}
        if clean_query:
            url = f"{url}?{urllib.parse.urlencode(clean_query, doseq=True)}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "User-Agent": "octoagent-software-interfaces"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    api_key = os.environ.get("OCTOAGENT_COMPOSIO_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            data = json.loads(text) if text else {}
            return _unwrap_gateway_envelope(data)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return {"success": False, "status": "http_error", "code": exc.code, "detail": text[:2000]}
    except Exception as exc:
        return {"success": False, "status": "transport_error", "detail": str(exc)}


def list_toolkits() -> dict[str, Any]:
    return _request("GET", "/agent-integrations/composio/toolkits")


def list_connections() -> dict[str, Any]:
    return _request("GET", "/agent-integrations/composio/connections")


def authorize(toolkit: str, extra_params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"toolkit": toolkit}
    if extra_params:
        clean = dict(extra_params)
        for key in {"toolkit", "auth", "client_id"}:
            clean.pop(key, None)
        payload.update(clean)
    return _request("POST", "/agent-integrations/composio/authorize", payload)


def delete_connection(connection_id: str) -> dict[str, Any]:
    return _request("DELETE", f"/agent-integrations/composio/connections/{urllib.parse.quote(connection_id, safe='')}")


def list_tools(toolkits: list[str] | None = None) -> dict[str, Any]:
    query = None
    if toolkits:
        query = {"toolkits": ",".join(part.strip().lower() for part in toolkits if part.strip())}
    return _request("GET", "/agent-integrations/composio/tools", query=query)


def execute(tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return _request("POST", "/agent-integrations/composio/execute", {"tool": tool, "arguments": arguments or {}})


def sync_connection(connection_id: str, reason: str = "manual") -> dict[str, Any]:
    return _request("POST", "/agent-integrations/composio/sync", {"connection_id": connection_id, "reason": reason})


def get_user_scopes(toolkit: str) -> dict[str, Any]:
    return _request("GET", f"/agent-integrations/composio/scopes/{urllib.parse.quote(toolkit, safe='')}")


def set_user_scopes(toolkit: str, pref: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "toolkit": toolkit,
        "read": bool(pref.get("read", True)),
        "write": bool(pref.get("write", True)),
        "admin": bool(pref.get("admin", False)),
    }
    return _request("POST", f"/agent-integrations/composio/scopes/{urllib.parse.quote(toolkit, safe='')}", payload)


def list_available_triggers(toolkit: str, connection_id: str | None = None) -> dict[str, Any]:
    return _request(
        "GET",
        "/agent-integrations/composio/triggers/available",
        query={"toolkit": toolkit, "connection_id": connection_id},
    )


def list_active_triggers(toolkit: str | None = None, connection_id: str | None = None) -> dict[str, Any]:
    return _request(
        "GET",
        "/agent-integrations/composio/triggers",
        query={"toolkit": toolkit, "connection_id": connection_id},
    )


def enable_trigger(
    slug: str,
    connection_id: str,
    trigger_config: dict[str, Any] | None = None,
    toolkit: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"slug": slug, "connection_id": connection_id, "triggerConfig": trigger_config or {}}
    if toolkit:
        payload["toolkit"] = toolkit
    return _request("POST", "/agent-integrations/composio/triggers", payload)


def disable_trigger(trigger_id: str) -> dict[str, Any]:
    return _request("DELETE", f"/agent-integrations/composio/triggers/{urllib.parse.quote(trigger_id, safe='')}")
