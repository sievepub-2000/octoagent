"""Workflow-facing studio runtime contracts.

These models define the compatibility contract returned by workflow runtime
surfaces while ownership shifts away from gateway-local response shaping.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .contracts import CheckpointRef, TaskProgress


class TaskArtifactFile(BaseModel):
    name: str
    path: str
    download_url: str


class TaskStudioChannelBinding(BaseModel):
    kind: str
    label: str
    enabled: bool
    status: str
    source: str


class TaskStudioBindingItem(BaseModel):
    binding_id: str
    kind: str
    label: str
    enabled: bool
    status: str
    source: str


class TaskStudioBindings(BaseModel):
    channels: list[TaskStudioBindingItem] = Field(default_factory=list)
    mcp_servers: list[TaskStudioBindingItem] = Field(default_factory=list)
    skills: list[TaskStudioBindingItem] = Field(default_factory=list)
    plugins: list[TaskStudioBindingItem] = Field(default_factory=list)


class TaskStudioTimelineEvent(BaseModel):
    event_id: str
    kind: str
    created_at: str
    title: str
    details: list[str] = Field(default_factory=list)
    summary: str | None = None
    source: str | None = None
    agent_id: str | None = None
    card_id: str | None = None
    session_id: str | None = None


class TaskStudioHandoff(BaseModel):
    handoff_id: str
    source_agent_id: str
    target_agent_id: str
    status: str
    query_session_id: str | None = None
    runtime_session_id: str | None = None
    linked_card_id: str | None = None
    created_at: str
    summary: str | None = None


class TaskStudioCheckpointSummary(BaseModel):
    total: int = 0
    latest: str | None = None
    ready_for_review: bool = False


class TaskStudioWorkflowSummary(BaseModel):
    graph_version: str
    cards_total: int = 0
    active_cards: int = 0
    completed_cards: int = 0
    blocked_cards: int = 0
    queued_cards: int = 0
    review_policy: str = "adaptive"


class TaskStudioReadiness(BaseModel):
    can_run: bool = False
    can_resume: bool = False
    requires_review: bool = False
    blocked_cards: int = 0
    queued_cards: int = 0
    completed_cards: int = 0
    active_handoffs: int = 0
    enabled_bindings: int = 0
    artifact_count: int = 0


class TaskStudioAgentSummary(BaseModel):
    agent_id: str
    name: str
    role: str
    status: str
    model_name: str | None = None
    task_scope: str | None = None
    linked_card_id: str | None = None
    query_session_id: str | None = None
    runtime_session_id: str | None = None
    langgraph_assistant_id: str | None = None
    langgraph_thread_scope: str | None = None
    last_runtime_provider: str | None = None
    last_execution_target: str | None = None
    last_execution_status: str | None = None
    last_result_summary: str | None = None
    message_count: int = 0
    last_message_at: str | None = None


class TaskStudioRuntimeSummary(BaseModel):
    project_memory_digest: str | None = None
    project_memory_updated_at: str | None = None
    latest_query_session_id: str | None = None
    latest_runtime_session_id: str | None = None
    active_query_sessions: int = 0
    active_runtime_sessions: int = 0
    memory_guard_state: str | None = None
    current_phase: str | None = None
    last_runtime_sync_at: str | None = None
    langgraph_graph_id: str | None = None
    last_langgraph_assistant_id: str | None = None
    langgraph_thread_scope: str | None = None
    langgraph_native_runtime: bool = False
    last_runtime_provider: str | None = None
    last_execution_target: str | None = None
    last_execution_status: str | None = None
    last_agent_result_summary: str | None = None


class TaskStudioRuntimeResponse(BaseModel):
    task_id: str
    name: str
    mode: str
    status: str
    goal: str
    updated_at: str
    progress: TaskProgress
    workflow_summary: TaskStudioWorkflowSummary
    agents: list[TaskStudioAgentSummary] = Field(default_factory=list)
    timeline: list[TaskStudioTimelineEvent] = Field(default_factory=list)
    handoffs: list[TaskStudioHandoff] = Field(default_factory=list)
    checkpoints: list[CheckpointRef] = Field(default_factory=list)
    checkpoints_summary: TaskStudioCheckpointSummary = Field(default_factory=TaskStudioCheckpointSummary)
    artifacts: list[TaskArtifactFile] = Field(default_factory=list)
    bindings: TaskStudioBindings = Field(default_factory=TaskStudioBindings)
    channel_bindings: list[TaskStudioChannelBinding] = Field(default_factory=list)
    readiness: TaskStudioReadiness = Field(default_factory=TaskStudioReadiness)
    runtime_summary: TaskStudioRuntimeSummary = Field(default_factory=TaskStudioRuntimeSummary)
    run_log: str = ""


class TaskStudioRuntimeEventsResponse(BaseModel):
    task_id: str
    cursor: int = 0
    next_cursor: int | None = None
    events: list[TaskStudioTimelineEvent] = Field(default_factory=list)


__all__ = [
    "TaskArtifactFile",
    "TaskStudioAgentSummary",
    "TaskStudioBindingItem",
    "TaskStudioBindings",
    "TaskStudioChannelBinding",
    "TaskStudioCheckpointSummary",
    "TaskStudioHandoff",
    "TaskStudioReadiness",
    "TaskStudioRuntimeEventsResponse",
    "TaskStudioRuntimeResponse",
    "TaskStudioRuntimeSummary",
    "TaskStudioTimelineEvent",
    "TaskStudioWorkflowSummary",
]