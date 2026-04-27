"""Smoke distributed execution dispatch, remote worker callback, and failover."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass
class DispatchSmokeReport:
    ok: bool = True
    remote_url: str | None = None
    checks: list[dict[str, Any]] = field(default_factory=list)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_local_contract() -> DispatchSmokeReport:
    from src.gateway.app import app

    report = DispatchSmokeReport()
    client = TestClient(app)
    response = client.post(
        "/api/execution-nodes/dispatch",
        json={"task_id": "distributed-smoke-local", "payload": {"mode": "local"}},
    )
    response.raise_for_status()
    payload = response.json()
    _expect(payload["status"] == "completed", f"local dispatch failed: {payload}")
    report.checks.append({"id": "local-dispatch", "payload": payload})
    return report


def run_remote_contract(gateway_url: str) -> DispatchSmokeReport:
    report = DispatchSmokeReport(remote_url=gateway_url)
    node_id = f"remote-smoke-{uuid.uuid4().hex[:8]}"
    token = f"token-{uuid.uuid4().hex}"
    port = 19982
    worker = subprocess.Popen(
        [
            sys.executable,
            str(BACKEND_ROOT / "scripts" / "run_execution_worker.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--node-id",
            node_id,
            "--token",
            token,
            "--capacity",
            "2",
        ],
        cwd=BACKEND_ROOT,
        env={**os.environ, "PYTHONPATH": str(BACKEND_ROOT)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with httpx.Client(base_url=gateway_url.rstrip("/"), timeout=15) as client:
        try:
            for _ in range(30):
                try:
                    health = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
                    if health.status_code == 200:
                        break
                except Exception:
                    pass
                time.sleep(0.2)
            registered = client.post(
                "/api/execution-nodes",
                json={
                    "node_id": node_id,
                    "address": f"http://127.0.0.1:{port}",
                    "capacity": 2,
                    "tags": ["smoke", "remote-worker-daemon"],
                    "metadata": {
                        "dispatch_token": token,
                        "callback_token": token,
                    },
                },
            )
            registered.raise_for_status()
            report.checks.append({"id": "remote-node-registered", "node_id": node_id})

            dispatched = client.post(
                "/api/execution-nodes/dispatch",
                json={
                    "task_id": "distributed-smoke-remote",
                    "payload": {"mode": "remote-worker-daemon", "node_id": node_id},
                    "affinity_node": node_id,
                    "timeout_seconds": 15,
                    "callback_url": gateway_url.rstrip("/"),
                },
            )
            dispatched.raise_for_status()
            payload = dispatched.json()
            _expect(payload["status"] == "completed", f"remote dispatch failed: {payload}")
            _expect(payload["target_node_id"] == node_id, f"dispatch did not use remote node: {payload}")
            _expect(payload.get("lease_id"), f"dispatch lease missing: {payload}")
            report.checks.append({"id": "remote-worker-dispatch", "payload": payload})

            history = client.get("/api/execution-nodes/history/dispatches")
            history.raise_for_status()
            _expect(any(item["dispatch_id"] == payload["dispatch_id"] for item in history.json()), "dispatch history missing")
            report.checks.append({"id": "dispatch-history", "count": len(history.json())})

            replay = client.post(
                f"/api/execution-nodes/dispatches/{payload['dispatch_id']}/replay",
                json={"confirmation": "CONFIRM REPLAY DISPATCH", "timeout_seconds": 15},
            )
            replay.raise_for_status()
            report.checks.append({"id": "failover-replay", "payload": replay.json()})

            cleanup = client.delete(f"/api/execution-nodes/{node_id}")
            cleanup.raise_for_status()
            report.checks.append({"id": "remote-node-cleaned", "node_id": node_id})
        finally:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-url", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = run_remote_contract(args.gateway_url) if args.gateway_url else run_local_contract()
    except Exception as exc:
        report = DispatchSmokeReport(ok=False, remote_url=args.gateway_url or None, checks=[{"id": "distributed-dispatch-smoke", "error": str(exc)}])
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2 if args.json else None))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
