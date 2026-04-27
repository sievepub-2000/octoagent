"""Exercise a real LangGraph remote thread/run id through lifecycle controls."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass
class LangGraphRemoteLifecycleReport:
    ok: bool = True
    base_url: str = ""
    thread_id: str = ""
    run_id: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _extract_id(payload: Any, key: str) -> str:
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    value = getattr(payload, key, None)
    if isinstance(value, str) and value:
        return value
    return ""


async def run(*, base_url: str, assistant_id: str, require_cancel: bool = True) -> LangGraphRemoteLifecycleReport:
    from langgraph_sdk import get_client

    from src.agent_runtime import get_langgraph_workflow_contract_service
    from src.gateway.app import app

    report = LangGraphRemoteLifecycleReport(base_url=base_url)
    remote = get_client(url=base_url)
    gateway = TestClient(app)
    contract = get_langgraph_workflow_contract_service()

    thread = await remote.threads.create()
    thread_id = _extract_id(thread, "thread_id")
    _expect(bool(thread_id), f"remote thread id missing: {thread}")
    report.thread_id = thread_id
    report.checks.append({"id": "remote-thread-created", "thread": thread})

    created_run: Any = None
    run_error: str | None = None
    try:
        created_run = await remote.runs.create(
            thread_id,
            assistant_id,
            input={"messages": [{"role": "user", "content": "remote lifecycle smoke"}]},
        )
    except TypeError:
        try:
            created_run = await remote.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id,
                input={"messages": [{"role": "user", "content": "remote lifecycle smoke"}]},
            )
        except Exception as exc:
            run_error = str(exc)
    except Exception as exc:
        run_error = str(exc)

    run_id = _extract_id(created_run, "run_id")
    if not run_id and isinstance(created_run, dict):
        run_id = str(created_run.get("id") or "")
    if not run_id:
        report.ok = False
        report.checks.append({"id": "remote-run-created", "error": run_error or f"missing run id: {created_run}"})
        await remote.threads.delete(thread_id)
        return report
    report.run_id = run_id
    report.checks.append({"id": "remote-run-created", "run": created_run})

    local_run = contract.start_run(
        task_id="langgraph-remote-lifecycle-e2e",
        thread_id=thread_id,
        assistant_id=assistant_id,
        graph_id="remote-e2e",
        agent_id="lead",
        query_session_id=None,
        thread_scope="workspace",
    )
    local_run.run_id = run_id

    for action in ("pause", "resume"):
        response = gateway.post(
            f"/api/runtime/langgraph-contract/threads/{thread_id}/lifecycle",
            json={"action": action, "run_id": run_id, "actor": "remote-e2e", "reason": f"remote-e2e-{action}", "remote": True},
        )
        response.raise_for_status()
        report.checks.append({"id": f"remote-{action}", "payload": response.json()})

    cancel_response = gateway.post(
        f"/api/runtime/langgraph-contract/threads/{thread_id}/lifecycle",
        json={"action": "cancel", "run_id": run_id, "actor": "remote-e2e", "reason": "remote-e2e-cancel", "remote": True},
    )
    cancel_response.raise_for_status()
    cancel_payload = cancel_response.json()
    cancel_ok = bool((cancel_payload.get("remote") or {}).get("ok"))
    if require_cancel:
        _expect(cancel_ok, f"remote cancel failed: {cancel_payload}")
    contract.finish_run(thread_id=thread_id, run_id=run_id, status="cancelled")
    report.checks.append({"id": "remote-cancel", "payload": cancel_payload})

    replay_response = gateway.post(
        "/api/runtime/langgraph-contract/copy",
        json={"source_thread_id": thread_id, "target_thread_id": f"{thread_id}-local-replay", "target_task_id": "langgraph-remote-lifecycle-e2e-replay", "remote": True},
    )
    replay_response.raise_for_status()
    report.checks.append({"id": "remote-replay-copy", "payload": replay_response.json()})

    terminate_response = gateway.post(
        f"/api/runtime/langgraph-contract/threads/{thread_id}/lifecycle",
        json={"action": "terminate", "run_id": run_id, "actor": "remote-e2e", "reason": "remote-e2e-terminate", "remote": True},
    )
    terminate_response.raise_for_status()
    report.checks.append({"id": "remote-terminate", "payload": terminate_response.json()})

    delete_response = gateway.delete(f"/api/runtime/langgraph-contract/threads/{thread_id}")
    delete_response.raise_for_status()
    contract.delete_thread_contract(f"{thread_id}-local-replay")
    contract.delete_thread_contract(thread_id)
    report.checks.append({"id": "remote-thread-deleted", "payload": delete_response.json()})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:19884")
    parser.add_argument("--assistant-id", default="lead_agent")
    parser.add_argument("--allow-cancel-recovery", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = asyncio.run(
            run(
                base_url=args.base_url,
                assistant_id=args.assistant_id,
                require_cancel=not args.allow_cancel_recovery,
            )
        )
    except Exception as exc:
        report = LangGraphRemoteLifecycleReport(ok=False, base_url=args.base_url, checks=[{"id": "langgraph-remote-lifecycle-e2e", "error": str(exc)}])
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2 if args.json else None))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
