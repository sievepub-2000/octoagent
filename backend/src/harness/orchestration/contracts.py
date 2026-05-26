"""Contracts for the orchestration plane."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OrchestrationCapability(BaseModel):
    enabled: bool = True
    supports_task_graph_compilation: bool = True
    supports_subagent_handoff: bool = True
    supports_budget_policies: bool = True
    supports_runtime_cards: bool = True
    note: str = "Orchestration owns task graph compilation, runtime routing, and bounded handoff. It does not replace Brain planning."


class PromptModuleProfile(BaseModel):
    module_id: str
    stage: Literal[
        "identity",
        "workflow",
        "context",
        "reminder",
        "compaction",
        "summarization",
        "routing",
        "policy",
    ]
    title: str
    purpose: str
    dynamic_inputs: list[str] = Field(default_factory=list)
    instruction_template: str = ""


class PromptStackProfile(BaseModel):
    profile_id: str
    title: str
    modules: list[PromptModuleProfile] = Field(default_factory=list)
    source_alignment: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BudgetPolicy(BaseModel):
    token_budget: int
    tool_call_budget: int
    browser_step_budget: int
    research_trial_budget: int
    approval_mode: Literal["none", "soft", "strict"] = "soft"


class RuntimeBinding(BaseModel):
    binding_id: str
    kind: Literal["agent", "tooling", "browser", "research", "system", "review"]
    target: str
    state: Literal["planned", "ready", "blocked"] = "planned"
    notes: list[str] = Field(default_factory=list)


class RuntimeHandoff(BaseModel):
    handoff_id: str
    task_id: str | None = None
    source: Literal["brain", "task_workspace", "agent_chat"] = "brain"
    destination: Literal["agent_runtime", "browser_runtime", "research_runtime", "review_queue"] = "agent_runtime"
    summary: str
    status: Literal["planned", "ready", "blocked"] = "planned"


class OrchestrationCard(BaseModel):
    card_id: str
    title: str
    kind: Literal["agent", "tooling", "browser", "research", "checkpoint", "review"]
    dependencies: list[str] = Field(default_factory=list)
    runtime_binding: RuntimeBinding | None = None
    template_id: str = ""
    ui: dict[str, object] = Field(default_factory=dict)


class CompiledTaskGraph(BaseModel):
    graph_id: str
    task_id: str | None = None
    source_plan_summary: str
    cards: list[OrchestrationCard] = Field(default_factory=list)
    handoffs: list[RuntimeHandoff] = Field(default_factory=list)
    budget_policy: BudgetPolicy
