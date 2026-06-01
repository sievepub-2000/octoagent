"""Regression: startup orphan recovery dispatches each workspace at most once."""

from __future__ import annotations

import asyncio
import types

import src.gateway.routers.task_workspaces as task_workspaces_router
import src.storage.workflow as workflow_mod
from src.gateway import lifecycle


def test_orphan_recovery_dispatches_each_workspace_at_most_once(monkeypatch):
    lifecycle._ORPHAN_RECOVERY_RUNNER = None

    ws_a = types.SimpleNamespace(task_id="task-a")
    ws_b = types.SimpleNamespace(task_id="task-b")

    monkeypatch.setattr(workflow_mod, "recoverable_orphaned_workspaces", lambda: [ws_a, ws_b], raising=False)
    monkeypatch.setattr(workflow_mod, "TaskWorkflowModule", object, raising=False)

    async def _noop_exec(*args, **kwargs):
        return None

    monkeypatch.setattr(workflow_mod, "safe_auto_execute_workspace", _noop_exec, raising=False)
    monkeypatch.setattr(task_workspaces_router, "_merge_workspace_metadata", lambda *a, **k: None, raising=False)

    dispatched: list[str] = []

    def _fake_create_task(coro, *args, **kwargs):
        try:
            coro.close()
        except Exception:
            pass
        dispatched.append("x")
        return None

    monkeypatch.setattr(asyncio, "create_task", _fake_create_task)

    # First sweep dispatches both orphaned workspaces once each.
    lifecycle._recover_orphaned_task_workspaces()
    assert len(dispatched) == 2

    # Adversarial repeat sweep over the same set must not re-dispatch (at-most-once).
    lifecycle._recover_orphaned_task_workspaces()
    assert len(dispatched) == 2
