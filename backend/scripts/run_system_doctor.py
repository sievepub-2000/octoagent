"""Run OctoAgent doctor and core API contract smoke checks."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass
class DoctorCheck:
    id: str
    status: str
    detail: str = ""
    seconds: float = 0.0
    error: str | None = None


@dataclass
class DoctorReport:
    ok: bool
    checks: list[DoctorCheck] = field(default_factory=list)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _timed(check_id: str, fn: Callable[[], str]) -> DoctorCheck:
    started = time.monotonic()
    try:
        detail = fn()
        return DoctorCheck(
            id=check_id,
            status="ok",
            detail=detail,
            seconds=round(time.monotonic() - started, 3),
        )
    except Exception as exc:  # pragma: no cover - operator diagnostic boundary
        return DoctorCheck(
            id=check_id,
            status="fail",
            seconds=round(time.monotonic() - started, 3),
            error=str(exc),
        )


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _git_sync_detail() -> str:
    root = _repo_root()
    status = subprocess.check_output(["git", "status", "--short"], cwd=root, text=True).strip()
    counts = subprocess.check_output(
        ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"],
        cwd=root,
        text=True,
    ).strip()
    _expect(not status, f"working tree is not clean: {status}")
    _expect(counts == "0	0", f"origin/main and HEAD diverged: {counts}")
    return "working_tree=clean, origin/main...HEAD=0 0"


def _json(client: TestClient, path: str) -> Any:
    response = client.get(path)
    response.raise_for_status()
    return response.json()


def _contract_checks(*, include_git: bool) -> list[DoctorCheck]:
    from src.gateway.app import app

    checks: list[DoctorCheck] = []
    if include_git:
        checks.append(_timed("git-sync", _git_sync_detail))

    client = TestClient(app)
    checks.append(
        _timed(
            "health-api",
            lambda: _check_health(client),
        )
    )
    checks.append(
        _timed(
            "runtime-doctor-api",
            lambda: _check_runtime_doctor(client),
        )
    )
    checks.append(
        _timed(
            "capability-registry-api",
            lambda: _check_capability_registry(client),
        )
    )
    checks.append(
        _timed(
            "capability-binding-contract-api",
            lambda: _check_binding_contract(client),
        )
    )
    checks.append(_timed("channels-api", lambda: _check_channels(client)))
    checks.append(_timed("models-api", lambda: _check_models(client)))
    checks.append(_timed("task-workspaces-api", lambda: _check_task_workspaces(client)))
    checks.append(_timed("memory-api", lambda: _check_memory(client)))
    checks.append(_timed("capability-policy-api", lambda: _check_capability_policy(client)))
    checks.append(_timed("capability-policy-export-api", lambda: _check_capability_policy_export(client)))
    checks.append(_timed("capability-policy-precheck-api", lambda: _check_capability_policy_precheck(client)))
    checks.append(_timed("runtime-provider-contract-api", lambda: _check_provider_contract(client)))
    checks.append(_timed("runtime-long-running-health-api", lambda: _check_long_running_health(client)))
    checks.append(_timed("runtime-maintenance-api", lambda: _check_runtime_maintenance(client)))
    checks.append(_timed("langgraph-contract-api", lambda: _check_langgraph_contract(client)))
    checks.append(_timed("workflow-langgraph-contract-smoke", lambda: _check_workflow_langgraph_contract_smoke()))
    checks.append(_timed("query-engine-maintenance-api", lambda: _check_query_engine_maintenance(client)))
    checks.append(_timed("distributed-execution-api", lambda: _check_distributed_execution(client)))
    checks.append(_timed("multi-tenant-api", lambda: _check_multi_tenant(client)))
    return checks


def _check_health(client: TestClient) -> str:
    payload = _json(client, "/health")
    _expect(payload.get("status") == "healthy", f"unexpected health payload: {payload}")
    return "status=healthy"


def _check_runtime_doctor(client: TestClient) -> str:
    payload = _json(client, "/api/runtime/doctor")
    checks = payload.get("checks") or []
    ids = {item.get("id") for item in checks if isinstance(item, dict)}
    required = {"config", "models", "capability-registry", "capability-binding-contract", "channels", "runtime-provider"}
    missing = sorted(required - ids)
    _expect(not missing, f"runtime doctor missing checks: {missing}")
    _expect(payload.get("overall_status") in {"ok", "warn", "fail"}, f"invalid doctor status: {payload}")
    return f"overall={payload.get('overall_status')}, checks={len(checks)}"


def _check_capability_registry(client: TestClient) -> str:
    payload = _json(client, "/api/capabilities/registry")
    summary = payload.get("summary") or {}
    total = int(summary.get("total_items") or 0)
    by_kind = summary.get("by_kind") or {}
    _expect(total > 0, "capability registry is empty")
    _expect("skill" in by_kind, f"skill kind missing: {by_kind}")
    _expect("channel" in by_kind, f"channel kind missing: {by_kind}")
    _expect(isinstance(payload.get("items"), list), "registry items must be a list")
    return f"items={total}, kinds={by_kind}"


def _check_binding_contract(client: TestClient) -> str:
    registry = _json(client, "/api/capabilities/registry")
    payload = _json(client, "/api/capabilities/binding-contract")
    registry_total = int((registry.get("summary") or {}).get("total_items") or 0)
    contract_total = int((payload.get("summary") or {}).get("total_items") or 0)
    _expect(contract_total == registry_total, f"contract_total={contract_total}, registry_total={registry_total}")
    items = payload.get("items") or []
    _expect(all("bindable_targets" in item and "dispatch_contract" in item for item in items[:10]), "contract item shape invalid")
    return f"items={contract_total}"


def _check_channels(client: TestClient) -> str:
    payload = _json(client, "/api/channels/")
    channels = payload.get("channels") or {}
    _expect(isinstance(channels, dict), "channels must be a mapping")
    _expect(len(channels) > 0, "channel registry is empty")
    return f"channels={len(channels)}, service_running={payload.get('service_running')}"


def _check_models(client: TestClient) -> str:
    payload = _json(client, "/api/models")
    models = payload.get("models") if isinstance(payload, dict) else None
    _expect(isinstance(models, list), "models endpoint should return an object with a models list")
    return f"models={len(models)}"


def _check_task_workspaces(client: TestClient) -> str:
    payload = _json(client, "/api/task-workspaces")
    workspaces = payload.get("workspaces")
    _expect(isinstance(workspaces, list), "task workspaces payload must contain workspaces list")
    return f"workspaces={len(workspaces)}"


def _check_memory(client: TestClient) -> str:
    payload = _json(client, "/api/memory/status")
    _expect(isinstance(payload, dict), "memory status must be an object")
    return f"keys={sorted(payload.keys())[:8]}"


def _check_capability_policy(client: TestClient) -> str:
    payload = _json(client, "/api/capabilities/policies")
    _expect(isinstance(payload.get("policies"), list), "policies must be a list")
    _expect(isinstance(payload.get("audit_events"), list), "audit_events must be a list")
    return f"policies={len(payload.get('policies') or [])}, audit_events={len(payload.get('audit_events') or [])}"


def _check_capability_policy_export(client: TestClient) -> str:
    payload = _json(client, "/api/capabilities/policies/export")
    _expect(payload.get("signature_algorithm") == "sha256", "policy export must be signed with sha256")
    _expect(bool(payload.get("signature")), "policy export signature missing")
    state = payload.get("state") or {}
    _expect(isinstance(state, dict), "policy export state must be an object")
    return f"signature={str(payload.get('signature'))[:12]}"


def _check_capability_policy_precheck(client: TestClient) -> str:
    payload = _json(client, "/api/capabilities/policies/precheck")
    _expect(payload.get("ok") is True, "policy precheck must return ok")
    _expect(bool(payload.get("signature")), "policy precheck signature missing")
    return f"policies={payload.get('policy_count')}, deny={payload.get('deny_count')}, audit_only={payload.get('audit_only_count')}"


def _check_provider_contract(client: TestClient) -> str:
    payload = _json(client, "/api/runtime/provider-contracts")
    providers = payload.get("providers") or {}
    _expect(isinstance(providers, dict), "providers must be a mapping")
    _expect(payload.get("default_provider"), "default provider missing")
    return f"default={payload.get('default_provider')}, providers={list(providers.keys())}"


def _check_long_running_health(client: TestClient) -> str:
    payload = _json(client, "/api/runtime/long-running-health")
    snapshot = payload.get("snapshot") or {}
    _expect("memory" in snapshot, "memory metrics missing")
    _expect("disk" in snapshot, "disk metrics missing")
    _expect("worker_isolation" in snapshot, "worker isolation metrics missing")
    _expect("langgraph_contract" in snapshot, "langgraph contract metrics missing")
    return (
        f"disk_free_gb={(snapshot.get('disk') or {}).get('free_gb')}, "
        f"queue={(snapshot.get('worker_isolation') or {}).get('total_queued')}, "
        f"checkpoints={(snapshot.get('langgraph_contract') or {}).get('checkpoint_count')}, "
        f"alerts={len(snapshot.get('alerts') or [])}"
    )


def _check_runtime_maintenance(client: TestClient) -> str:
    payload = _json(client, "/api/runtime/maintenance/status")
    _expect("interval_seconds" in payload, "maintenance interval missing")
    _expect("max_checkpoints_per_thread" in payload, "maintenance checkpoint cap missing")
    return f"running={payload.get('running')}, interval={payload.get('interval_seconds')}"


def _check_langgraph_contract(client: TestClient) -> str:
    payload = _json(client, "/api/runtime/langgraph-contract")
    _expect("threads" in payload, "contract state missing threads")
    remote = payload.get("remote_capabilities") or {}
    threads = remote.get("threads") if isinstance(remote, dict) else {}
    _expect(isinstance(threads, dict), "remote thread capabilities must be a mapping")
    return f"threads={len(payload.get('threads') or {})}, remote={threads}"


def _check_query_engine_maintenance(client: TestClient) -> str:
    payload = _json(client, "/api/query-engine/maintenance")
    _expect("session_count" in payload, "query maintenance snapshot missing session_count")
    _expect("budgets" in payload, "query maintenance snapshot missing budgets")
    return f"sessions={payload.get('session_count')}, turns={payload.get('turn_count')}"


def _check_workflow_langgraph_contract_smoke() -> str:
    import asyncio

    from scripts.run_workflow_langgraph_contract_smoke import run

    report = asyncio.run(run(require_remote=False))
    _expect(report.ok, "workflow LangGraph contract smoke failed")
    actions = [item["id"] for item in report.checks if str(item.get("id", "")).startswith("lifecycle-")]
    _expect(len(actions) == 5, f"missing lifecycle actions: {actions}")
    return f"remote_available={report.remote_available}, actions={actions}"


def _check_distributed_execution(client: TestClient) -> str:
    payload = _json(client, "/api/execution-nodes")
    _expect(isinstance(payload.get("nodes"), list), "execution nodes must be a list")
    route = client.post("/api/execution-nodes/route", json={"task_id": "doctor-smoke"})
    route.raise_for_status()
    route_payload = route.json()
    _expect("strategy" in route_payload, "routing response missing strategy")
    return f"nodes={payload.get('total')}, healthy={payload.get('healthy_count')}, route={route_payload.get('strategy')}"


def _check_multi_tenant(client: TestClient) -> str:
    payload = _json(client, "/api/tenants")
    _expect(isinstance(payload.get("tenants"), list), "tenants must be a list")
    governance = _json(client, "/api/tenants/governance")
    _expect("tenant_count" in governance, "tenant governance missing tenant_count")
    limit = client.get("/api/tenants/default/limits/workspaces", params={"current_count": 0})
    limit.raise_for_status()
    _expect("allowed" in limit.json(), "tenant limit response missing allowed")
    return f"tenants={payload.get('total')}, audit={len(governance.get('audit_events') or [])}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    parser.add_argument("--skip-git", action="store_true", help="Skip clean/synced git check.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    checks = _contract_checks(include_git=not args.skip_git)
    report = DoctorReport(ok=all(check.status == "ok" for check in checks), checks=checks)
    payload = asdict(report)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for check in checks:
            marker = "OK" if check.status == "ok" else "FAIL"
            print(f"[{marker}] {check.id} ({check.seconds}s) {check.detail or check.error or ''}")
        print(json.dumps({"ok": report.ok, "total": len(checks)}, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
