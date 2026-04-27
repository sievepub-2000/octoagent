"""Shared workflow status and stage normalization helpers."""

from __future__ import annotations

from src.task_workspaces.contracts import TaskWorkspace, TaskWorkspaceStatus

TERMINAL_WORKSPACE_STATUSES = {"completed", "failed", "terminated"}

# Slice C / D extended vocabulary for Hermes-style lifecycle states
LIFECYCLE_STATES = {
    "signal_wait",
    "human_review_required",
    "checkpoint_ready",
    "hook_executing",
    "builder_applying",
}


def workflow_stage_for_status(status: str) -> str:
    if status == "created":
        return "created"
    if status == "planned":
        return "planned"
    if status == "running":
        return "executing"
    if status == "paused":
        return "paused"
    if status == "waiting_review":
        return "review"
    if status == "completed":
        return "completed"
    if status == "failed":
        return "failed"
    if status == "terminated":
        return "terminated"
    # Hermes-style extended states
    if status == "signal_wait":
        return "waiting"
    if status == "human_review_required":
        return "review"
    if status == "checkpoint_ready":
        return "review"
    if status == "hook_executing":
        return "executing"
    if status == "builder_applying":
        return "executing"
    return "unknown"


def lifecycle_phase_label(status: str) -> str:
    """Return a human-readable label for any workflow phase."""
    labels = {
        "created": "Created",
        "planned": "Planned",
        "running": "Executing",
        "paused": "Paused",
        "waiting_review": "Waiting for Review",
        "completed": "Completed",
        "failed": "Failed",
        "terminated": "Terminated",
        "signal_wait": "Waiting for Signal",
        "human_review_required": "Human Review Required",
        "checkpoint_ready": "Checkpoint Ready",
        "hook_executing": "Hook Executing",
        "builder_applying": "Builder Applying",
    }
    return labels.get(status, status.replace("_", " ").title())


def workspace_status_from_runtime(workspace: TaskWorkspace) -> TaskWorkspaceStatus:
    agent_statuses = {agent.status for agent in workspace.agents}
    if "failed" in agent_statuses:
        return "failed"
    if "running" in agent_statuses:
        return "running"
    if "paused" in agent_statuses and "running" not in agent_statuses:
        return "paused"
    if workspace.agents and all(agent.status in {"completed", "terminated"} for agent in workspace.agents):
        review_policy = str(workspace.metadata.get("review_policy") or "adaptive")
        if review_policy == "required" and bool(workspace.metadata.get("review_completed")):
            return "completed"
        return "waiting_review" if review_policy == "required" else "completed"
    if "waiting_handoff" in agent_statuses or "queued" in agent_statuses:
        return "planned"
    return workspace.status


def agent_status_from_query_session(status: str, latest_execution_status: str | None) -> str:
    if status == "running":
        return "running"
    if status == "paused":
        return "paused"
    if status == "failed" or latest_execution_status == "blocked":
        return "failed"
    if status == "completed":
        return "completed"
    return "waiting_handoff"


def agent_status_from_workspace_terminal_state(
    workspace_status: TaskWorkspaceStatus,
    current_status: str,
    runtime_status: str,
) -> str:
    if workspace_status == "completed":
        if current_status in {"failed", "terminated"}:
            return current_status
        return "completed"
    if workspace_status == "failed":
        if current_status in {"failed", "completed", "terminated"}:
            return current_status
        if runtime_status == "failed":
            return "failed"
        return "terminated"
    if workspace_status == "terminated":
        if current_status in {"failed", "completed", "terminated"}:
            return current_status
        return "terminated"
    return runtime_status


def card_status_from_query_session(status: str, latest_execution_status: str | None) -> str:
    if status == "running":
        return "running"
    if status == "paused":
        return "paused"
    if status == "failed" or latest_execution_status == "blocked":
        return "blocked"
    if status == "completed":
        return "completed"
    return "configured"


def card_status_from_agent_status(agent_status: str) -> str:
    if agent_status == "running":
        return "running"
    if agent_status == "paused":
        return "paused"
    if agent_status == "failed":
        return "blocked"
    if agent_status == "completed":
        return "completed"
    if agent_status == "terminated":
        return "terminated"
    return "configured"


__all__ = [
    "TERMINAL_WORKSPACE_STATUSES",
    "agent_status_from_query_session",
    "agent_status_from_workspace_terminal_state",
    "card_status_from_agent_status",
    "card_status_from_query_session",
    "workflow_stage_for_status",
    "workspace_status_from_runtime",
]