"""Auditable LangGraph thread/run/checkpoint contract ledger."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.runtime.config.paths import get_paths
from src.governance.operator import signed_audit_event
from src.utils.json_atomic import write_json_atomic
from src.utils.datetime import utc_now_iso as _utc_now

RunStatus = Literal["running", "completed", "failed", "timeout", "cancelled"]
WorkflowLifecycleAction = Literal["pause", "resume", "cancel", "replay", "terminate"]




def _contract_path() -> Path:
    return get_paths().runtime_root / "langgraph_workflow_contracts.json"


def _langgraph_base_url() -> str:
    return os.getenv("OCTO_LANGGRAPH_BASE_URL", "http://localhost:19804")


def _is_langgraph_remote_thread_id(thread_id: str) -> bool:
    try:
        UUID(thread_id)
    except ValueError:
        return False
    return True


class LangGraphRunRecord(BaseModel):
    run_id: str
    task_id: str
    agent_id: str | None = None
    query_session_id: str | None = None
    thread_id: str
    assistant_id: str
    graph_id: str | None = None
    status: RunStatus = "running"
    started_at: str
    completed_at: str | None = None
    message_count: int = 0
    tool_call_count: int = 0
    error: str | None = None


class LangGraphCheckpointRecord(BaseModel):
    checkpoint_id: str
    task_id: str
    thread_id: str
    run_id: str | None = None
    label: str = ""
    source: str = "octoagent"
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class LangGraphThreadContract(BaseModel):
    thread_id: str
    task_id: str
    agent_id: str | None = None
    assistant_id: str = "lead_agent"
    graph_id: str | None = None
    thread_scope: str = "workspace"
    created_at: str
    updated_at: str
    runs: list[LangGraphRunRecord] = Field(default_factory=list)
    checkpoints: list[LangGraphCheckpointRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LangGraphWorkflowContractState(BaseModel):
    version: str = "langgraph-workflow-contract-v1"
    updated_at: str = Field(default_factory=_utc_now)
    threads: dict[str, LangGraphThreadContract] = Field(default_factory=dict)
    audit_events: list[dict[str, Any]] = Field(default_factory=list)


class LangGraphWorkflowContractService:
    """Owns OctoAgent-side thread/run/checkpoint lifecycle semantics."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _contract_path()
        self._lock = RLock()
        self._state: LangGraphWorkflowContractState | None = None

    def _load(self) -> LangGraphWorkflowContractState:
        if self._state is not None:
            return self._state
        if not self._path.exists():
            self._state = LangGraphWorkflowContractState()
            return self._state
        self._state = LangGraphWorkflowContractState.model_validate_json(self._path.read_text(encoding="utf-8"))
        return self._state

    def _save(self) -> None:
        state = self._load()
        state.updated_at = _utc_now()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self._path, state.model_dump(mode="json"))

    def _audit(self, event: str, **details: Any) -> None:
        state = self._load()
        state.audit_events.insert(
            0,
            signed_audit_event(event, **details),
        )
        del state.audit_events[200:]

    def register_thread(
        self,
        *,
        task_id: str,
        thread_id: str,
        agent_id: str | None,
        assistant_id: str,
        graph_id: str | None,
        thread_scope: str,
        metadata: dict[str, Any] | None = None,
    ) -> LangGraphThreadContract:
        with self._lock:
            state = self._load()
            existing = state.threads.get(thread_id)
            now = _utc_now()
            if existing is None:
                existing = LangGraphThreadContract(
                    thread_id=thread_id,
                    task_id=task_id,
                    agent_id=agent_id,
                    assistant_id=assistant_id,
                    graph_id=graph_id,
                    thread_scope=thread_scope,
                    created_at=now,
                    updated_at=now,
                    metadata=dict(metadata or {}),
                )
                state.threads[thread_id] = existing
                self._audit("langgraph_thread.registered", task_id=task_id, thread_id=thread_id)
            else:
                existing.task_id = task_id
                existing.agent_id = agent_id or existing.agent_id
                existing.assistant_id = assistant_id or existing.assistant_id
                existing.graph_id = graph_id or existing.graph_id
                existing.thread_scope = thread_scope or existing.thread_scope
                existing.metadata.update(metadata or {})
                existing.updated_at = now
            self._save()
            return existing

    def start_run(
        self,
        *,
        task_id: str,
        thread_id: str,
        assistant_id: str,
        graph_id: str | None,
        agent_id: str | None,
        query_session_id: str | None,
        thread_scope: str,
    ) -> LangGraphRunRecord:
        with self._lock:
            thread = self.register_thread(
                task_id=task_id,
                thread_id=thread_id,
                agent_id=agent_id,
                assistant_id=assistant_id,
                graph_id=graph_id,
                thread_scope=thread_scope,
                metadata={"last_query_session_id": query_session_id},
            )
            run = LangGraphRunRecord(
                run_id=f"lg-run-{uuid4()}",
                task_id=task_id,
                agent_id=agent_id,
                query_session_id=query_session_id,
                thread_id=thread_id,
                assistant_id=assistant_id,
                graph_id=graph_id,
                started_at=_utc_now(),
            )
            thread.runs.insert(0, run)
            thread.updated_at = run.started_at
            self._audit(
                "langgraph_run.started",
                task_id=task_id,
                thread_id=thread_id,
                run_id=run.run_id,
            )
            self._save()
            return run

    def finish_run(
        self,
        *,
        thread_id: str,
        run_id: str,
        status: RunStatus,
        message_count: int = 0,
        tool_call_count: int = 0,
        error: str | None = None,
    ) -> None:
        with self._lock:
            state = self._load()
            thread = state.threads.get(thread_id)
            if thread is None:
                return
            for run in thread.runs:
                if run.run_id != run_id:
                    continue
                run.status = status
                run.completed_at = _utc_now()
                run.message_count = message_count
                run.tool_call_count = tool_call_count
                run.error = error
                thread.updated_at = run.completed_at
                self._audit(
                    "langgraph_run.finished",
                    task_id=run.task_id,
                    thread_id=thread_id,
                    run_id=run_id,
                    status=status,
                )
                break
            self._save()

    def record_checkpoint(
        self,
        *,
        task_id: str,
        thread_id: str | None,
        checkpoint_id: str,
        label: str,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not thread_id:
            return
        with self._lock:
            thread = self._load().threads.get(thread_id)
            if thread is None:
                thread = self.register_thread(
                    task_id=task_id,
                    thread_id=thread_id,
                    agent_id=None,
                    assistant_id="lead_agent",
                    graph_id=None,
                    thread_scope="workspace",
                )
            if any(item.checkpoint_id == checkpoint_id for item in thread.checkpoints):
                return
            checkpoint = LangGraphCheckpointRecord(
                checkpoint_id=checkpoint_id,
                task_id=task_id,
                thread_id=thread_id,
                run_id=run_id,
                label=label,
                created_at=_utc_now(),
                metadata=dict(metadata or {}),
            )
            thread.checkpoints.insert(0, checkpoint)
            thread.updated_at = checkpoint.created_at
            self._audit(
                "langgraph_checkpoint.recorded",
                task_id=task_id,
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
            )
            self._save()

    def prune(
        self,
        *,
        max_checkpoints_per_thread: int = 20,
        max_runs_per_thread: int = 100,
    ) -> dict[str, int]:
        with self._lock:
            pruned_checkpoints = 0
            pruned_runs = 0
            for thread in self._load().threads.values():
                if len(thread.checkpoints) > max_checkpoints_per_thread:
                    pruned_checkpoints += len(thread.checkpoints) - max_checkpoints_per_thread
                    thread.checkpoints = thread.checkpoints[:max_checkpoints_per_thread]
                if len(thread.runs) > max_runs_per_thread:
                    pruned_runs += len(thread.runs) - max_runs_per_thread
                    thread.runs = thread.runs[:max_runs_per_thread]
            self._audit(
                "langgraph_contract.pruned",
                pruned_checkpoints=pruned_checkpoints,
                pruned_runs=pruned_runs,
                max_checkpoints_per_thread=max_checkpoints_per_thread,
                max_runs_per_thread=max_runs_per_thread,
            )
            self._save()
            return {
                "pruned_checkpoints": pruned_checkpoints,
                "pruned_runs": pruned_runs,
            }

    def recover_stale_running_runs(self, *, max_age_seconds: int = 3600) -> dict[str, int]:
        """Mark long-running local contract records as timed out.

        This only mutates OctoAgent's contract ledger. It prevents abandoned
        local bookkeeping rows from blocking long-running health/soak checks
        after the backing LangGraph run has already disappeared or stalled.
        """
        with self._lock:
            state = self._load()
            now_dt = datetime.now(UTC)
            threshold = now_dt - timedelta(seconds=max(60, max_age_seconds))
            recovered = 0
            touched_threads = 0
            completed_at = now_dt.isoformat()
            for thread in state.threads.values():
                thread_touched = False
                for run in thread.runs:
                    if run.status != "running":
                        continue
                    try:
                        started_at = datetime.fromisoformat(run.started_at.replace("Z", "+00:00"))
                    except ValueError:
                        started_at = threshold - timedelta(seconds=1)
                    if started_at > threshold:
                        continue
                    run.status = "timeout"
                    run.completed_at = completed_at
                    run.error = run.error or "stale_running_run_recovered_by_maintenance"
                    recovered += 1
                    thread_touched = True
                    self._audit(
                        "langgraph_run.stale_recovered",
                        task_id=run.task_id,
                        thread_id=thread.thread_id,
                        run_id=run.run_id,
                        max_age_seconds=max_age_seconds,
                    )
                if thread_touched:
                    touched_threads += 1
                    thread.updated_at = completed_at
            if recovered:
                self._save()
            return {"recovered_runs": recovered, "touched_threads": touched_threads}

    def copy_thread_contract(
        self,
        source_thread_id: str,
        target_thread_id: str,
        *,
        target_task_id: str | None = None,
    ) -> LangGraphThreadContract | None:
        with self._lock:
            state = self._load()
            source = state.threads.get(source_thread_id)
            if source is None:
                return None
            copied = source.model_copy(deep=True)
            copied.thread_id = target_thread_id
            copied.task_id = target_task_id or source.task_id
            copied.created_at = _utc_now()
            copied.updated_at = copied.created_at
            copied.metadata["copied_from_thread_id"] = source_thread_id
            state.threads[target_thread_id] = copied
            self._audit(
                "langgraph_thread.copied",
                source_thread_id=source_thread_id,
                target_thread_id=target_thread_id,
            )
            self._save()
            return copied

    def delete_thread_contract(self, thread_id: str) -> bool:
        with self._lock:
            state = self._load()
            removed = state.threads.pop(thread_id, None)
            if removed is None:
                return False
            self._audit("langgraph_thread.deleted", task_id=removed.task_id, thread_id=thread_id)
            self._save()
            return True

    async def remote_capabilities(self) -> dict[str, Any]:
        from langgraph_sdk import get_client

        client = get_client(url=_langgraph_base_url())
        return {
            "base_url": _langgraph_base_url(),
            "threads": {
                "copy": callable(getattr(client.threads, "copy", None)),
                "delete": callable(getattr(client.threads, "delete", None)),
                "prune": callable(getattr(client.threads, "prune", None)),
                "get_state": callable(getattr(client.threads, "get_state", None)),
                "get_history": callable(getattr(client.threads, "get_history", None)),
            },
            "runs": {
                "cancel": callable(getattr(client.runs, "cancel", None)),
                "delete": callable(getattr(client.runs, "delete", None)),
                "list": callable(getattr(client.runs, "list", None)),
            },
        }

    async def prune_remote_threads(
        self,
        thread_ids: list[str],
        *,
        strategy: str = "delete",
    ) -> dict[str, Any]:
        remote_thread_ids = [thread_id for thread_id in thread_ids if _is_langgraph_remote_thread_id(thread_id)]
        remote_thread_id_set = set(remote_thread_ids)
        skipped_thread_ids = [thread_id for thread_id in thread_ids if thread_id not in remote_thread_id_set]
        if not remote_thread_ids:
            return {
                "ok": True,
                "thread_ids": [],
                "skipped_thread_ids": skipped_thread_ids,
                "result": {},
            }
        from langgraph_sdk import get_client

        client = get_client(url=_langgraph_base_url())
        result = await client.threads.prune(remote_thread_ids, strategy=strategy)
        self._audit(
            "langgraph_remote.pruned",
            thread_ids=remote_thread_ids,
            skipped_thread_ids=skipped_thread_ids,
            strategy=strategy,
            result=result,
        )
        self._save()
        return {
            "ok": True,
            "thread_ids": remote_thread_ids,
            "skipped_thread_ids": skipped_thread_ids,
            "result": result,
        }

    async def copy_remote_thread(self, thread_id: str) -> dict[str, Any]:
        if not _is_langgraph_remote_thread_id(thread_id):
            return {
                "ok": True,
                "skipped": True,
                "thread_id": thread_id,
                "reason": "non_uuid_thread_id",
            }
        from langgraph_sdk import get_client

        client = get_client(url=_langgraph_base_url())
        result = await client.threads.copy(thread_id)
        self._audit("langgraph_remote.thread_copied", thread_id=thread_id, result=result)
        self._save()
        return {"ok": True, "thread_id": thread_id, "result": result}

    async def delete_remote_thread(self, thread_id: str) -> dict[str, Any]:
        if not _is_langgraph_remote_thread_id(thread_id):
            return {
                "ok": True,
                "skipped": True,
                "thread_id": thread_id,
                "reason": "non_uuid_thread_id",
            }
        from langgraph_sdk import get_client

        client = get_client(url=_langgraph_base_url())
        result = await client.threads.delete(thread_id)
        self._audit("langgraph_remote.thread_deleted", thread_id=thread_id, result=result)
        self._save()
        return {"ok": True, "thread_id": thread_id, "result": result}

    def record_lifecycle_action(
        self,
        *,
        thread_id: str,
        action: WorkflowLifecycleAction,
        run_id: str | None = None,
        actor: str = "operator",
        reason: str = "",
        remote: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._load()
            thread = state.threads.get(thread_id)
            if thread is None:
                return {"ok": False, "error": "thread_not_found", "thread_id": thread_id}
            now = _utc_now()
            thread.metadata["last_lifecycle_action"] = action
            thread.metadata["last_lifecycle_action_at"] = now
            thread.metadata["last_lifecycle_actor"] = actor
            if reason:
                thread.metadata["last_lifecycle_reason"] = reason
            if action in {"cancel", "terminate"}:
                for run in thread.runs:
                    if run_id is not None and run.run_id != run_id:
                        continue
                    if run.status == "running":
                        run.status = "cancelled"
                        run.completed_at = now
                    if run_id is not None:
                        break
            if action == "replay":
                thread.metadata["replay_requested_at"] = now
            thread.updated_at = now
            self._audit(
                "langgraph_workflow.lifecycle",
                thread_id=thread_id,
                run_id=run_id,
                action=action,
                actor=actor,
                reason=reason,
                remote=remote or {},
            )
            self._save()
            return {
                "ok": True,
                "thread_id": thread_id,
                "run_id": run_id,
                "action": action,
                "remote": remote,
                "updated_at": now,
            }

    def snapshot(self) -> dict[str, Any]:
        state = self._load()
        active_runs = 0
        failed_runs = 0
        checkpoint_count = 0
        task_ids: set[str] = set()
        for thread in state.threads.values():
            task_ids.add(thread.task_id)
            checkpoint_count += len(thread.checkpoints)
            for run in thread.runs:
                if run.status == "running":
                    active_runs += 1
                if run.status in {"failed", "timeout"}:
                    failed_runs += 1
        return {
            "path": str(self._path),
            "thread_count": len(state.threads),
            "task_count": len(task_ids),
            "checkpoint_count": checkpoint_count,
            "active_runs": active_runs,
            "failed_runs": failed_runs,
            "audit_event_count": len(state.audit_events),
            "updated_at": state.updated_at,
        }

    def export_state(self) -> dict[str, Any]:
        return self._load().model_dump(mode="json") | {"path": str(self._path)}

    def contract_for_task(self, task_id: str) -> dict[str, Any]:
        state = self._load()
        threads = [thread.model_dump(mode="json") for thread in state.threads.values() if thread.task_id == task_id]
        return {
            "task_id": task_id,
            "threads": threads,
            "summary": {
                "thread_count": len(threads),
                "checkpoint_count": sum(len(thread["checkpoints"]) for thread in threads),
                "run_count": sum(len(thread["runs"]) for thread in threads),
            },
        }


_contract_service: LangGraphWorkflowContractService | None = None


def get_langgraph_workflow_contract_service() -> LangGraphWorkflowContractService:
    global _contract_service
    if _contract_service is None:
        _contract_service = LangGraphWorkflowContractService()
    return _contract_service
