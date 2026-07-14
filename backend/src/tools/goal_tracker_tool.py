"""Goal tracking tool — allows agent to read/reaffirm current task goal."""

from __future__ import annotations

import logging
from typing import Any

from src.storage.task_workspaces import get_task_workspace_service

logger = logging.getLogger(__name__)

GOAL_TRACKING_TOOL_DEFINITION = {
    "name": "get_current_goal",
    "description": "Read the current task/project goal to reaffirm what you are working on. Call this when you feel uncertain about the objective or before making significant decisions.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "Optional task/project ID. If omitted, returns the most recently active goal.",
            }
        },
    },
}

SET_SUBGOAL_TOOL_DEFINITION = {
    "name": "set_subgoal",
    "description": "Record a sub-goal or intermediate milestone within the current task. This helps track progress and prevents goal drift.",
    "parameters": {
        "type": "object",
        "properties": {
            "subgoal": {
                "type": "string",
                "description": "The sub-goal description (1-2 sentences).",
            },
            "task_id": {
                "type": "string",
                "description": "Task/project ID.",
            },
        },
        "required": ["subgoal", "task_id"],
    },
}

CONFIRM_GOAL_TOOL_DEFINITION = {
    "name": "confirm_goal_alignment",
    "description": "Check whether your current direction still aligns with the original task goal. Use this when you suspect goal drift.",
    "parameters": {
        "type": "object",
        "properties": {
            "current_approach": {
                "type": "string",
                "description": "Describe what you are currently doing or planning to do.",
            },
            "task_id": {
                "type": "string",
                "description": "Task/project ID.",
            },
        },
        "required": ["current_approach", "task_id"],
    },
}


def get_current_goal(task_id: str | None = None) -> dict[str, Any]:
    """Tool: return the current task/project goal."""
    try:
        svc = get_task_workspace_service()
        if task_id:
            ws = svc.get_workspace(task_id)
            if ws is not None:
                return {
                    "status": "ok",
                    "task_id": ws.task_id,
                    "name": ws.name,
                    "goal": ws.goal or ws.name,
                    "task_status": ws.status,
                    "progress": {
                        "completed": ws.progress.completed_cards,
                        "total": ws.progress.total_cards,
                    },
                }
            return {"status": "error", "message": f"Task {task_id} not found"}

        # Return most recently updated workspace
        workspaces = svc.list_workspaces()
        if workspaces:
            ws = workspaces[0]
            return {
                "status": "ok",
                "task_id": ws.task_id,
                "name": ws.name,
                "goal": ws.goal or ws.name,
                "task_status": ws.status,
                "progress": {
                    "completed": ws.progress.completed_cards,
                    "total": ws.progress.total_cards,
                },
            }
        return {"status": "error", "message": "No active task found"}
    except Exception as exc:
        logger.warning("get_current_goal failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def set_subgoal(subgoal: str, task_id: str) -> dict[str, Any]:
    """Tool: record a sub-goal to track progress."""
    try:
        svc = get_task_workspace_service()
        ws = svc.get_workspace(task_id)
        if ws is None:
            return {"status": "error", "message": f"Task {task_id} not found"}
        metadata = dict(ws.metadata or {})
        subgoals = metadata.get("subgoals", [])
        if not isinstance(subgoals, list):
            subgoals = []
        from datetime import UTC, datetime

        subgoals.append(
            {
                "goal": subgoal,
                "timestamp": datetime.now(UTC).isoformat(),
                "completed": False,
            }
        )
        metadata["subgoals"] = subgoals
        svc.merge_workspace_metadata(task_id, **metadata)
        return {"status": "ok", "subgoal_index": len(subgoals) - 1}
    except Exception as exc:
        logger.warning("set_subgoal failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def confirm_goal_alignment(current_approach: str, task_id: str) -> dict[str, Any]:
    """Tool: check if current approach aligns with original goal."""
    try:
        svc = get_task_workspace_service()
        ws = svc.get_workspace(task_id)
        if ws is None:
            return {"status": "error", "message": f"Task {task_id} not found"}
        goal = ws.goal or ws.name
        return {
            "status": "ok",
            "original_goal": goal,
            "current_approach": current_approach,
            "task_name": ws.name,
            "reminder": f"Your original goal is: {goal}. Ensure your current approach directly serves this goal.",
        }
    except Exception as exc:
        logger.warning("confirm_goal_alignment failed: %s", exc)
        return {"status": "error", "message": str(exc)}


# Registry for all goal-tracking tools
GOAL_TRACKING_TOOLS = [
    get_current_goal,
    set_subgoal,
    confirm_goal_alignment,
]

GOAL_TRACKING_TOOL_DEFINITIONS = [
    GOAL_TRACKING_TOOL_DEFINITION,
    SET_SUBGOAL_TOOL_DEFINITION,
    CONFIRM_GOAL_TOOL_DEFINITION,
]
