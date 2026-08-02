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


def _json(client: TestClient, path: str, *, headers: dict[str, str] | None = None) -> Any:
    response = client.get(path, headers=headers)
    response.raise_for_status()
    return response.json()


def _operator_headers(*, role: str = "admin") -> dict[str, str]:
    """Use the configured operator credential for guarded doctor probes."""
    import os

    token = os.getenv("OCTO_OPERATOR_TOKEN", "").strip()
    if not token:
        raise RuntimeError("OCTO_OPERATOR_TOKEN is required for guarded doctor probes")
    return {
        "X-OctoAgent-Operator-Token": token,
        "X-OctoAgent-Operator-Role": role,
    }


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
    checks.append(_timed("harness-api", lambda: _check_harness(client)))
    checks.append(_timed("agent-runtime-api", lambda: _check_agent_runtime(client)))
    checks.append(_timed("channels-api", lambda: _check_channels(client)))
    checks.append(_timed("models-api", lambda: _check_models(client)))
    checks.append(_timed("runtime-long-running-health-api", lambda: _check_long_running_health(client)))
    checks.append(_timed("runtime-maintenance-api", lambda: _check_runtime_maintenance(client)))
    return checks


def _check_health(client: TestClient) -> str:
    payload = _json(client, "/health")
    _expect(payload.get("status") == "healthy", f"unexpected health payload: {payload}")
    return "status=healthy"


def _check_runtime_doctor(client: TestClient) -> str:
    payload = _json(client, "/api/runtime/doctor")
    checks = payload.get("checks") or []
    ids = {item.get("id") for item in checks if isinstance(item, dict)}
    required = {"config", "models", "capability-registry", "channels", "langgraph-state"}
    missing = sorted(required - ids)
    _expect(not missing, f"runtime doctor missing checks: {missing}")
    _expect(payload.get("overall_status") in {"ok", "warn", "fail"}, f"invalid doctor status: {payload}")
    return f"overall={payload.get('overall_status')}, checks={len(checks)}"


def _check_harness(client: TestClient) -> str:
    payload = _json(client, "/api/harness")
    summary = payload.get("summary") or {}
    total = sum(int(value or 0) for key, value in summary.items() if key.endswith("_total"))
    _expect(total > 0, "Harness capability inventory is empty")
    _expect(isinstance(payload.get("memory"), dict), "Harness memory status missing")
    return f"capabilities={total}, skills={summary.get('skills_total')}, builtins={summary.get('builtin_tools_total')}"


def _check_agent_runtime(client: TestClient) -> str:
    payload = _json(client, "/api/agent-runtime")
    _expect(isinstance(payload, dict), "Agent Runtime snapshot must be an object")
    return f"keys={sorted(payload)[:8]}"


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


def _check_long_running_health(client: TestClient) -> str:
    payload = _json(client, "/api/runtime/long-running-health")
    snapshot = payload.get("snapshot") or {}
    _expect("memory" in snapshot, "memory metrics missing")
    _expect("disk" in snapshot, "disk metrics missing")
    _expect("worker_isolation" in snapshot, "worker isolation metrics missing")
    _expect("langgraph_state" in snapshot, "LangGraph PostgreSQL state metrics missing")
    return (
        f"disk_free_gb={(snapshot.get('disk') or {}).get('free_gb')}, "
        f"queue={(snapshot.get('worker_isolation') or {}).get('total_queued')}, "
        f"checkpoints={(snapshot.get('langgraph_state') or {}).get('checkpoint_count')}, "
        f"alerts={len(snapshot.get('alerts') or [])}"
    )


def _check_runtime_maintenance(client: TestClient) -> str:
    payload = _json(client, "/api/runtime/maintenance/status")
    _expect("interval_seconds" in payload, "maintenance interval missing")
    return f"running={payload.get('running')}, interval={payload.get('interval_seconds')}"


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
