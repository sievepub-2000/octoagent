"""Smoke workflow/LangGraph thread-run-checkpoint lifecycle contracts."""

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
class ContractSmokeReport:
    ok: bool = True
    remote_available: bool = False
    thread_id: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def _remote_thread_id(base_url: str) -> tuple[str, bool, dict[str, Any]]:
    try:
        from langgraph_sdk import get_client

        client = get_client(url=base_url)
        thread = await client.threads.create()
        return str(thread["thread_id"]), True, {"thread": thread}
    except Exception as exc:
        return str(uuid.uuid4()), False, {"error": str(exc)}


async def run(*, require_remote: bool = False, base_url: str = "http://localhost:19884") -> ContractSmokeReport:
    from src.agents.runtime import get_langgraph_workflow_contract_service
    from src.gateway.app import app

    report = ContractSmokeReport()
    client = TestClient(app)
    contract = get_langgraph_workflow_contract_service()

    thread_id, remote_available, remote_create = await _remote_thread_id(base_url)
    report.thread_id = thread_id
    report.remote_available = remote_available
    report.checks.append({"id": "remote-thread-create", "remote_available": remote_available, "detail": remote_create})
    if require_remote:
        _expect(remote_available, f"LangGraph remote unavailable: {remote_create}")

    run_record = contract.start_run(
        task_id="workflow-contract-smoke",
        thread_id=thread_id,
        assistant_id="lead_agent",
        graph_id="smoke-graph",
        agent_id="smoke-agent",
        query_session_id=None,
        thread_scope="workspace",
    )
    contract.record_checkpoint(
        task_id="workflow-contract-smoke",
        thread_id=thread_id,
        checkpoint_id=f"checkpoint-{uuid.uuid4()}",
        label="Workflow contract smoke checkpoint",
        run_id=run_record.run_id,
        metadata={"source": "workflow-langgraph-contract-smoke"},
    )

    for action in ("pause", "resume", "cancel", "replay", "terminate"):
        response = client.post(
            f"/api/runtime/langgraph-contract/threads/{thread_id}/lifecycle",
            json={
                "action": action,
                "run_id": run_record.run_id,
                "actor": "contract-smoke",
                "reason": f"smoke-{action}",
                "remote": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
        _expect(payload.get("ok") is True, f"{action} lifecycle action failed: {payload}")
        report.checks.append({"id": f"lifecycle-{action}", "payload": payload})

    copy_response = client.post(
        "/api/runtime/langgraph-contract/copy",
        json={
            "source_thread_id": thread_id,
            "target_thread_id": f"{thread_id}-replay-copy",
            "target_task_id": "workflow-contract-smoke-copy",
            "remote": False,
        },
    )
    copy_response.raise_for_status()
    report.checks.append({"id": "local-replay-copy", "payload": copy_response.json()})

    prune_response = client.post(
        "/api/runtime/langgraph-contract/prune",
        json={
            "max_checkpoints_per_thread": 5,
            "max_runs_per_thread": 10,
            "remote_thread_ids": [thread_id] if remote_available and require_remote else [],
        },
    )
    prune_response.raise_for_status()
    report.checks.append({"id": "checkpoint-prune", "payload": prune_response.json()})

    for cleanup_thread_id in (f"{thread_id}-replay-copy", thread_id):
        delete_response = client.delete(f"/api/runtime/langgraph-contract/threads/{cleanup_thread_id}")
        delete_response.raise_for_status()
        report.checks.append({"id": "thread-cleanup", "payload": delete_response.json()})

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-remote", action="store_true")
    parser.add_argument("--base-url", default="http://localhost:19884")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        import asyncio

        report = asyncio.run(run(require_remote=args.require_remote, base_url=args.base_url))
    except Exception as exc:
        report = ContractSmokeReport(ok=False, checks=[{"id": "workflow-langgraph-contract-smoke", "error": str(exc)}])
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2 if args.json else None))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
