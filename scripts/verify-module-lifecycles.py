#!/usr/bin/env python3
"""Run non-destructive CRUD/lifecycle probes against a live OctoAgent gateway.

Every created record uses a unique ``codex-audit-*`` name and is removed (or,
for projects, archived) in ``finally`` cleanup. Existing records are never
modified except the selected built-in plugin, whose original registry state is
restored. Channel probing is opt-in and intended for a clean installation.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path


class Api:
    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-OctoAgent-Operator-Role": "operator"}
        if token:
            self.headers["X-OctoAgent-Operator-Token"] = token

    def call(self, method: str, path: str, body=None, *, expected=(200,)):
        data = None if body is None else json.dumps(body).encode()
        headers = dict(self.headers)
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        if status not in expected:
            detail = raw.decode(errors="replace")[:800]
            raise RuntimeError(
                f"{method} {path}: expected {expected}, got {status}: {detail}"
            )
        return None if not raw else json.loads(raw)


def read_dotenv_value(path: str, key: str) -> str:
    if not path:
        return ""
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


def contains(items, key, value) -> bool:
    return any(isinstance(item, dict) and item.get(key) == value for item in items)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:19802")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--include-channel", action="store_true")
    args = parser.parse_args()
    token = os.getenv("OCTO_OPERATOR_TOKEN", "") or read_dotenv_value(
        args.env_file, "OCTO_OPERATOR_TOKEN"
    )
    api = Api(args.base_url, token)
    suffix = secrets.token_hex(4)
    names = {
        "model": f"codex-audit-model-{suffix}",
        "skill": f"codex-audit-skill-{suffix}",
        "mcp": f"codex-audit-mcp-{suffix}",
        "agent": f"codex-audit-agent-{suffix}",
        "tenant": f"codex-audit-tenant-{suffix}",
    }
    created: dict[str, str] = {}
    passed: list[str] = []
    plugin_original = None
    plugin_id = ""
    try:
        # Models: create, read, update, read, delete, absence.
        api.call(
            "POST",
            "/api/models",
            {
                "name": names["model"],
                "model": "audit/no-network",
                "display_name": "CRUD audit",
                "interface_type": "openai_compatible",
                "base_url": "http://127.0.0.1:9/v1",
                "api_key": "audit-only",
            },
        )
        created["model"] = names["model"]
        assert (
            api.call("GET", f"/api/models/{names['model']}")["name"] == names["model"]
        )
        api.call(
            "PUT",
            f"/api/models/{names['model']}",
            {"description": "updated-by-crud-audit"},
        )
        assert (
            api.call("GET", f"/api/models/{names['model']}")["description"]
            == "updated-by-crud-audit"
        )
        api.call("DELETE", f"/api/models/{names['model']}")
        created.pop("model")
        api.call("GET", f"/api/models/{names['model']}", expected=(404,))
        passed.append("models")

        # Skills.
        api.call(
            "POST",
            "/api/skills",
            {
                "name": names["skill"],
                "description": "CRUD audit skill",
                "content": "# Audit",
            },
        )
        created["skill"] = names["skill"]
        assert (
            api.call("GET", f"/api/skills/{names['skill']}")["name"] == names["skill"]
        )
        api.call(
            "PUT",
            f"/api/skills/{names['skill']}",
            {"description": "updated-by-crud-audit"},
        )
        assert (
            api.call("GET", f"/api/skills/{names['skill']}")["description"]
            == "updated-by-crud-audit"
        )
        api.call("DELETE", f"/api/skills/{names['skill']}")
        created.pop("skill")
        api.call("GET", f"/api/skills/{names['skill']}", expected=(404,))
        passed.append("skills")

        # MCP server registry (disabled so no child process is launched).
        api.call(
            "POST",
            "/api/mcp/servers",
            {
                "name": names["mcp"],
                "server": {
                    "enabled": False,
                    "type": "stdio",
                    "command": "false",
                    "description": "CRUD audit",
                },
            },
        )
        created["mcp"] = names["mcp"]
        mcp = api.call("GET", "/api/mcp/config")["mcp_servers"]
        assert mcp[names["mcp"]]["status"] == "disabled"
        api.call(
            "POST",
            "/api/mcp/servers",
            {
                "name": names["mcp"],
                "server": {
                    "enabled": False,
                    "type": "stdio",
                    "command": "false",
                    "description": "updated-by-crud-audit",
                },
            },
        )
        assert (
            api.call("GET", "/api/mcp/config")["mcp_servers"][names["mcp"]][
                "description"
            ]
            == "updated-by-crud-audit"
        )
        api.call("DELETE", f"/api/mcp/servers/{names['mcp']}")
        created.pop("mcp")
        assert names["mcp"] not in api.call("GET", "/api/mcp/config")["mcp_servers"]
        passed.append("mcp")

        # Global memory.
        memory = api.call(
            "POST", "/api/memory/global", {"title": "CRUD audit", "content": suffix}
        )
        created["memory"] = memory["id"]
        assert contains(
            api.call("GET", "/api/memory/global")["entries"], "id", memory["id"]
        )
        api.call(
            "PUT",
            f"/api/memory/global/{memory['id']}",
            {"title": "CRUD audit updated", "content": suffix},
        )
        entries = api.call("GET", "/api/memory/global")["entries"]
        assert any(
            item.get("id") == memory["id"] and item.get("title") == "CRUD audit updated"
            for item in entries
        )
        api.call("DELETE", f"/api/memory/global/{memory['id']}")
        created.pop("memory")
        assert not contains(
            api.call("GET", "/api/memory/global")["entries"], "id", memory["id"]
        )
        passed.append("memory")

        # Custom agents.
        api.call(
            "POST",
            "/api/agents",
            {
                "name": names["agent"],
                "description": "CRUD audit agent",
                "soul": "Be precise.",
            },
            expected=(201,),
        )
        created["agent"] = names["agent"]
        assert (
            api.call("GET", f"/api/agents/{names['agent']}")["name"] == names["agent"]
        )
        api.call(
            "PUT",
            f"/api/agents/{names['agent']}",
            {"description": "updated-by-crud-audit"},
        )
        assert (
            api.call("GET", f"/api/agents/{names['agent']}")["description"]
            == "updated-by-crud-audit"
        )
        api.call("DELETE", f"/api/agents/{names['agent']}", expected=(204,))
        created.pop("agent")
        api.call("GET", f"/api/agents/{names['agent']}", expected=(404,))
        passed.append("agents")

        # Projects: archive before confirmed metadata deletion. Workspace files
        # and conversation checkpoints are intentionally untouched.
        project = api.call(
            "POST",
            "/api/projects",
            {
                "name": f"CRUD audit {suffix}",
                "root_path": "/app/workspace/default",
                "instructions": "created-by-crud-audit",
                "permission_mode": "directory",
            },
            expected=(201,),
        )
        project_id = project["project_id"]
        created["project"] = project_id
        assert api.call("GET", f"/api/projects/{project_id}")["project_id"] == project_id
        api.call(
            "PUT",
            f"/api/projects/{project_id}",
            {"instructions": "updated-by-crud-audit"},
        )
        assert (
            api.call("GET", f"/api/projects/{project_id}")["instructions"]
            == "updated-by-crud-audit"
        )
        api.call("PUT", f"/api/projects/{project_id}", {"status": "archived"})
        assert not contains(api.call("GET", "/api/projects"), "project_id", project_id)
        assert contains(
            api.call("GET", "/api/projects?include_archived=true"), "project_id", project_id
        )
        api.headers["X-OctoAgent-Confirmation"] = "CONFIRM DELETE PROJECT"
        api.call("DELETE", f"/api/projects/{project_id}", expected=(204,))
        api.headers.pop("X-OctoAgent-Confirmation", None)
        created.pop("project")
        api.call("GET", f"/api/projects/{project_id}", expected=(404,))
        passed.append("projects")

        # Multi-tenant governance.
        policy = {
            "workspace_isolation": "directory",
            "data_isolation": "tenant",
            "skill_sharing": "private",
            "max_concurrent_workspaces": 2,
            "max_agents_per_workspace": 3,
        }
        api.call(
            "POST",
            "/api/tenants",
            {
                "tenant_id": names["tenant"],
                "display_name": "CRUD audit",
                "tier": "free",
            },
            expected=(201,),
        )
        created["tenant"] = names["tenant"]
        assert (
            api.call("GET", f"/api/tenants/{names['tenant']}")["tenant"]["tenant_id"]
            == names["tenant"]
        )
        api.call("PUT", f"/api/tenants/{names['tenant']}/policy", policy)
        assert (
            api.call("GET", f"/api/tenants/{names['tenant']}")["policy"][
                "max_agents_per_workspace"
            ]
            == 3
        )
        api.headers["X-OctoAgent-Confirmation"] = "CONFIRM DELETE TENANT"
        api.call("DELETE", f"/api/tenants/{names['tenant']}", expected=(204,))
        api.headers.pop("X-OctoAgent-Confirmation", None)
        created.pop("tenant")
        api.call("GET", f"/api/tenants/{names['tenant']}", expected=(404,))
        passed.append("tenants")

        # Built-in plugin registry lifecycle, with exact original state restored.
        manifests = api.call("GET", "/api/plugins/manifests")["manifests"]
        registry = api.call("GET", "/api/plugins/registry")["entries"]
        if manifests:
            plugin_id = manifests[0]["plugin_id"]
            plugin_original = next(
                (entry for entry in registry if entry["plugin_id"] == plugin_id), None
            )
            if plugin_original is None:
                api.call(
                    "POST",
                    "/api/plugins/install",
                    {
                        "plugin_id": plugin_id,
                        "source": "builtin",
                        "enable_after_install": True,
                    },
                )
            api.call("POST", f"/api/plugins/{plugin_id}/disable")
            assert not next(
                x
                for x in api.call("GET", "/api/plugins/registry")["entries"]
                if x["plugin_id"] == plugin_id
            )["enabled"]
            api.call("POST", f"/api/plugins/{plugin_id}/enable")
            api.call("DELETE", f"/api/plugins/{plugin_id}")
            assert not contains(
                api.call("GET", "/api/plugins/registry")["entries"],
                "plugin_id",
                plugin_id,
            )
            api.call(
                "POST",
                "/api/plugins/install",
                {
                    "plugin_id": plugin_id,
                    "source": "builtin",
                    "enable_after_install": True,
                },
            )
            if plugin_original is None:
                api.call("DELETE", f"/api/plugins/{plugin_id}")
            elif not plugin_original["enabled"]:
                api.call("POST", f"/api/plugins/{plugin_id}/disable")
            passed.append("plugins")

        if args.include_channel:
            status = api.call("GET", "/api/channels/")
            candidate = next(
                (
                    name
                    for name, item in status["channels"].items()
                    if not item.get("configured")
                ),
                "",
            )
            if not candidate:
                raise RuntimeError("channel probe requires an unconfigured channel")
            api.call(
                "PUT",
                f"/api/channels/{candidate}/config",
                {"config": {"enabled": False}},
            )
            assert candidate in api.call("GET", "/api/channels/")["channels"]
            api.call("DELETE", f"/api/channels/{candidate}/config")
            passed.append("channels")

    finally:
        # Best-effort cleanup for interrupted probes; never touch unrelated IDs.
        cleanup = [
            ("model", "DELETE", f"/api/models/{names['model']}", (200, 404)),
            ("skill", "DELETE", f"/api/skills/{names['skill']}", (200, 404)),
            ("mcp", "DELETE", f"/api/mcp/servers/{names['mcp']}", (200, 404)),
            (
                "memory",
                "DELETE",
                f"/api/memory/global/{created.get('memory', '-')}",
                (200, 404),
            ),
            ("agent", "DELETE", f"/api/agents/{names['agent']}", (204, 404)),
        ]
        for key, method, path, expected in cleanup:
            if key in created:
                try:
                    api.call(method, path, expected=expected)
                except Exception as exc:  # noqa: BLE001
                    print(f"cleanup warning: {key}: {exc}", file=sys.stderr)
        if "project" in created:
            project_id = created["project"]
            try:
                api.call("PUT", f"/api/projects/{project_id}", {"status": "archived"}, expected=(200, 404))
                api.headers["X-OctoAgent-Confirmation"] = "CONFIRM DELETE PROJECT"
                api.call("DELETE", f"/api/projects/{project_id}", expected=(204, 404))
                api.headers.pop("X-OctoAgent-Confirmation", None)
            except Exception as exc:  # noqa: BLE001
                print(f"cleanup warning: project: {exc}", file=sys.stderr)
        if "tenant" in created:
            try:
                api.headers["X-OctoAgent-Confirmation"] = "CONFIRM DELETE TENANT"
                api.call(
                    "DELETE", f"/api/tenants/{names['tenant']}", expected=(204, 404)
                )
            except Exception as exc:  # noqa: BLE001
                print(f"cleanup warning: tenant: {exc}", file=sys.stderr)

    print(
        json.dumps({"ok": True, "passed": passed, "suffix": suffix}, ensure_ascii=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
