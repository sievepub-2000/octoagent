"""Core contracts for the subagent runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class SubagentStatus(StrEnum):
    """Canonical lifecycle states for delegated subagent jobs."""

    QUEUED = "queued"
    PENDING = "queued"
    ADMISSION_REJECTED = "admission_rejected"
    STARTING = "starting"
    RUNNING = "running"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_SUBAGENT_STATUSES


TERMINAL_SUBAGENT_STATUSES = frozenset(
    {
        SubagentStatus.ADMISSION_REJECTED,
        SubagentStatus.COMPLETED,
        SubagentStatus.FAILED,
        SubagentStatus.TIMED_OUT,
        SubagentStatus.CANCELLED,
        SubagentStatus.INTERRUPTED,
    }
)

ACTIVE_SUBAGENT_STATUSES = frozenset(
    {
        SubagentStatus.QUEUED,
        SubagentStatus.STARTING,
        SubagentStatus.RUNNING,
        SubagentStatus.STREAMING,
        SubagentStatus.CANCEL_REQUESTED,
    }
)


@dataclass
class SubagentBudget:
    """Resolved execution budget for a delegated job."""

    max_turns: int
    timeout_seconds: int
    model: str | None


@dataclass
class SubagentEvent:
    """Structured subagent runtime event."""

    sequence: int
    job_id: str
    event_type: str
    status: SubagentStatus
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class SubagentResult:
    """Materialized job state exposed to tools, routers, and tests."""

    task_id: str
    trace_id: str
    status: SubagentStatus
    result: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    ai_messages: list[dict[str, Any]] = field(default_factory=list)
    thread_id: str | None = None
    agent_name: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    rejection_reason: str | None = None
    cancellation_requested_at: datetime | None = None
    queue_started_at: datetime | None = None
    queue_completed_at: datetime | None = None
    budget: SubagentBudget | None = None
    event_count: int = 0

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal
