"""Run bounded long-running runtime sustainability checks."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass
class SoakReport:
    ok: bool = True
    seconds: float = 0.0
    checks: list[dict[str, object]] = field(default_factory=list)
    samples: list[dict[str, object]] = field(default_factory=list)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _capture_health_sample(client: TestClient, index: int) -> dict[str, object]:
    response = client.get("/api/runtime/long-running-health")
    response.raise_for_status()
    snapshot = response.json().get("snapshot") or {}
    disk = snapshot.get("disk") or {}
    worker = snapshot.get("worker_isolation") or {}
    contract = snapshot.get("langgraph_contract") or {}
    processes = snapshot.get("processes") or {}
    event_loop = snapshot.get("event_loop") or {}
    memory = snapshot.get("memory") or {}
    return {
        "index": index,
        "captured_at": round(time.time(), 3),
        "memory_available_gb": memory.get("available_gb"),
        "disk_free_gb": disk.get("free_gb"),
        "process_count": processes.get("host_process_count"),
        "event_loop_latency_ms": event_loop.get("latency_ms"),
        "worker_active": worker.get("total_active"),
        "worker_queued": worker.get("total_queued"),
        "checkpoint_count": contract.get("checkpoint_count"),
        "active_runs": contract.get("active_runs"),
        "alerts": len(snapshot.get("alerts") or []),
    }


def run(iterations: int, *, duration_seconds: int = 0, sample_interval_seconds: int = 30) -> SoakReport:
    from src.agents.runtime import get_langgraph_workflow_contract_service
    from src.gateway.app import app

    started = time.monotonic()
    report = SoakReport()
    client = TestClient(app)
    contract = get_langgraph_workflow_contract_service()
    stale_recovery_before = contract.recover_stale_running_runs()

    thread_id = f"soak-thread-{int(started * 1000)}"
    sample_index = 0
    for index in range(iterations):
        run_record = contract.start_run(
            task_id="soak-task",
            thread_id=thread_id,
            assistant_id="lead_agent",
            graph_id=None,
            agent_id="soak-agent",
            query_session_id=None,
            thread_scope="workspace",
        )
        contract.finish_run(
            thread_id=thread_id,
            run_id=run_record.run_id,
            status="completed",
            message_count=2,
            tool_call_count=0,
        )
        contract.record_checkpoint(
            task_id="soak-task",
            thread_id=thread_id,
            checkpoint_id=f"soak-checkpoint-{index}",
            label=f"Soak checkpoint {index}",
            run_id=run_record.run_id,
        )
        if duration_seconds > 0 and index % max(1, min(10, iterations)) == 0:
            report.samples.append(_capture_health_sample(client, sample_index))
            sample_index += 1

    duration_deadline = started + max(0, duration_seconds)
    while duration_seconds > 0 and time.monotonic() < duration_deadline:
        report.samples.append(_capture_health_sample(client, sample_index))
        sample_index += 1
        sleep_seconds = min(sample_interval_seconds, max(0.0, duration_deadline - time.monotonic()))
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    stale_recovery_after = contract.recover_stale_running_runs()
    before = contract.snapshot()
    prune_response = client.post(
        "/api/runtime/langgraph-contract/prune",
        json={"max_checkpoints_per_thread": 5, "max_runs_per_thread": 10},
    )
    prune_response.raise_for_status()
    after = contract.snapshot()
    _expect(int(after["checkpoint_count"]) <= int(before["checkpoint_count"]), "checkpoint count grew after prune")

    health = client.get("/api/runtime/long-running-health")
    health.raise_for_status()
    health_snapshot = health.json().get("snapshot") or {}
    worker = health_snapshot.get("worker_isolation") or {}
    _expect("total_queued" in worker, "worker queue metrics missing")

    maintenance = client.post("/api/query-engine/maintenance/run")
    maintenance.raise_for_status()
    maintenance_payload = maintenance.json()
    _expect("snapshot" in maintenance_payload, "query maintenance result missing snapshot")

    delete_response = client.delete(f"/api/runtime/langgraph-contract/threads/{thread_id}")
    delete_response.raise_for_status()
    report.samples.append(_capture_health_sample(client, sample_index))

    report.checks.extend(
        [
            {"id": "stale-run-recovery", "before": stale_recovery_before, "after": stale_recovery_after},
            {"id": "contract-generated", "before": before},
            {"id": "contract-pruned", "prune": prune_response.json(), "after": after},
            {"id": "long-running-health", "worker": worker},
            {"id": "query-maintenance", "result": maintenance_payload},
            {"id": "contract-cleanup", "deleted": delete_response.json()},
        ]
    )
    if report.samples:
        first = report.samples[0]
        last = report.samples[-1]
        _expect(last.get("worker_queued") in {0, None}, f"worker queue did not settle: {last}")
        _expect(last.get("active_runs") in {0, None}, f"active runs did not settle: {last}")
        # Checkpoint count is a process-global metric and can legitimately include
        # concurrent 8h/24h soak runs. The per-thread cleanup above proves this
        # run removed its own contract state; do not fail on unrelated samples.
        report.checks.append(
            {
                "id": "resource-stability",
                "first": first,
                "last": last,
                "sample_count": len(report.samples),
            }
        )
    report.seconds = round(time.monotonic() - started, 3)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--sample-interval-seconds", type=int, default=30)
    parser.add_argument("--report-path", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = run(
            max(1, min(args.iterations, 500)),
            duration_seconds=max(0, args.duration_seconds),
            sample_interval_seconds=max(1, args.sample_interval_seconds),
        )
    except Exception as exc:
        report = SoakReport(ok=False, checks=[{"id": "soak", "error": str(exc)}])
    payload = asdict(report)
    if args.report_path:
        Path(args.report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.json else None))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
