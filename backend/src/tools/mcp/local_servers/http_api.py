"""Local MCP server for safe HTTP API probes."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("octoagent-http-api")

_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_METHODS = {"GET", "HEAD"}


def _response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


@mcp.tool()
def http_api_probe(url: str = "http://127.0.0.1:19802/health", method: str = "GET", timeout_seconds: int = 8) -> str:
    """Probe an HTTP API endpoint with a read-only request."""
    parsed = urlparse(url)
    verb = method.strip().upper() or "GET"
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return _response({"ok": False, "error": "unsupported_scheme", "allowed": sorted(_ALLOWED_SCHEMES)})
    if verb not in _ALLOWED_METHODS:
        return _response({"ok": False, "error": "method_not_allowed", "allowed": sorted(_ALLOWED_METHODS)})
    req = urllib.request.Request(url, method=verb, headers={"User-Agent": "OctoAgent-HTTP-MCP/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=max(1, min(int(timeout_seconds), 30))) as resp:
            body = resp.read(4096)
            content_type = resp.headers.get("content-type", "")
            return _response(
                {
                    "ok": 200 <= int(resp.status) < 400,
                    "status": int(resp.status),
                    "url": url,
                    "content_type": content_type,
                    "body_preview": body.decode("utf-8", "replace")[:1000],
                }
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(2048).decode("utf-8", "replace")
        return _response({"ok": False, "status": int(exc.code), "url": url, "body_preview": body[:1000]})
    except Exception as exc:  # noqa: BLE001 - MCP boundary returns structured failure
        return _response({"ok": False, "error": type(exc).__name__, "detail": str(exc)[:500], "url": url})


if __name__ == "__main__":
    mcp.run()
