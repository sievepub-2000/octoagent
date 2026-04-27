"""Public-facing runtime API for workflow consumers (Slice E).

Provides a stable, narrow reading surface for external SDKs, widgets,
and channel integrations.  Write operations are limited to binding
activation metadata.

All endpoints live under /api/runtime/workflows.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.workflow_core import get_workflow_core_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runtime/workflows", tags=["public-runtime"])


# ── Request / response bodies ──────────────────────────────────────


class UpdateBindingsBody(BaseModel):
    """Request body for PUT /bindings."""

    channels: list[str] | None = Field(default=None, description="Channel kind identifiers to bind")
    mcp_servers: list[str] | None = Field(default=None, description="MCP server names to bind")
    skills: list[str] | None = Field(default=None, description="Skill names to enable")
    plugins: list[str] | None = Field(default=None, description="Plugin IDs to activate")


# ── Routes ─────────────────────────────────────────────────────────


@router.get("/{task_id}")
async def get_workflow_runtime(task_id: str) -> dict[str, Any]:
    """Return a stable public runtime snapshot of a workflow."""
    svc = get_workflow_core_service()
    result = svc.get_public_runtime(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Workflow {task_id!r} not found")
    return result


@router.get("/{task_id}/events")
async def get_workflow_events(
    task_id: str,
    cursor: int = Query(default=0, ge=0, description="Pagination cursor"),
    limit: int = Query(default=20, ge=1, le=200, description="Max events per page"),
) -> dict[str, Any]:
    """Return paginated timeline events for a workflow."""
    svc = get_workflow_core_service()
    result = svc.get_public_runtime_events(task_id, cursor=cursor, limit=limit)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Workflow {task_id!r} not found")
    return result


@router.get("/{task_id}/bindings")
async def get_workflow_bindings(task_id: str) -> dict[str, Any]:
    """Return the current binding metadata for a workflow."""
    svc = get_workflow_core_service()
    result = svc.get_public_bindings(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Workflow {task_id!r} not found")
    return result


@router.put("/{task_id}/bindings")
async def update_workflow_bindings(
    task_id: str,
    body: UpdateBindingsBody,
) -> dict[str, Any]:
    """Update the binding activation metadata for a workflow.

    Only provided fields are updated; omitted fields are left unchanged.
    """
    svc = get_workflow_core_service()
    result = svc.update_public_bindings(
        task_id,
        channels=body.channels,
        mcp_servers=body.mcp_servers,
        skills=body.skills,
        plugins=body.plugins,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Workflow {task_id!r} not found")
    return result


@router.get("/{task_id}/artifacts")
async def get_workflow_artifacts(task_id: str) -> list[dict[str, Any]]:
    """Return the list of artifacts produced by a workflow."""
    svc = get_workflow_core_service()
    result = svc.get_public_artifacts(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Workflow {task_id!r} not found")
    return result
