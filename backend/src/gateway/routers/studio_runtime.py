"""Studio Runtime gateway router — workflow compile/run/pause/resume/terminate.

Exposes the StudioRuntimeService lifecycle over HTTP so the frontend
workflow builder can manage executions.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.studio_runtime import get_studio_runtime_service
from src.studio_runtime.contracts import WorkflowExecutionStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/studio", tags=["studio"])


# ── Request / Response models ─────────────────────────────────────────────────

class NodeSpec(BaseModel):
    id: str
    type: str = "passthrough"
    label: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class EdgeSpec(BaseModel):
    id: str
    source: str
    target: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    id: str | None = None
    name: str = "Untitled"
    nodes: list[NodeSpec] = Field(default_factory=list)
    edges: list[EdgeSpec] = Field(default_factory=list)
    entry_node_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompiledWorkflowResponse(BaseModel):
    workflow_id: str
    name: str
    node_count: int
    edge_count: int
    entry_node_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunRequest(BaseModel):
    definition: WorkflowDefinition
    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowExecutionResponse(BaseModel):
    execution_id: str
    workflow_id: str
    status: WorkflowExecutionStatus
    current_node_id: str | None = None
    step_count: int = 0
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class WorkflowExecutionsListResponse(BaseModel):
    executions: list[WorkflowExecutionResponse] = Field(default_factory=list)
    total: int = 0


# ── Helper ─────────────────────────────────────────────────────────────────────

def _execution_to_response(ex) -> WorkflowExecutionResponse:
    return WorkflowExecutionResponse(
        execution_id=ex.execution_id,
        workflow_id=ex.workflow_id,
        status=ex.status,
        current_node_id=ex.current_node_id,
        step_count=ex.step_count,
        outputs=ex.outputs,
        error=ex.error,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/compile", response_model=CompiledWorkflowResponse)
async def compile_workflow(definition: WorkflowDefinition) -> CompiledWorkflowResponse:
    """Compile a visual workflow definition (validate graph structure, resolve entry node)."""
    svc = get_studio_runtime_service()
    compiled = svc.compile_workflow(definition.model_dump())
    return CompiledWorkflowResponse(
        workflow_id=compiled.workflow_id,
        name=compiled.name,
        node_count=len(compiled.nodes),
        edge_count=len(compiled.edges),
        entry_node_id=compiled.entry_node_id,
        metadata=compiled.metadata,
    )


@router.post("/run", response_model=WorkflowExecutionResponse, status_code=202)
async def run_workflow(request: WorkflowRunRequest) -> WorkflowExecutionResponse:
    """Compile and start a workflow execution. Returns the initial execution state."""
    svc = get_studio_runtime_service()
    compiled = svc.compile_workflow(request.definition.model_dump())
    execution = await svc.run(compiled, inputs=request.inputs)
    return _execution_to_response(execution)


@router.get("/executions", response_model=WorkflowExecutionsListResponse)
async def list_executions() -> WorkflowExecutionsListResponse:
    """List all workflow executions (active and completed)."""
    svc = get_studio_runtime_service()
    executions = svc.list_executions()
    return WorkflowExecutionsListResponse(
        executions=[_execution_to_response(e) for e in executions],
        total=len(executions),
    )


@router.get("/executions/{execution_id}", response_model=WorkflowExecutionResponse)
async def get_execution(execution_id: str) -> WorkflowExecutionResponse:
    """Get the current state of a workflow execution."""
    svc = get_studio_runtime_service()
    ex = svc.get_execution(execution_id)
    if ex is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return _execution_to_response(ex)


@router.post("/executions/{execution_id}/pause", response_model=WorkflowExecutionResponse)
async def pause_execution(execution_id: str) -> WorkflowExecutionResponse:
    """Pause a running workflow execution."""
    svc = get_studio_runtime_service()
    ex = svc.pause(execution_id)
    if ex is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found or not running")
    return _execution_to_response(ex)


@router.post("/executions/{execution_id}/resume", response_model=WorkflowExecutionResponse)
async def resume_execution(execution_id: str) -> WorkflowExecutionResponse:
    """Resume a paused workflow execution."""
    svc = get_studio_runtime_service()
    ex = svc.resume(execution_id)
    if ex is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found or not paused")
    return _execution_to_response(ex)


@router.post("/executions/{execution_id}/terminate", response_model=WorkflowExecutionResponse)
async def terminate_execution(execution_id: str) -> WorkflowExecutionResponse:
    """Terminate a running or paused workflow execution."""
    svc = get_studio_runtime_service()
    ex = svc.terminate(execution_id)
    if ex is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found or already terminal")
    return _execution_to_response(ex)
