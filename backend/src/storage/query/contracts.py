"""Contracts for the repository-owned query engine layer."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.agents.runtime.contracts import AgentRuntimeProviderName

QueryPermissionMode = Literal["approval", "directory", "system", "workspace", "yolo"]


class QueryEngineCapability(BaseModel):
    enabled: bool = True
    supports_workspace_sessions: bool = True
    supports_prompt_section_assembly: bool = True
    supports_handoff_ready_sessions: bool = True
    supports_compaction_planning: bool = True
    supports_previous_session_summary: bool = True
    supports_runtime_events: bool = True
    supports_context_snapshots: bool = True
    supports_tool_registry: bool = True
    supports_mcp_server_summary: bool = True
    supports_task_analysis: bool = True
    supports_turn_execution: bool = True
    supports_memory_optimization: bool = True
    supports_client_operation_protocol: bool = True
    supports_session_governance: bool = True
    supports_goal_drift_detection: bool = True
    supports_stale_session_recovery: bool = True
    supports_runtime_cache_maintenance: bool = True
    note: str = "Query engine owns session-scoped turn execution between workspace/orchestration state and provider-facing query loops."


class QueryClientCommand(BaseModel):
    operation_id: str
    source: Literal["client", "server"] = "client"
    intent: Literal[
        "conversation",
        "repo_read",
        "browser",
        "workspace_cli",
        "system_cli",
        "filesystem",
        "desktop",
        "research",
    ] = "conversation"
    execution_target: Literal[
        "repo_read",
        "browser_runtime",
        "system_execution",
        "research_runtime",
    ] = "repo_read"
    command_text: str | None = None
    cli_scope: Literal["workspace", "system"] | None = None
    requested_url: str | None = None
    requested_path: str | None = None
    requested_app: str | None = None
    notes: list[str] = Field(default_factory=list)


class QueryGoalDriftReport(BaseModel):
    status: Literal["aligned", "watch", "drifting"] = "aligned"
    score: float = 0.0
    reason: str = "Current turn remains aligned with the active goal."
    suggested_focus: str | None = None


class QuerySessionGovernance(BaseModel):
    continuation_mode: Literal["fresh", "continued", "resumed"] = "fresh"
    continuity_summary: str = "Fresh session with no prior handoff detected."
    context_pressure: Literal["low", "medium", "high"] = "low"
    recommended_memory_action: Literal["continue", "refresh", "compact"] = "continue"
    goal_drift: QueryGoalDriftReport = Field(default_factory=QueryGoalDriftReport)
    active_operation: QueryClientCommand | None = None


class PromptSection(BaseModel):
    section_id: str
    title: str
    content: str
    cache_behavior: Literal["stable", "dynamic"] = "stable"


class QueryTurn(BaseModel):
    turn_id: str
    status: Literal["planned", "running", "completed", "failed"] = "planned"
    user_message: str
    assistant_summary: str | None = None
    operation_id: str | None = None
    tool_call_count: int = 0
    execution_target: str | None = None
    execution_status: Literal["none", "planned", "completed", "blocked", "simulated"] = "none"
    runtime_provider: AgentRuntimeProviderName | None = None
    runtime_session_id: str | None = None
    runtime_step_id: str | None = None
    memory_action: Literal["none", "refreshed", "compacted"] = "none"
    created_at: str


class QuerySessionSummary(BaseModel):
    summary_id: str
    session_id: str
    kind: Literal["compaction", "previous_session"] = "compaction"
    title: str
    content: str
    open_items: list[str] = Field(default_factory=list)
    quality_score: float = 0.0
    quality_notes: list[str] = Field(default_factory=list)
    created_at: str


class QueryRuntimeEvent(BaseModel):
    event_id: str
    session_id: str
    turn_id: str | None = None
    kind: Literal[
        "session_created",
        "context_snapshot_built",
        "tool_registry_built",
        "task_analyzed",
        "turn_recorded",
        "turn_executed",
        "memory_optimized",
        "session_compacted",
        "summary_promoted",
        "client_command_planned",
        "goal_drift_detected",
        "continuation_applied",
        "summary_quality_evaluated",
        "replay_context_built",
        "stale_thread_recovered",
    ]
    detail: str
    created_at: str


class QueryTurnRecordRequest(BaseModel):
    user_message: str
    assistant_summary: str | None = None
    tool_call_count: int = 0
    status: Literal["planned", "running", "completed", "failed"] = "completed"


class QuerySessionCompactRequest(BaseModel):
    retain_turns: int = 2
    title: str = "Session Compaction Summary"


class QuerySessionRefreshRequest(BaseModel):
    reason: str = "manual_refresh"


class QueryTurnExecutionRequest(BaseModel):
    user_message: str
    allow_side_effects: bool = False
    auto_compact: bool = True
    force_profile_refresh: bool = False
    client_command: QueryClientCommand | None = None


class QueryOperationPlanRequest(BaseModel):
    user_message: str
    current_goal: str | None = None
    continuation_source: str | None = None
    permission_mode: QueryPermissionMode = "approval"
    archived_turn_count: int = 0


class QueryOperationPlanResponse(BaseModel):
    normalized_message: str
    command: QueryClientCommand
    governance: QuerySessionGovernance


class QueryContextSnapshot(BaseModel):
    snapshot_id: str
    repo_root: str
    workspace_mode: str
    active_goal: str
    top_docs: list[str] = Field(default_factory=list)
    selected_runtime_profiles: list[str] = Field(default_factory=list)
    deployment_interfaces: list[str] = Field(default_factory=list)
    compiled_graph_id: str | None = None
    card_count: int = 0
    checkpoint_count: int = 0
    agent_count: int = 0


class QueryToolDescriptor(BaseModel):
    tool_id: str
    title: str
    source: Literal["builtin", "mcp", "plugin"]
    kind: Literal["read", "write", "exec", "browser", "system", "research", "coordination", "integration"]
    enabled: bool = True
    requires_approval: bool = False
    note: str = ""


class QueryMcpServerSummary(BaseModel):
    server_id: str
    transport: Literal["stdio", "sse", "http"]
    enabled: bool = True
    description: str = ""
    auth_mode: Literal["none", "oauth"] = "none"


class QueryTaskAnalysis(BaseModel):
    analysis_id: str
    summary: str
    session_mode: Literal["normal", "coordinator", "auto"] = "normal"
    coordination_strategy: Literal["solo", "coordinator_workers", "manager_review"] = "solo"
    permission_mode: QueryPermissionMode = "approval"
    execution_flow: list[str] = Field(default_factory=list)
    plan_items: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    suggested_runtime_targets: list[str] = Field(default_factory=list)
    primary_risk_labels: list[str] = Field(default_factory=list)
    memory_sources: list[str] = Field(default_factory=list)
    self_review_checklist: list[str] = Field(default_factory=list)
    review_required: bool = False


class QueryMemoryLayer(BaseModel):
    layer_id: str
    scope: Literal["session", "workspace", "project"] = "workspace"
    weight: float = 1.0
    summary: str
    source_refs: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class QueryMemoryProfile(BaseModel):
    archived_turn_count: int = 0
    compaction_count: int = 0
    active_layers: int = 0
    dominant_scope: Literal["session", "workspace", "project", "mixed"] = "mixed"
    weighted_signal_score: float = 0.0
    recall_summary: str = ""
    context_pressure: Literal["low", "medium", "high"] = "low"
    recommended_action: Literal["continue", "refresh", "compact"] = "continue"


class QuerySession(BaseModel):
    session_id: str
    task_id: str
    agent_id: str
    status: Literal["planned", "ready", "running", "paused", "completed", "failed"] = "planned"
    current_goal: str
    prompt_stack_profile_id: str
    prompt_sections: list[PromptSection] = Field(default_factory=list)
    assembled_system_prompt: str = ""
    context_snapshot: QueryContextSnapshot | None = None
    available_tools: list[QueryToolDescriptor] = Field(default_factory=list)
    mcp_servers: list[QueryMcpServerSummary] = Field(default_factory=list)
    task_analysis: QueryTaskAnalysis | None = None
    memory_layers: list[QueryMemoryLayer] = Field(default_factory=list)
    memory_profile: QueryMemoryProfile = Field(default_factory=QueryMemoryProfile)
    governance: QuerySessionGovernance = Field(default_factory=QuerySessionGovernance)
    turns: list[QueryTurn] = Field(default_factory=list)
    summaries: list[QuerySessionSummary] = Field(default_factory=list)
    runtime_events: list[QueryRuntimeEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
