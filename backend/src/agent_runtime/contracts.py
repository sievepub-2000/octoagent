"""Provider-neutral agent runtime contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

AgentRuntimeProviderName = Literal["langgraph"]
AgentRuntimeKind = Literal["remote_graph"]
AgentRuntimeSessionIdentifierKind = Literal["thread_id"]
AgentRuntimeExecutionTargetKind = Literal["assistant_or_graph"]
AgentToolRuntimeContract = Literal["langgraph_context"]

# Execution strategy remains fixed even when the underlying runtime varies.
AgentExecutionStrategy = Literal["fixed"]


@dataclass(slots=True)
class AgentRuntimeProviderContract:
    provider: AgentRuntimeProviderName
    runtime_kind: AgentRuntimeKind
    session_identifier_kind: AgentRuntimeSessionIdentifierKind
    execution_target_kind: AgentRuntimeExecutionTargetKind
    tool_runtime_contract: AgentToolRuntimeContract
    supports_subagents: bool
    supports_thread_reuse: bool
    sdk_info: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentRuntimeExecutionSnapshot:
    provider: AgentRuntimeProviderName
    session_id: str | None
    execution_target: str | None
    message_count: int
    tool_call_count: int
    model_name: str | None = None
    status: str = "completed"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentExecutionRequest:
    task_id: str
    prompt: str
    model_override: str | None
    timeout_seconds: int
    recursion_limit: int
    subagent_enabled: bool
    query_session_id: str | None = None
    workspace_metadata: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    agent_name: str | None = None
    agent_role: str | None = None
    assistant_id: str | None = None
    thread_id: str | None = None
    graph_id: str | None = None
    # Legacy per-agent overrides are normalized upstream.
    agent_runtime_provider_override: str | None = None


@dataclass(slots=True)
class AgentExecutionResult:
    provider: AgentRuntimeProviderName
    output_text: str | None
    message_count: int
    tool_call_count: int
    thread_id: str | None
    planned_execution_target: str | None = None
    runtime_snapshot: AgentRuntimeExecutionSnapshot | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class AgentRuntimeProvider(Protocol):
    name: AgentRuntimeProviderName

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        """Execute a prompt against the provider runtime."""

    def get_contract(self) -> AgentRuntimeProviderContract:
        """Describe the provider using a provider-neutral runtime contract."""
