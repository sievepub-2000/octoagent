"""Local MCP server for Docker Compose inspection."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("octoagent-compose")

_REPO_ROOT = Path(__file__).resolve().parents[5]


def _response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _run(args: list[str], timeout_seconds: int = 20) -> dict[str, Any]:
    proc = subprocess.run(args, cwd=_REPO_ROOT, text=True, capture_output=True, timeout=timeout_seconds, check=False)
    return {"exit_code": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}


@mcp.tool()
def compose_version() -> str:
    """Return the installed Docker Compose plugin version."""
    result = _run(["docker", "compose", "version", "--short"], timeout_seconds=10)
    result["ok"] = result["exit_code"] == 0
    return _response(result)


@mcp.tool()
def compose_config_check(compose_file: str = "docker/docker-compose-dev.yaml") -> str:
    """Validate and render a compose file without applying it."""
    path = (_REPO_ROOT / compose_file).resolve()
    if not str(path).startswith(str(_REPO_ROOT)):
        return _response({"ok": False, "error": "compose_file_outside_repo"})
    if not path.exists():
        return _response({"ok": False, "error": "compose_file_missing", "compose_file": str(path)})
    result = _run(["docker", "compose", "-f", str(path), "config"], timeout_seconds=60)
    result.update({"ok": result["exit_code"] == 0, "compose_file": str(path)})
    return _response(result)


if __name__ == "__main__":
    mcp.run()
