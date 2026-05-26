"""Smoke the closed operator contracts for capability, hook, distributed, tenant, monitoring, reflection, self-evolution, and governance modules."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

OPERATOR_TOKEN = "closure-operator-token"
WORKER_TOKEN = "closure-worker-token"
AUDIT_SECRET = "closure-audit-secret"


@dataclass
class ModuleClosureSmokeReport:
    ok: bool = True
    checks: list[dict[str, Any]] = field(default_factory=list)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _expect_status(response, expected: int, message: str) -> None:
    if response.status_code != expected:
        raise AssertionError(f"{message}: expected {expected}, got {response.status_code}, body={response.text[:500]}")


def _headers(role: str = "operator") -> dict[str, str]:
    return {
        "X-OctoAgent-Operator-Token": OPERATOR_TOKEN,
        "X-OctoAgent-Operator-Role": role,
    }


def _prepare_env(runtime_home: str) -> None:
    os.environ["OCTO_AGENT_HOME"] = runtime_home
    os.environ["OCTO_OPERATOR_TOKEN"] = OPERATOR_TOKEN
    os.environ["OCTO_EXECUTION_WORKER_TOKEN"] = WORKER_TOKEN
    os.environ["OCTO_OPERATOR_AUDIT_SECRET"] = AUDIT_SECRET
    os.environ["OCTO_OPERATOR_ACTOR"] = "closure-smoke"


def _check_operator_governance(report: ModuleClosureSmokeReport) -> None:
    from src.governance.operator import (
        confirmation_matches,
        redact_secrets,
        require_operator_access,
        signed_audit_event,
    )

    try:
        require_operator_access(role="operator", token="wrong")
    except ValueError:
        rejected = True
    else:
        rejected = False
    _expect(rejected, "operator token mismatch should be rejected")
    require_operator_access(role="admin", token=OPERATOR_TOKEN, minimum="admin")
    redacted = redact_secrets({"token": "secret-token-value", "nested": {"api_key": "abc123456"}})
    _expect(redacted["token"] == "***REDACTED***", "token field was not redacted")
    _expect(redacted["nested"]["api_key"] == "***REDACTED***", "api_key field was not redacted")
    audit = signed_audit_event("operator_governance.closure_smoke", token="hidden")
    _expect(audit.get("signature_algorithm") == "hmac-sha256", "audit signature must use HMAC when secret is configured")
    _expect(confirmation_matches("DELETE TENANT", "CONFIRM DELETE TENANT"), "confirmation helper mismatch")
    report.checks.append({"id": "operator-governance", "signature_algorithm": audit.get("signature_algorithm")})


def _check_capability_core(client: TestClient, report: ModuleClosureSmokeReport) -> None:
    registry = client.get("/api/capabilities/registry")
    registry.raise_for_status()
    items = registry.json().get("items") or []
    _expect(items, "capability registry must expose at least one item")
    capability_id = items[0]["capability_id"]

    forbidden = client.post("/api/capabilities/invalidate-cache")
    _expect_status(forbidden, 403, "capability cache mutation without operator token should fail")
    invalidated = client.post("/api/capabilities/invalidate-cache", headers=_headers())
    invalidated.raise_for_status()

    policy = client.put(
        f"/api/capabilities/policies/{capability_id}",
        headers=_headers(),
        json={"decision": "audit_only", "reason": "closure smoke", "operator": "closure-smoke"},
    )
    policy.raise_for_status()
    restored = client.put(
        f"/api/capabilities/policies/{capability_id}",
        headers=_headers(),
        json={"decision": "inherit", "reason": "closure smoke cleanup", "operator": "closure-smoke"},
    )
    restored.raise_for_status()
    exported = client.get("/api/capabilities/policies/export", headers=_headers("admin"))
    exported.raise_for_status()
    _expect(exported.json().get("signature"), "capability policy export missing signature")
    report.checks.append({"id": "capability-core", "capability_id": capability_id})


def _check_hook_core(client: TestClient, report: ModuleClosureSmokeReport) -> None:
    state = client.get("/api/hooks/state")
    state.raise_for_status()
    forbidden = client.post("/api/hooks/emit", json={"event": "closure.smoke", "payload": {}})
    _expect_status(forbidden, 403, "hook emit without operator token should fail")
    emitted = client.post(
        "/api/hooks/emit",
        headers=_headers(),
        json={"event": "closure.smoke", "payload": {"module": "hook_core"}},
    )
    emitted.raise_for_status()
    report.checks.append({"id": "hook-core", "listeners_invoked": emitted.json().get("listeners_invoked", 0)})


def _check_distributed_execution(client: TestClient, report: ModuleClosureSmokeReport) -> None:
    forbidden = client.post("/api/execution-nodes/dispatch", json={"task_id": "closure-noauth", "payload": {}})
    _expect_status(forbidden, 403, "distributed dispatch without operator token should fail")
    dispatched = client.post(
        "/api/execution-nodes/dispatch",
        headers=_headers(),
        json={"task_id": "closure-dispatch", "payload": {"mode": "closure"}},
    )
    dispatched.raise_for_status()
    payload = dispatched.json()
    _expect(payload.get("status") == "completed", f"distributed dispatch failed: {payload}")
    report.checks.append({"id": "distributed-execution", "dispatch_id": payload.get("dispatch_id")})


def _check_multi_tenant(client: TestClient, report: ModuleClosureSmokeReport) -> None:
    tenant_id = f"closure-{uuid.uuid4().hex[:8]}"
    forbidden = client.post("/api/tenants", json={"tenant_id": tenant_id})
    _expect_status(forbidden, 403, "tenant create without operator token should fail")
    created = client.post(
        "/api/tenants",
        headers=_headers(),
        json={"tenant_id": tenant_id, "display_name": "Closure Smoke", "tier": "pro"},
    )
    created.raise_for_status()
    exported = client.get("/api/tenants/export", headers=_headers("admin"))
    exported.raise_for_status()
    _expect(tenant_id in exported.json().get("tenants", {}), "tenant export missing created tenant")
    deleted = client.delete(
        f"/api/tenants/{tenant_id}",
        headers={**_headers(), "X-OctoAgent-Confirmation": "CONFIRM DELETE TENANT"},
    )
    deleted.raise_for_status()
    report.checks.append({"id": "multi-tenant", "tenant_id": tenant_id})


def _check_monitoring(client: TestClient, report: ModuleClosureSmokeReport) -> None:
    governance = client.get("/api/metrics/governance")
    governance.raise_for_status()
    _expect(governance.json().get("metric_count", 0) >= 1, "monitoring governance missing metrics")
    forbidden = client.post("/api/metrics/increment/closure_smoke_total", json={"amount": 1})
    _expect_status(forbidden, 403, "metric increment without operator token should fail")
    incremented = client.post(
        "/api/metrics/increment/closure_smoke_total",
        headers=_headers(),
        json={"amount": 1},
    )
    incremented.raise_for_status()
    report.checks.append({"id": "monitoring", "metric_count": governance.json().get("metric_count")})


def _check_reflection(client: TestClient, report: ModuleClosureSmokeReport) -> None:
    forbidden = client.post(
        "/api/reflection/observations",
        json={"task_id": "closure", "summary": "should fail without token"},
    )
    _expect_status(forbidden, 403, "reflection observation without operator token should fail")
    observed = client.post(
        "/api/reflection/observations",
        headers=_headers(),
        json={
            "task_id": "closure",
            "category": "outcome",
            "summary": "closure smoke observation",
            "details": {"status": "completed"},
            "severity": "info",
        },
    )
    observed.raise_for_status()
    derived = client.post("/api/reflection/insights/derive", headers=_headers())
    derived.raise_for_status()
    exported = client.get("/api/reflection/export", headers=_headers(), params={"dataset": "observations", "format": "jsonl"})
    exported.raise_for_status()
    _expect("closure smoke observation" in exported.text, "reflection export missing closure observation")
    report.checks.append({"id": "reflection", "observation_id": observed.json().get("observation_id")})


def _check_self_evolution(client: TestClient, report: ModuleClosureSmokeReport) -> None:
    forbidden = client.post(
        "/api/evolution/proposals",
        json={"change_type": "skill_config", "title": "noauth", "description": "noauth should fail", "proposed_change": {"x": 1}},
    )
    _expect_status(forbidden, 403, "evolution proposal without operator token should fail")
    created = client.post(
        "/api/evolution/proposals",
        headers=_headers(),
        json={
            "change_type": "skill_config",
            "title": "Closure smoke proposal",
            "description": "Validate the self-evolution governance lifecycle in closure smoke.",
            "proposed_change": {"enabled": True},
            "current_value": {"enabled": False},
            "source": "closure-smoke",
            "tags": ["closure"],
        },
    )
    created.raise_for_status()
    proposal_id = created.json()["proposal_id"]
    client.post(f"/api/evolution/proposals/{proposal_id}/shadow-run", headers=_headers()).raise_for_status()
    validation = client.post(f"/api/evolution/proposals/{proposal_id}/validate", headers=_headers())
    validation.raise_for_status()
    _expect(validation.json().get("passed") is True, f"evolution validation failed: {validation.text}")
    client.post(f"/api/evolution/proposals/{proposal_id}/approve", headers=_headers("admin"), json={"approved_by": "closure-smoke"}).raise_for_status()
    promoted = client.post(f"/api/evolution/proposals/{proposal_id}/promote", headers=_headers("admin"))
    promoted.raise_for_status()
    _expect(promoted.json().get("status") == "promoted", f"proposal was not promoted: {promoted.text}")
    rolled_back = client.post(
        f"/api/evolution/proposals/{proposal_id}/rollback",
        headers=_headers("admin"),
        json={"reason": "closure smoke cleanup"},
    )
    rolled_back.raise_for_status()
    _expect(rolled_back.json().get("status") == "rolled_back", f"proposal was not rolled back: {rolled_back.text}")
    report.checks.append({"id": "self-evolution", "proposal_id": proposal_id})


def run() -> ModuleClosureSmokeReport:
    runtime_home = tempfile.mkdtemp(prefix="octoagent-closure-smoke-")
    _prepare_env(runtime_home)
    try:
        from src.gateway.app import app

        report = ModuleClosureSmokeReport()
        client = TestClient(app)
        _check_operator_governance(report)
        _check_capability_core(client, report)
        _check_hook_core(client, report)
        _check_distributed_execution(client, report)
        _check_multi_tenant(client, report)
        _check_monitoring(client, report)
        _check_reflection(client, report)
        _check_self_evolution(client, report)
        return report
    finally:
        shutil.rmtree(runtime_home, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = run()
    except Exception as exc:
        report = ModuleClosureSmokeReport(ok=False, checks=[{"id": "operator-module-closure-smoke", "error": str(exc)}])
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2 if args.json else None))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
