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
from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command
from langgraph.typing import ContextT

from src.agents.subagents.catalog import get_subagent_names
from src.agents.thread_state import ThreadState


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _workplans(runtime: ToolRuntime[ContextT, ThreadState] | None) -> list[dict[str, Any]]:
    if runtime is None or not runtime.state:
        return []
    state_runtime = runtime.state.get("runtime") or {}
    plans = state_runtime.get("workplans") if isinstance(state_runtime, dict) else None
    return [dict(item) for item in plans if isinstance(item, dict)] if isinstance(plans, list) else []


def _upsert_workplan(
    runtime: ToolRuntime[ContextT, ThreadState] | None,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    state_runtime = dict((runtime.state.get("runtime") or {}) if runtime is not None and runtime.state else {})
    plans = _workplans(runtime)
    next_plans: list[dict[str, Any]] = []
    replaced = False
    for plan in plans:
        if plan.get("workplan_id") == snapshot.get("workplan_id"):
            next_plans.append({**plan, **snapshot, "updated_at": _utc_now()})
            replaced = True
        else:
            next_plans.append(plan)
    if not replaced:
        next_plans.insert(0, {**snapshot, "created_at": _utc_now(), "updated_at": _utc_now()})
    state_runtime["workplans"] = next_plans[:20]
    state_runtime["active_workplan_id"] = snapshot.get("workplan_id")
    return state_runtime


def _append_workplan_node(
    runtime: ToolRuntime[ContextT, ThreadState] | None,
    *,
    workplan_id: str,
    node: dict[str, Any],
) -> dict[str, Any]:
    plans = _workplans(runtime)
    target = next((dict(plan) for plan in plans if plan.get("workplan_id") == workplan_id), None)
    if target is None:
        target = {
            "workplan_id": workplan_id,
            "run_id": _run_id(runtime),
            "goal": "",
            "mode": "workplan",
            "status": "running",
            "nodes": [],
        }
    nodes = [dict(item) for item in target.get("nodes", []) if isinstance(item, dict)]
    if not any(item.get("node_id") == node.get("node_id") for item in nodes):
        nodes.append(node)
    target["nodes"] = nodes[-80:]
    target["updated_at"] = _utc_now()
    return _upsert_workplan(runtime, target)


def _command(content: dict[str, Any], *, runtime_state: dict[str, Any], tool_call_id: str) -> Command:
    return Command(
        update={
            "runtime": runtime_state,
            "messages": [ToolMessage(_json(content), tool_call_id=tool_call_id)],
        }
    )


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
    tool_call_id: Annotated[str, InjectedToolCallId],
    workflow_id: str | None = None,
    mode: str = "workplan",
) -> Command:
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
    snapshot = {
        "workplan_id": workplan_id,
        "run_id": run_id,
        "goal": goal,
        "mode": mode,
        "status": "running",
        "nodes": [],
    }
    runtime_state = _upsert_workplan(runtime, snapshot)
    _emit_run_event(
        kind="workflow",
        title="Workflow started",
        detail=goal.strip()[:240],
        run_id=run_id,
        node_id=workplan_id,
        payload={"workflow_id": workplan_id, "mode": mode},
    )
    return _command(
        {
            "status": "started",
            "workplan_id": workplan_id,
            "run_id": run_id,
            "goal": goal,
            "mode": mode,
            "next_tools": ["spawn_subagent", "checkpoint", "workflow_status"],
        },
        runtime_state=runtime_state,
        tool_call_id=tool_call_id,
    )


@tool("workflow_status", parse_docstring=True)
def workflow_status_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    workplan_id: str | None = None,
) -> Command:
    """Return the current workflow/subagent runtime status for this thread.

    Args:
        workplan_id: Optional WorkPlan ID to attach to the emitted status event.
    """

    run_id = _run_id(runtime)
    state = runtime.state if runtime is not None else {}
    runtime_state = state.get("runtime") or {}
    runtime_state = dict(runtime_state) if isinstance(runtime_state, dict) else {}
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
    return _command(
        {
            "status": "ok",
            "run_id": run_id,
            "workplan_id": workplan_id,
            "workflow_count": len(workflows),
            "workflow_event_count": len(events),
            "task_workspace_ids": task_ids,
            "workplans": runtime_state.get("workplans", []),
        },
        runtime_state=runtime_state,
        tool_call_id=tool_call_id,
    )


@tool("spawn_subagent", parse_docstring=True)
def spawn_subagent_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    workplan_id: str,
    description: str,
    prompt: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    subagent_type: str = "general-purpose",
    max_turns: int | None = None,
) -> Command:
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
        return _command(
            {
                "status": "error",
                "error": f"unknown subagent_type: {subagent_type}",
                "available_subagents": sorted(available),
            },
            runtime_state=dict((runtime.state.get("runtime") or {}) if runtime is not None and runtime.state else {}),
            tool_call_id=tool_call_id,
        )
    run_id = _run_id(runtime)
    node_id = f"subagent-{uuid.uuid4().hex[:10]}"
    runtime_state = _append_workplan_node(
        runtime,
        workplan_id=workplan_id,
        node={
            "node_id": node_id,
            "kind": "subagent",
            "status": "planned",
            "description": description,
            "subagent_type": subagent_type,
            "created_at": _utc_now(),
        },
    )
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
    return _command(
        {
            "status": "ready",
            "workplan_id": workplan_id,
            "node_id": node_id,
            "run_id": run_id,
            "dispatch": dispatch,
            "next_tool": "task",
        },
        runtime_state=runtime_state,
        tool_call_id=tool_call_id,
    )


@tool("checkpoint", parse_docstring=True)
def checkpoint_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    workplan_id: str,
    title: str,
    summary: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    status: str = "running",
) -> Command:
    """Record a workflow checkpoint into the unified run timeline.

    Args:
        workplan_id: WorkPlan ID returned by ``workflow_start``.
        title: Short checkpoint title.
        summary: User-visible checkpoint summary.
        status: running, blocked, completed, failed, or waiting_user.
    """

    run_id = _run_id(runtime)
    level = "success" if status == "completed" else "error" if status == "failed" else "warning" if status in {"blocked", "waiting_user"} else "info"
    runtime_state = _upsert_workplan(
        runtime,
        {
            "workplan_id": workplan_id,
            "run_id": run_id,
            "status": status,
            "last_checkpoint": {
                "title": title,
                "summary": summary,
                "status": status,
                "created_at": _utc_now(),
            },
        },
    )
    _emit_run_event(
        kind="workflow",
        title=title,
        detail=summary,
        level=level,
        run_id=run_id,
        node_id=workplan_id,
        payload={"status": status, "workplan_id": workplan_id},
    )
    return _command(
        {
            "status": status,
            "workplan_id": workplan_id,
            "run_id": run_id,
            "title": title,
            "summary": summary,
        },
        runtime_state=runtime_state,
        tool_call_id=tool_call_id,
    )


WORKFLOW_RUNTIME_TOOLS = [
    workflow_start_tool,
    workflow_status_tool,
    spawn_subagent_tool,
    checkpoint_tool,
]
