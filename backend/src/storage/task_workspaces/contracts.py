"""Contracts for task workspaces, cards, checkpoints, and agent sessions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from src.agents.runtime.contracts import AgentExecutionStrategy, AgentRuntimeProviderName

TaskExecutionMode = Literal["single", "branch", "group"]
TaskAgentPermissionMode = Literal["approval", "directory", "system", "workspace", "yolo"]
TaskWorkspaceStatus = Literal[
    "created",
    "planned",
    "running",
    "paused",
    "waiting_review",
    "completed",
    "terminated",
    "failed",
]
TaskCardKind = Literal[
    "start",
    "agent",
    "conversation-interface",
    "tooling",
    "research",
    "docker-runtime",
    "branch-router",
    "group-manager",
    "checkpoint",
    "artifact",
    "review",
]
TaskCardStatus = Literal[
    "idle",
    "configured",
    "running",
    "paused",
    "blocked",
    "completed",
    "terminated",
]
AgentHandleStatus = Literal[
    "idle",
    "queued",
    "running",
    "paused",
    "waiting_handoff",
    "completed",
    "terminated",
    "failed",
]
AgentMessageRole = Literal["system", "user", "assistant"]


def normalize_runtime_provider(value: Any) -> AgentRuntimeProviderName:
    candidate = str(value or "").strip().lower()
    if candidate in {"", "crewai", "crew_ai", "crew-ai", "langgraph", "openai", "openai_agents", "openai-agents", "unified"}:
        return "langgraph"
    return "langgraph"


def normalize_execution_strategy(value: Any) -> AgentExecutionStrategy:
    _ = value
    return "fixed"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


class TaskProgress(BaseModel):
    completed_cards: int = 0
    total_cards: int = 0
    active_agents: int = 0
    completed_agents: int = 0
    checkpoint_count: int = 0


class DeploymentInterface(BaseModel):
    kind: Literal["conversation", "api", "webhook", "internal"]
    label: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class DockerExecutionProfile(BaseModel):
    profile_id: str
    label: str
    runtime_kind: Literal[
        "local_host",
        "docker_local",
        "docker_provisioner",
        "remote_runtime",
        "desktop_local",
    ]
    selected: bool = False
    image: str | None = None
    resource_limits: dict[str, Any] = Field(default_factory=dict)
    mounts: list[str] = Field(default_factory=list)
    network_policy: str = "default"
    persistence_mode: str = "task_scoped"
    checkpoint_policy: str = "manual_and_runtime"
    approval_level: Literal["none", "soft", "strict"] = "soft"
    live_status: Literal["ready", "degraded", "disabled"] = "ready"
    capabilities: list[str] = Field(default_factory=list)


class TaskCard(BaseModel):
    card_id: str
    kind: TaskCardKind
    title: str
    description: str | None = None
    status: TaskCardStatus = "configured"
    linked_agent_id: str | None = None
    permission_mode: TaskAgentPermissionMode = "workspace"
    config: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class TaskCardEdge(BaseModel):
    edge_id: str
    source_card_id: str
    target_card_id: str
    label: str | None = None


class TaskCardGraph(BaseModel):
    cards: list[TaskCard] = Field(default_factory=list)
    edges: list[TaskCardEdge] = Field(default_factory=list)


class CheckpointRef(BaseModel):
    checkpoint_id: str
    label: str
    task_status: TaskWorkspaceStatus
    created_at: str
    card_id: str | None = None
    note: str | None = None


class AgentConversationRef(BaseModel):
    task_id: str
    agent_id: str
    message_count: int = 0
    last_message_at: str | None = None


class AgentMessage(BaseModel):
    message_id: str
    role: AgentMessageRole
    content: str
    created_at: str


class AgentHandle(BaseModel):
    agent_id: str
    name: str
    role: str
    status: AgentHandleStatus = "idle"
    model_name: str | None = None
    runtime_provider: str | None = None  # Per-agent provider override (hybrid mode)
    linked_card_id: str | None = None
    task_scope: str | None = None
    conversation: AgentConversationRef
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("runtime_provider", mode="before")
    @classmethod
    def _normalize_runtime_provider(cls, value: Any) -> str | None:
        if value is None:
            return None
        return normalize_runtime_provider(value)


class TaskWorkspaceSummary(BaseModel):
    task_id: str
    name: str
    mode: TaskExecutionMode
    summary: str = ""
    agent_runtime_provider: AgentRuntimeProviderName = "langgraph"
    execution_strategy: AgentExecutionStrategy = "fixed"
    status: TaskWorkspaceStatus
    created_at: str
    updated_at: str
    goal: str = ""
    progress: TaskProgress = Field(default_factory=TaskProgress)

    @field_validator("agent_runtime_provider", mode="before")
    @classmethod
    def _normalize_runtime_provider(cls, value: Any) -> AgentRuntimeProviderName:
        return normalize_runtime_provider(value)

    @field_validator("execution_strategy", mode="before")
    @classmethod
    def _normalize_execution_strategy(cls, value: Any) -> AgentExecutionStrategy:
        return normalize_execution_strategy(value)


class TaskWorkspace(BaseModel):
    task_id: str
    name: str
    mode: TaskExecutionMode
    agent_runtime_provider: AgentRuntimeProviderName = "langgraph"
    execution_strategy: AgentExecutionStrategy = "fixed"
    status: TaskWorkspaceStatus
    created_at: str
    updated_at: str
    goal: str = ""
    summary: str = ""
    top_bar_label: str | None = None
    deployment_interfaces: list[DeploymentInterface] = Field(default_factory=list)
    runtime_profiles: list[DockerExecutionProfile] = Field(default_factory=list)
    card_graph: TaskCardGraph = Field(default_factory=TaskCardGraph)
    agents: list[AgentHandle] = Field(default_factory=list)
    checkpoints: list[CheckpointRef] = Field(default_factory=list)
    progress: TaskProgress = Field(default_factory=TaskProgress)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent_runtime_provider", mode="before")
    @classmethod
    def _normalize_runtime_provider(cls, value: Any) -> AgentRuntimeProviderName:
        return normalize_runtime_provider(value)

    @field_validator("execution_strategy", mode="before")
    @classmethod
    def _normalize_execution_strategy(cls, value: Any) -> AgentExecutionStrategy:
        return normalize_execution_strategy(value)


class CreateTaskWorkspaceRequest(BaseModel):
    name: str | None = None
    goal: str = ""
    mode: TaskExecutionMode = "single"
    agent_runtime_provider: AgentRuntimeProviderName | None = None
    execution_strategy: AgentExecutionStrategy | None = None
    summary: str = ""
    auto_research: bool = False
    enabled_skills: list[str] = Field(default_factory=list)
    expected_keywords: list[str] = Field(default_factory=list)
    max_turns: int | None = None
    timeout_seconds: int | None = None
    token_budget: int | None = None

    @field_validator("agent_runtime_provider", mode="before")
    @classmethod
    def _normalize_runtime_provider(cls, value: Any) -> AgentRuntimeProviderName | None:
        if value is None:
            return None
        return normalize_runtime_provider(value)

    @field_validator("execution_strategy", mode="before")
    @classmethod
    def _normalize_execution_strategy(cls, value: Any) -> AgentExecutionStrategy | None:
        if value is None:
            return None
        return normalize_execution_strategy(value)


class UpdateTaskWorkspaceRequest(BaseModel):
    name: str | None = None
    goal: str | None = None
    summary: str | None = None
    agent_runtime_provider: AgentRuntimeProviderName | None = None
    execution_strategy: AgentExecutionStrategy | None = None
    status: TaskWorkspaceStatus | None = None
    top_bar_label: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("agent_runtime_provider", mode="before")
    @classmethod
    def _normalize_runtime_provider(cls, value: Any) -> AgentRuntimeProviderName | None:
        if value is None:
            return None
        return normalize_runtime_provider(value)

    @field_validator("execution_strategy", mode="before")
    @classmethod
    def _normalize_execution_strategy(cls, value: Any) -> AgentExecutionStrategy | None:
        if value is None:
            return None
        return normalize_execution_strategy(value)


class UpdateTaskCardGraphRequest(BaseModel):
    card_graph: TaskCardGraph


class CreateCheckpointRequest(BaseModel):
    label: str | None = None
    card_id: str | None = None
    note: str | None = None


class CreateAgentMessageRequest(BaseModel):
    content: str
    model_override: str | None = None


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    model_name: str | None = None
    task_scope: str | None = None
    metadata: dict[str, Any] | None = None


class UpdateTaskCardRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    linked_agent_id: str | None = None
    config: dict[str, Any] | None = None
    tags: list[str] | None = None
