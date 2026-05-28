"""MCP smoke testing and degradation helpers."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.runtime.config.extensions_config import ExtensionsConfig, McpServerConfig

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SMOKE_PATH = _REPO_ROOT / "runtime" / "cache" / "mcp_smoke.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def smoke_results_path() -> Path:
    return _SMOKE_PATH


def load_mcp_smoke_snapshot() -> dict[str, Any]:
    if not _SMOKE_PATH.exists():
        return {"generated_at": None, "servers": {}}
    try:
        data = json.loads(_SMOKE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"generated_at": None, "servers": {}}
    except Exception:
        return {"generated_at": None, "servers": {}}


def server_smoke_failure_reason(server_name: str) -> str | None:
    if os.getenv("OCTOAGENT_MCP_IGNORE_SMOKE_FAILURES", "").strip().lower() in {"1", "true", "yes"}:
        return None
    servers = load_mcp_smoke_snapshot().get("servers", {})
    result = servers.get(server_name) if isinstance(servers, dict) else None
    if not isinstance(result, dict):
        return None
    if result.get("enabled") is False:
        return None
    if result.get("overall_status") in {"pass", "warn"}:
        return None
    return str(result.get("failure_reason") or result.get("overall_status") or "mcp_smoke_failed")


def _serialize_error(exc: BaseException) -> dict[str, str]:
    return {"type": type(exc).__name__, "message": str(exc)[:1000]}


def _build_server_params(server_name: str, config: McpServerConfig) -> dict[str, Any]:
    transport_type = config.type or "stdio"
    params: dict[str, Any] = {"transport": transport_type}
    if transport_type == "stdio":
        if not config.command:
            raise ValueError(f"MCP server '{server_name}' with stdio transport requires 'command' field")
        params["command"] = config.command
        params["args"] = config.args
        if config.env:
            params["env"] = config.env
    elif transport_type in {"sse", "http"}:
        if not config.url:
            raise ValueError(f"MCP server '{server_name}' with {transport_type} transport requires 'url' field")
        params["url"] = config.url
        if config.headers:
            params["headers"] = config.headers
    else:
        raise ValueError(f"MCP server '{server_name}' has unsupported transport type: {transport_type}")
    return params


def _configured_smoke(config: McpServerConfig) -> tuple[str | None, dict[str, Any]]:
    smoke = getattr(config, "smoke_test", None)
    if smoke is None or not getattr(smoke, "enabled", True):
        return None, {}
    tool_name = (getattr(smoke, "tool", "") or "").strip() or None
    args = getattr(smoke, "args", {}) or {}
    return tool_name, dict(args) if isinstance(args, dict) else {}


def _schema_check(name: str, config: McpServerConfig) -> dict[str, Any]:
    checks: dict[str, Any] = {"ok": True, "issues": []}
    if config.type == "stdio":
        if not config.command:
            checks["ok"] = False
            checks["issues"].append("stdio_command_missing")
        elif shutil.which(config.command) is None and not Path(config.command).exists():
            checks["ok"] = False
            checks["issues"].append("stdio_command_not_found")
    elif config.type in {"http", "sse"}:
        if not config.url:
            checks["ok"] = False
            checks["issues"].append("url_missing")
    else:
        checks["ok"] = False
        checks["issues"].append(f"unsupported_transport:{config.type}")
    missing_env = [key for key, value in config.env.items() if not str(value or "").strip()]
    if missing_env:
        checks["ok"] = False
        checks["issues"].append("env_missing:" + ",".join(sorted(missing_env)))
    if config.enabled and _configured_smoke(config)[0] is None:
        checks["ok"] = False
        checks["issues"].append("smoke_test_missing")
    checks["server"] = name
    return checks


async def smoke_one_mcp_server(name: str, config: McpServerConfig) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "enabled": bool(config.enabled),
        "transport": config.type,
        "permission_scope": config.permission_scope,
        "checked_at": _now(),
        "schema": _schema_check(name, config),
        "startup": {"ok": False, "skipped": True},
        "list_tools": {"ok": False, "skipped": True, "tool_count": 0, "tools": []},
        "minimal_call": {"ok": False, "skipped": True},
        "registry_visible": {"ok": True, "expected": True},
        "overall_status": "disabled" if not config.enabled else "fail",
        "failure_reason": "",
    }
    if not config.enabled:
        result["failure_reason"] = "server_disabled"
        return result
    if not result["schema"]["ok"]:
        result["failure_reason"] = ";".join(result["schema"].get("issues", []))
        return result

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        params = _build_server_params(name, config)
        client = MultiServerMCPClient({name: params})
        tools = await asyncio.wait_for(client.get_tools(), timeout=30)
        tool_names = [tool.name for tool in tools]
        result["startup"] = {"ok": True, "skipped": False}
        result["list_tools"] = {"ok": bool(tools), "skipped": False, "tool_count": len(tools), "tools": tool_names}
        smoke_tool_name, smoke_args = _configured_smoke(config)
        selected = None
        if smoke_tool_name:
            selected = next((tool for tool in tools if tool.name == smoke_tool_name), None)
            if selected is None:
                selected = next((tool for tool in tools if tool.name.endswith(smoke_tool_name)), None)
        if selected is None:
            result["minimal_call"] = {"ok": False, "skipped": False, "error": "configured_smoke_tool_not_found", "tool": smoke_tool_name}
        else:
            try:
                output = await asyncio.wait_for(selected.ainvoke(smoke_args), timeout=30)
                result["minimal_call"] = {
                    "ok": True,
                    "skipped": False,
                    "tool": selected.name,
                    "args": smoke_args,
                    "output_preview": str(output)[:1000],
                }
            except Exception as exc:  # noqa: BLE001 - captured in smoke report
                result["minimal_call"] = {"ok": False, "skipped": False, "tool": selected.name, "args": smoke_args, "error": _serialize_error(exc)}
        ok = bool(result["startup"].get("ok") and result["list_tools"].get("ok") and result["minimal_call"].get("ok"))
        result["overall_status"] = "pass" if ok else "fail"
        if not ok:
            if not result["list_tools"].get("ok"):
                result["failure_reason"] = "list_tools_failed_or_empty"
            elif not result["minimal_call"].get("ok"):
                result["failure_reason"] = "minimal_call_failed"
            else:
                result["failure_reason"] = "unknown_failure"
        return result
    except Exception as exc:  # noqa: BLE001 - captured in smoke report
        result["startup"] = {"ok": False, "skipped": False, "error": _serialize_error(exc)}
        result["overall_status"] = "fail"
        result["failure_reason"] = "startup_failed"
        return result


async def run_mcp_smoke_tests(config_path: str | None = None, *, include_disabled: bool = True, persist: bool = True) -> dict[str, Any]:
    config = ExtensionsConfig.from_file(config_path)
    servers = config.mcp_servers if include_disabled else config.get_enabled_mcp_servers()
    results: dict[str, Any] = {"generated_at": _now(), "servers": {}}
    for name, server_config in sorted(servers.items()):
        results["servers"][name] = await smoke_one_mcp_server(name, server_config)
    enabled = [item for item in results["servers"].values() if item.get("enabled")]
    results["summary"] = {
        "total": len(results["servers"]),
        "enabled": len(enabled),
        "passed": sum(1 for item in enabled if item.get("overall_status") == "pass"),
        "failed": sum(1 for item in enabled if item.get("overall_status") == "fail"),
        "disabled": sum(1 for item in results["servers"].values() if item.get("overall_status") == "disabled"),
    }
    if persist:
        _SMOKE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SMOKE_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return results


def main() -> None:
    results = asyncio.run(run_mcp_smoke_tests())
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
