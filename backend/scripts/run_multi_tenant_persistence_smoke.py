"""Smoke tenant persistence and tenant-bound workspace/query policy metadata."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass
class SmokeReport:
    ok: bool = True
    checks: list[dict[str, Any]] = field(default_factory=list)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> SmokeReport:
    from src.gateway.app import app
    from src.governance.multi_tenant import TenantRegistry

    report = SmokeReport()
    client = TestClient(app)
    tenant_id = f"tenant-smoke-{uuid.uuid4().hex[:8]}"
    task_id = ""

    created = client.post(
        "/api/tenants",
        json={
            "tenant_id": tenant_id,
            "display_name": "Tenant Smoke",
            "tier": "pro",
            "policy": {
                "workspace_isolation": "namespace",
                "data_isolation": "row_level",
                "skill_sharing": "read_only",
                "max_concurrent_workspaces": 3,
                "max_agents_per_workspace": 6,
            },
        },
    )
    created.raise_for_status()
    report.checks.append({"id": "tenant-created", "tenant_id": tenant_id})

    workspace_response = client.post(
        "/api/task-workspaces",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": "tenant smoke", "goal": "verify tenant binding"},
    )
    workspace_response.raise_for_status()
    workspace = workspace_response.json()
    task_id = workspace["task_id"]
    _expect(workspace["metadata"]["tenant_id"] == tenant_id, "workspace tenant_id was not bound")
    report.checks.append({"id": "workspace-bound", "task_id": workspace["task_id"]})

    listed = client.get("/api/task-workspaces", headers={"X-Tenant-ID": tenant_id})
    listed.raise_for_status()
    task_ids = [item["task_id"] for item in listed.json().get("workspaces", [])]
    _expect(workspace["task_id"] in task_ids, "tenant-filtered workspace list missed created workspace")
    report.checks.append({"id": "workspace-filtered", "count": len(task_ids)})

    exported = client.get("/api/tenants/export")
    exported.raise_for_status()
    payload = exported.json()
    _expect(tenant_id in payload["tenants"], "exported registry missed tenant")
    reloaded = TenantRegistry(path=Path(payload["registry_path"]))
    _expect(reloaded.get_tenant(tenant_id).tenant_id == tenant_id, "tenant registry did not reload from disk")
    report.checks.append({"id": "registry-reloaded", "path": payload["registry_path"]})

    cleanup_workspace = client.delete(f"/api/task-workspaces/{task_id}") if task_id else None
    cleanup_tenant = client.delete(
        f"/api/tenants/{tenant_id}",
        headers={"X-OctoAgent-Confirmation": "CONFIRM DELETE TENANT"},
    )
    report.checks.append(
        {
            "id": "cleanup",
            "workspace_status": cleanup_workspace.status_code if cleanup_workspace is not None else None,
            "tenant_status": cleanup_tenant.status_code,
        }
    )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = run()
    except Exception as exc:
        report = SmokeReport(ok=False, checks=[{"id": "multi-tenant-persistence-smoke", "error": str(exc)}])
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2 if args.json else None))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
