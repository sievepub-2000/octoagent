"""Rowboat-style studio runtime contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowExecutionStatus(str, Enum):
    PENDING = "pending"
    COMPILING = "compiling"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


@dataclass
class CompiledWorkflow:
    """A compiled, execution-ready workflow graph."""

    workflow_id: str
    name: str
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    entry_node_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowExecution:
    """Runtime state for an executing workflow."""

    execution_id: str
    workflow_id: str
    status: WorkflowExecutionStatus = WorkflowExecutionStatus.PENDING
    current_node_id: str | None = None
    step_count: int = 0
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
