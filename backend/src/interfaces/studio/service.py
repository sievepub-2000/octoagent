"""Studio Runtime service — Rowboat-compatible workflow execution engine.

Compiles visual workflow definitions into executable graphs and manages
the run/pause/resume/terminate lifecycle. Delegates actual agent
execution to task_workspaces.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from .contracts import CompiledWorkflow, WorkflowExecution, WorkflowExecutionStatus

logger = logging.getLogger(__name__)


class StudioRuntimeService:
    """Manages workflow compilation, execution lifecycle, and result collection."""

    def __init__(self) -> None:
        self._executions: dict[str, WorkflowExecution] = {}

    def compile_workflow(self, definition: dict[str, Any]) -> CompiledWorkflow:
        """Compile a visual workflow definition into an executable graph."""
        workflow_id = definition.get("id", str(uuid.uuid4()))
        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])
        entry = definition.get("entry_node_id") or (nodes[0]["id"] if nodes else None)

        compiled = CompiledWorkflow(
            workflow_id=workflow_id,
            name=definition.get("name", "Untitled"),
            nodes=nodes,
            edges=edges,
            entry_node_id=entry,
            metadata=definition.get("metadata", {}),
        )
        logger.info(
            "Compiled workflow %s: %d nodes, %d edges",
            compiled.workflow_id,
            len(nodes),
            len(edges),
        )
        return compiled

    async def run(self, compiled: CompiledWorkflow, *, inputs: dict[str, Any] | None = None) -> WorkflowExecution:
        """Execute a compiled workflow end-to-end."""
        execution_id = str(uuid.uuid4())
        execution = WorkflowExecution(
            execution_id=execution_id,
            workflow_id=compiled.workflow_id,
            status=WorkflowExecutionStatus.RUNNING,
            current_node_id=compiled.entry_node_id,
        )
        self._executions[execution_id] = execution

        try:
            for node in compiled.nodes:
                if execution.status == WorkflowExecutionStatus.PAUSED:
                    break
                execution.current_node_id = node.get("id")
                execution.step_count += 1

                # Dispatch node execution to task_workspaces
                node_result = await self._execute_node(node, inputs or {})
                execution.outputs[node.get("id", "")] = node_result

            if execution.status == WorkflowExecutionStatus.RUNNING:
                execution.status = WorkflowExecutionStatus.COMPLETED
        except Exception as exc:
            execution.status = WorkflowExecutionStatus.FAILED
            execution.error = str(exc)
            logger.error("Workflow execution %s failed: %s", execution_id, exc)

        return execution

    def pause(self, execution_id: str) -> WorkflowExecution | None:
        """Pause a running workflow execution."""
        execution = self._executions.get(execution_id)
        if execution and execution.status == WorkflowExecutionStatus.RUNNING:
            execution.status = WorkflowExecutionStatus.PAUSED
        return execution

    def resume(self, execution_id: str) -> WorkflowExecution | None:
        """Resume a paused workflow execution."""
        execution = self._executions.get(execution_id)
        if execution and execution.status == WorkflowExecutionStatus.PAUSED:
            execution.status = WorkflowExecutionStatus.RUNNING
        return execution

    def terminate(self, execution_id: str) -> WorkflowExecution | None:
        """Terminate a workflow execution."""
        execution = self._executions.get(execution_id)
        if execution and execution.status in (
            WorkflowExecutionStatus.RUNNING,
            WorkflowExecutionStatus.PAUSED,
        ):
            execution.status = WorkflowExecutionStatus.TERMINATED
        return execution

    def get_execution(self, execution_id: str) -> WorkflowExecution | None:
        return self._executions.get(execution_id)

    def list_executions(self) -> list[WorkflowExecution]:
        return list(self._executions.values())

    async def _execute_node(self, node: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute a single workflow node. Delegates to task_workspaces for agent nodes."""
        node_type = node.get("type", "passthrough")
        node_id = node.get("id", "unknown")

        if node_type == "agent":
            # Delegate to task workspace execution
            task_id = node.get("task_id")
            agent_id = node.get("agent_id")
            if task_id and agent_id:
                try:
                    from src.storage.task_workspaces import get_task_workspace_service

                    ws_service = get_task_workspace_service()
                    workspace = ws_service._find(task_id)
                    if workspace is not None:
                        return {"status": "delegated", "task_id": task_id, "agent_id": agent_id}
                except Exception as exc:
                    logger.warning("Node %s: agent delegation failed: %s", node_id, exc)
            return {"status": "skipped", "reason": "missing task_id or agent_id"}

        # Passthrough / transform nodes
        return {"status": "completed", "node_type": node_type, "inputs": inputs}


_service: StudioRuntimeService | None = None


def get_studio_runtime_service() -> StudioRuntimeService:
    global _service
    if _service is None:
        _service = StudioRuntimeService()
    return _service
