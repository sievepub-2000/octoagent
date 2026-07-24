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
    langgraph_state = snapshot.get("langgraph_state") or {}
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
        "checkpoint_count": langgraph_state.get("checkpoint_count"),
        "alerts": len(snapshot.get("alerts") or []),
    }


def run(iterations: int, *, duration_seconds: int = 0, sample_interval_seconds: int = 30) -> SoakReport:
    from src.gateway.app import app

    started = time.monotonic()
    report = SoakReport()
    with TestClient(app) as client:
        sample_index = 0
        for _ in range(iterations):
            report.samples.append(_capture_health_sample(client, sample_index))
            sample_index += 1

        duration_deadline = started + max(0, duration_seconds)
        while duration_seconds > 0 and time.monotonic() < duration_deadline:
            report.samples.append(_capture_health_sample(client, sample_index))
            sample_index += 1
            sleep_seconds = min(sample_interval_seconds, max(0.0, duration_deadline - time.monotonic()))
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        maintenance = client.post("/api/runtime/maintenance/run")
        maintenance.raise_for_status()
        report.checks.append({"id": "artifact-maintenance", "result": maintenance.json()})

    if report.samples:
        first = report.samples[0]
        last = report.samples[-1]
        _expect(last.get("worker_queued") in {0, None}, f"worker queue did not settle: {last}")
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
