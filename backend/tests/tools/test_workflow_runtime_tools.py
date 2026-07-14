from __future__ import annotations

import json

from src.tools.builtins.task_tool import _extract_workplan_context
from src.tools.builtins.workflow_runtime_tools import _append_workplan_node, _upsert_workplan


class RuntimeStub:
    def __init__(self) -> None:
        self.context = {"thread_id": "thread-1"}
        self.state = {"runtime": {}}


def test_upsert_workplan_creates_and_updates_snapshot() -> None:
    runtime = RuntimeStub()

    created = _upsert_workplan(
        runtime,  # type: ignore[arg-type]
        {
            "workplan_id": "workplan-1",
            "run_id": "thread-1",
            "goal": "Ship it",
            "status": "running",
            "nodes": [],
        },
    )
    runtime.state["runtime"] = created
    updated = _upsert_workplan(
        runtime,  # type: ignore[arg-type]
        {
            "workplan_id": "workplan-1",
            "status": "completed",
            "last_checkpoint": {"title": "Done"},
        },
    )

    assert updated["active_workplan_id"] == "workplan-1"
    assert len(updated["workplans"]) == 1
    assert updated["workplans"][0]["goal"] == "Ship it"
    assert updated["workplans"][0]["status"] == "completed"
    assert updated["workplans"][0]["last_checkpoint"]["title"] == "Done"


def test_append_workplan_node_preserves_parent_snapshot() -> None:
    runtime = RuntimeStub()
    runtime.state["runtime"] = _upsert_workplan(
        runtime,  # type: ignore[arg-type]
        {
            "workplan_id": "workplan-1",
            "run_id": "thread-1",
            "goal": "Ship it",
            "status": "running",
            "nodes": [],
        },
    )

    updated = _append_workplan_node(
        runtime,  # type: ignore[arg-type]
        workplan_id="workplan-1",
        node={"node_id": "node-1", "kind": "subagent", "status": "planned"},
    )

    assert updated["workplans"][0]["workplan_id"] == "workplan-1"
    assert updated["workplans"][0]["nodes"][0]["node_id"] == "node-1"


def test_extract_workplan_context_from_spawn_prompt() -> None:
    workplan_id, node_id = _extract_workplan_context("WorkPlan: workplan-1\nNode: subagent-1\n\nDo the work")

    assert workplan_id == "workplan-1"
    assert node_id == "subagent-1"


def test_workplan_snapshot_is_json_serializable() -> None:
    runtime = RuntimeStub()
    snapshot = _append_workplan_node(
        runtime,  # type: ignore[arg-type]
        workplan_id="workplan-json",
        node={"node_id": "node-json", "kind": "subagent", "status": "planned"},
    )

    json.dumps(snapshot)
