"""Golden smoke for QueryEngine compaction, quality, replay, and tenant continuity."""

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
class QueryGoldenReport:
    ok: bool = True
    checks: list[dict[str, Any]] = field(default_factory=list)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> QueryGoldenReport:
    from src.gateway.app import app

    client = TestClient(app)
    report = QueryGoldenReport()
    tenant_id = f"query-golden-{uuid.uuid4().hex[:8]}"
    tenant = client.post("/api/tenants", json={"tenant_id": tenant_id, "display_name": "Query Golden", "tier": "pro"})
    tenant.raise_for_status()

    workspace_response = client.post(
        "/api/task-workspaces",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": "query golden", "goal": "validate long-session replay and semantic compression"},
    )
    workspace_response.raise_for_status()
    workspace = workspace_response.json()
    agent_id = workspace["agents"][0]["agent_id"]

    handoff = client.post(f"/api/task-workspaces/{workspace['task_id']}/agents/{agent_id}/handoff")
    handoff.raise_for_status()
    session = handoff.json()
    session_id = session["session_id"]
    _expect(session["metadata"]["tenant_id"] == tenant_id, "query session tenant metadata missing")
    report.checks.append({"id": "session-created", "session_id": session_id, "tenant_id": tenant_id})

    for index in range(12):
        turn = client.post(
            f"/api/query-engine/sessions/{session_id}/turns",
            json={
                "user_message": f"step {index}: preserve decision, blocker, and next action",
                "assistant_summary": f"Decision {index}: completed step; blocked items: none; next action: continue validation.",
                "tool_call_count": 1,
                "status": "completed",
            },
        )
        turn.raise_for_status()
    report.checks.append({"id": "turns-recorded", "count": 12})

    compact = client.post(f"/api/query-engine/sessions/{session_id}/compact", json={"retain_turns": 3, "title": "Golden Replay Summary"})
    compact.raise_for_status()
    compact_payload = compact.json()
    _expect(compact_payload["summaries"], "compaction did not create summary")
    report.checks.append({"id": "session-compacted", "summary_count": len(compact_payload["summaries"])})

    quality = client.post(f"/api/query-engine/sessions/{session_id}/summary-quality")
    quality.raise_for_status()
    quality_payload = quality.json()
    _expect(quality_payload["summary_count"] >= 1, "quality evaluator saw no summaries")
    _expect(quality_payload["evaluations"][0]["quality_score"] >= 0.6, f"summary quality degraded: {quality_payload}")
    report.checks.append({"id": "summary-quality", "payload": quality_payload})

    replay = client.get(f"/api/query-engine/sessions/{session_id}/replay-context")
    replay.raise_for_status()
    replay_payload = replay.json()
    _expect(replay_payload["tenant_id"] == tenant_id, "replay context lost tenant_id")
    _expect(replay_payload["latest_summary"], "replay context missing latest summary")
    _expect(replay_payload["summary_degradation_detected"] is False, "summary degradation was incorrectly flagged")
    report.checks.append({"id": "replay-context", "tenant_id": replay_payload["tenant_id"]})

    recovered = client.post(f"/api/query-engine/sessions/{session_id}/recover", json={"reason": "golden-cross-process-recovery"})
    recovered.raise_for_status()
    report.checks.append({"id": "stale-recovery", "status": recovered.json()["status"]})

    workspace_cleanup = client.delete(f"/api/task-workspaces/{workspace['task_id']}")
    tenant_cleanup = client.delete(f"/api/tenants/{tenant_id}")
    report.checks.append(
        {
            "id": "cleanup",
            "workspace_status": workspace_cleanup.status_code,
            "tenant_status": tenant_cleanup.status_code,
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
        report = QueryGoldenReport(ok=False, checks=[{"id": "query-engine-replay-golden", "error": str(exc)}])
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2 if args.json else None))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
