"""Local MCP server for OpenAPI inspection."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("octoagent-openapi")


def _response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _load_spec(spec: str, timeout_seconds: int) -> dict[str, Any]:
    if spec.startswith(("http://", "https://")):
        with urllib.request.urlopen(spec, timeout=max(1, min(int(timeout_seconds), 30))) as resp:
            return json.loads(resp.read(2_000_000).decode("utf-8"))
    path = Path(spec).expanduser().resolve()
    return json.loads(path.read_text(encoding="utf-8"))


@mcp.tool()
def openapi_summary(spec: str = "http://127.0.0.1:19802/openapi.json", timeout_seconds: int = 8) -> str:
    """Summarize an OpenAPI JSON document from a URL or local file."""
    try:
        data = _load_spec(spec, timeout_seconds)
        paths = data.get("paths") if isinstance(data, dict) else {}
        path_items = paths if isinstance(paths, dict) else {}
        operations: list[dict[str, str]] = []
        for path, methods in sorted(path_items.items()):
            if not isinstance(methods, dict):
                continue
            for method, op in sorted(methods.items()):
                if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                    continue
                summary = op.get("summary", "") if isinstance(op, dict) else ""
                operations.append({"method": method.upper(), "path": str(path), "summary": str(summary)[:180]})
        info = data.get("info") if isinstance(data, dict) else {}
        return _response(
            {
                "ok": True,
                "source": spec,
                "title": str(info.get("title", "")) if isinstance(info, dict) else "",
                "version": str(info.get("version", "")) if isinstance(info, dict) else "",
                "paths": len(path_items),
                "operations": len(operations),
                "sample_operations": operations[:25],
            }
        )
    except Exception as exc:  # noqa: BLE001 - MCP boundary returns structured failure
        return _response({"ok": False, "error": type(exc).__name__, "detail": str(exc)[:500], "source": spec})


if __name__ == "__main__":
    mcp.run()
