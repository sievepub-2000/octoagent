"""First-class workflow runtime tools for the lead agent.

These tools intentionally expose a small runtime interface over the existing
workflow/subagent implementation.  They do not replace the LangGraph state
machine; they give the lead agent deterministic verbs for creating a WorkPlan,
attaching subagent dispatches to it, and streaming a unified timeline to the
WebUI.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from langchain.tools import ToolRuntime, tool
from langgraph.config import get_stream_writer
from langgraph.typing import ContextT

from src.agents.subagents.catalog import get_subagent_names
from src.agents.thread_state import ThreadState


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _run_id(runtime: ToolRuntime[ContextT, ThreadState] | None) -> str:
    if runtime is None:
        return f"run-{uuid.uuid4().hex[:10]}"
    context = runtime.context or {}
    state_runtime = (runtime.state.get("runtime") or {}) if runtime.state else {}
    for value in (
        context.get("thread_id"),
        state_runtime.get("planned_operation_id"),
        state_runtime.get("context_cycle_id"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"run-{uuid.uuid4().hex[:10]}"


def _emit_run_event(
    *,
    kind: str,
    title: str,
    detail: str | None = None,
    level: str = "info",
    run_id: str | None = None,
    node_id: str | None = None,
    task_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    try:
        writer = get_stream_writer()
    except Exception:
        return
    writer(
        {
            "type": "run_event",
            "event": {
                "id": f"run-event-{uuid.uuid4().hex[:12]}",
                "kind": kind,
                "title": title,
                "detail": detail,
                "level": level,
                "created_at": _utc_now(),
                "run_id": run_id,
                "node_id": node_id,
                "task_id": task_id,
                "payload": payload or {},
            },
        }
    )


@tool("workflow_start", parse_docstring=True)
def workflow_start_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    goal: str,
    workflow_id: str | None = None,
    mode: str = "workplan",
) -> str:
    """Start a first-class WorkPlan for the current user task.

    Use this before a complex task that benefits from explicit workflow
    tracking.  The returned WorkPlan ID should be referenced by subsequent
    ``spawn_subagent`` and ``checkpoint`` calls.

    Args:
        goal: The user-visible outcome the workflow is driving toward.
        workflow_id: Optional stable ID when resuming an existing workflow.
        mode: Execution mode hint such as workplan, branch, group, or task.
    """

    run_id = _run_id(runtime)
    workplan_id = workflow_id.strip() if isinstance(workflow_id, str) and workflow_id.strip() else f"workplan-{uuid.uuid4().hex[:10]}"
    _emit_run_event(
        kind="workflow",
        title="Workflow started",
        detail=goal.strip()[:240],
        run_id=run_id,
        node_id=workplan_id,
        payload={"workflow_id": workplan_id, "mode": mode},
    )
    return _json(
        {
            "status": "started",
            "workplan_id": workplan_id,
            "run_id": run_id,
            "goal": goal,
            "mode": mode,
            "next_tools": ["spawn_subagent", "checkpoint", "workflow_status"],
        }
    )


@tool("workflow_status", parse_docstring=True)
def workflow_status_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    workplan_id: str | None = None,
) -> str:
    """Return the current workflow/subagent runtime status for this thread.

    Args:
        workplan_id: Optional WorkPlan ID to attach to the emitted status event.
    """

    run_id = _run_id(runtime)
    state = runtime.state if runtime is not None else {}
    runtime_state = state.get("runtime") or {}
    workflows = state.get("workflows") or []
    events = state.get("workflow_events") or []
    task_ids = state.get("task_workspace_ids") or []
    _emit_run_event(
        kind="workflow",
        title="Workflow status checked",
        detail=f"{len(workflows)} workflow(s), {len(task_ids)} task workspace(s)",
        run_id=run_id,
        node_id=workplan_id,
        payload={"workflow_count": len(workflows), "task_workspace_count": len(task_ids)},
    )
    return _json(
        {
            "status": "ok",
            "run_id": run_id,
            "workplan_id": workplan_id,
            "workflow_count": len(workflows),
            "workflow_event_count": len(events),
            "task_workspace_ids": task_ids,
            "runtime": runtime_state,
        }
    )


@tool("spawn_subagent", parse_docstring=True)
def spawn_subagent_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    workplan_id: str,
    description: str,
    prompt: str,
    subagent_type: str = "general-purpose",
    max_turns: int | None = None,
) -> str:
    """Prepare a subagent dispatch as a child node of the current WorkPlan.

    This tool does not execute the subagent itself.  It returns a ``dispatch``
    payload that the lead agent can pass directly to ``task``.  Keeping the
    dispatch explicit makes the WorkPlan auditable while still using the
    existing subagent runtime as the execution adapter.

    Args:
        workplan_id: WorkPlan ID returned by ``workflow_start``.
        description: Short child-node description.
        prompt: Full subagent instructions.
        subagent_type: Catalog subagent type. Defaults to general-purpose.
        max_turns: Optional maximum subagent turns.
    """

    subagent_type = subagent_type.strip() or "general-purpose"
    available = set(get_subagent_names())
    if subagent_type not in available:
        return _json(
            {
                "status": "error",
                "error": f"unknown subagent_type: {subagent_type}",
                "available_subagents": sorted(available),
            }
        )
    run_id = _run_id(runtime)
    node_id = f"subagent-{uuid.uuid4().hex[:10]}"
    _emit_run_event(
        kind="subagent",
        title=f"Subagent planned: {subagent_type}",
        detail=description.strip()[:240],
        run_id=run_id,
        node_id=node_id,
        payload={"workplan_id": workplan_id, "subagent_type": subagent_type},
    )
    dispatch: dict[str, Any] = {
        "description": description,
        "prompt": f"WorkPlan: {workplan_id}\nNode: {node_id}\n\n{prompt}",
        "subagent_type": subagent_type,
    }
    if max_turns is not None:
        dispatch["max_turns"] = max_turns
    return _json(
        {
            "status": "ready",
            "workplan_id": workplan_id,
            "node_id": node_id,
            "run_id": run_id,
            "dispatch": dispatch,
            "next_tool": "task",
        }
    )


@tool("checkpoint", parse_docstring=True)
def checkpoint_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    workplan_id: str,
    title: str,
    summary: str,
    status: str = "running",
) -> str:
    """Record a workflow checkpoint into the unified run timeline.

    Args:
        workplan_id: WorkPlan ID returned by ``workflow_start``.
        title: Short checkpoint title.
        summary: User-visible checkpoint summary.
        status: running, blocked, completed, failed, or waiting_user.
    """

    run_id = _run_id(runtime)
    level = "success" if status == "completed" else "error" if status == "failed" else "warning" if status in {"blocked", "waiting_user"} else "info"
    _emit_run_event(
        kind="workflow",
        title=title,
        detail=summary,
        level=level,
        run_id=run_id,
        node_id=workplan_id,
        payload={"status": status, "workplan_id": workplan_id},
    )
    return _json(
        {
            "status": status,
            "workplan_id": workplan_id,
            "run_id": run_id,
            "title": title,
            "summary": summary,
        }
    )


WORKFLOW_RUNTIME_TOOLS = [
    workflow_start_tool,
    workflow_status_tool,
    spawn_subagent_tool,
    checkpoint_tool,
]
