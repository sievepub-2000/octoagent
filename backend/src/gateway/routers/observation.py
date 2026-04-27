"""Observation routes backed by existing task workspace run logs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.workflow_core import get_workflow_core_service
from src.workflow_core.observation import parse_run_log_timeline

router = APIRouter(prefix="/api/observation", tags=["observation"])

class ObservationTimelineEvent(BaseModel):
    timestamp: str
    title: str
    details: list[str] = Field(default_factory=list)


class TaskObservationTimelineResponse(BaseModel):
    task_id: str
    events: list[ObservationTimelineEvent] = Field(default_factory=list)

@router.get("/tasks/{task_id}/timeline", response_model=TaskObservationTimelineResponse)
async def get_task_observation_timeline(task_id: str) -> TaskObservationTimelineResponse:
    workspace = get_workflow_core_service().get_workspace(task_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{task_id}' not found")
    run_log = get_workflow_core_service().read_run_log(task_id) or ""
    return TaskObservationTimelineResponse(
        task_id=workspace.task_id,
        events=[
            ObservationTimelineEvent(
                timestamp=str(event.get("created_at") or ""),
                title=str(event.get("title") or "Run log event"),
                details=[str(item) for item in event.get("details", []) if str(item).strip()],
            )
            for event in parse_run_log_timeline(run_log)
        ],
    )