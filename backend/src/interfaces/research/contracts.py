"""Contracts for the research runtime plane."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ResearchLoopTemplate = Literal["bounded_autoresearch", "manual"]
ResearchExperimentStatus = Literal[
    "planned",
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
]
ResearchTrialStatus = Literal[
    "planned",
    "queued",
    "running",
    "completed",
    "failed",
    "discarded",
]


class ResearchRuntimeCapability(BaseModel):
    enabled: bool = True
    supports_experiment_loops: bool = True
    supports_code_mutation: bool = True
    supports_metric_comparison: bool = True
    supports_artifact_persistence: bool = True
    supports_program_instructions: bool = True
    supports_workspace_binding: bool = True
    supports_trial_execution: bool = True
    default_loop_template: ResearchLoopTemplate = "bounded_autoresearch"
    note: str = "Research runtime is contract-first and shaped around bounded experiment loops, proposal instructions, trial comparison, and artifact retention."
    supports_workspace_status_projection: bool = True
    supports_runtime_snapshots: bool = True


class ResearchInstructionProgram(BaseModel):
    instruction_id: str
    title: str
    summary: str
    objective: str
    guardrails: list[str] = Field(default_factory=list)
    iteration_budget: int = 1
    time_budget_minutes: int = 15
    allowed_mutation_roots: list[str] = Field(default_factory=list)
    allowed_tool_classes: list[str] = Field(default_factory=list)


class ResearchExperimentSpec(BaseModel):
    spec_id: str
    title: str
    objective: str
    candidate_files: list[str] = Field(default_factory=list)
    success_metric: str
    max_trials: int = 1
    evaluation_window_minutes: int = 15
    instruction_program_id: str | None = None
    stop_on_promote: bool = True


class ResearchArtifactRef(BaseModel):
    artifact_id: str
    kind: Literal["report", "diff", "metric_log", "checkpoint"]
    label: str
    path: str


class ResearchTrialVerdict(BaseModel):
    outcome: Literal["promote", "discard", "review"]
    rationale: list[str] = Field(default_factory=list)
    metric_delta: dict[str, float] = Field(default_factory=dict)
    confidence: float = 0.0


class ResearchExecutionBudget(BaseModel):
    requested_trials: int = 1
    granted_trials: int = 1
    remaining_trials_after_run: int = 0
    time_budget_minutes: int = 15


class ResearchRuntimeSnapshot(BaseModel):
    total_experiments: int = 0
    active_experiments: int = 0
    completed_experiments: int = 0
    failed_experiments: int = 0
    total_trials: int = 0
    active_trials: int = 0
    experiment_status_counts: dict[str, int] = Field(default_factory=dict)
    trial_status_counts: dict[str, int] = Field(default_factory=dict)
    task_bound_experiments: int = 0
    recent_activity: list[dict[str, Any]] = Field(default_factory=list)


class ResearchExperiment(BaseModel):
    experiment_id: str
    task_id: str | None = None
    goal: str
    status: ResearchExperimentStatus = "planned"
    hypothesis: str | None = None
    success_metric: str | None = None
    instruction_program_id: str | None = None
    source: Literal["task_workspace", "brain", "manual"] = "brain"
    spec: ResearchExperimentSpec | None = None
    trial_count: int = 0
    latest_trial_id: str | None = None
    promoted_trial_id: str | None = None
    last_error: str | None = None
    candidate_files: list[str] = Field(default_factory=list)
    guardrails: list[str] = Field(default_factory=list)
    progress_score: float = 0.0
    created_at: str
    updated_at: str


class ResearchTrial(BaseModel):
    trial_id: str
    experiment_id: str
    title: str
    status: ResearchTrialStatus = "planned"
    summary: str
    metrics: dict[str, float] = Field(default_factory=dict)
    modified_files: list[str] = Field(default_factory=list)
    artifacts: list[ResearchArtifactRef] = Field(default_factory=list)
    verdict: ResearchTrialVerdict | None = None
    iteration_index: int = 0
    budget: ResearchExecutionBudget | None = None
    created_at: str | None = None
    updated_at: str | None = None


class CreateResearchExperimentRequest(BaseModel):
    goal: str
    task_id: str | None = None
    hypothesis: str | None = None
    success_metric: str = "research_progress_score"
    candidate_files: list[str] = Field(default_factory=list)
    max_trials: int = 3
    evaluation_window_minutes: int = 15
    instruction_program_id: str = "program-bounded-autoresearch"
    source: Literal["task_workspace", "brain", "manual"] = "manual"


class RunResearchExperimentRequest(BaseModel):
    requested_trials: int = 1
    stop_on_promote: bool = True


class ResearchExperimentRunResponse(BaseModel):
    experiment: ResearchExperiment
    new_trials: list[ResearchTrial] = Field(default_factory=list)
    runtime_snapshot: ResearchRuntimeSnapshot | None = None


class ResearchExperimentListResponse(BaseModel):
    experiments: list[ResearchExperiment] = Field(default_factory=list)


class ResearchProgramListResponse(BaseModel):
    programs: list[ResearchInstructionProgram] = Field(default_factory=list)


class ResearchRuntimeStatusResponse(BaseModel):
    snapshot: ResearchRuntimeSnapshot
