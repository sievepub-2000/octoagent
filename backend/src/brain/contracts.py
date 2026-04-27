"""Core contracts for the OctoAgent Brain Core skeleton."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .strategy_graph import StrategyGraph, StrategyGraphValidationReport


class BrainTaskContext(BaseModel):
    thread_id: str | None = Field(default=None)
    user_goal: str = Field(..., description="The normalized goal the brain should reason about.")
    constraints: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    preferred_mode: Literal["plan", "research", "quant", "policy"] = "plan"
    factor_candidates: list[str] = Field(default_factory=list)
    risk_limits: list[str] = Field(default_factory=list)
    memory_hints: list[str] = Field(default_factory=list)


class BrainPlanStep(BaseModel):
    id: str
    title: str
    description: str
    status: Literal["pending", "ready", "blocked"] = "pending"


class BrainPlan(BaseModel):
    summary: str
    steps: list[BrainPlanStep] = Field(default_factory=list)


class BrainAnalysis(BaseModel):
    findings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class BrainModuleReport(BaseModel):
    name: str
    findings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class BrainDecision(BaseModel):
    recommendation: str
    rationale: list[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high"] = "medium"


class BrainApprovalCheckpoint(BaseModel):
    id: str
    title: str
    required: bool = True
    status: Literal["pending", "ready", "blocked"] = "pending"
    phase: Literal["inputs", "review", "approval", "execution"] = "review"
    reason: str | None = None
    handoff_kind: Literal["operator_review", "risk_signoff", "evidence_review", "policy_signoff"] = "operator_review"
    owner_role: Literal["operator", "risk_reviewer", "research_reviewer", "policy_reviewer"] = "operator"
    next_step: str | None = None


class BrainQuantBacktestContract(BaseModel):
    factor_count: int = 0
    evidence_count: int = 0
    risk_guardrail_count: int = 0
    factor_candidates: list[str] = Field(default_factory=list)
    risk_guardrails: list[str] = Field(default_factory=list)
    suggested_universe: Literal["broad_market", "constrained", "undefined"] = "undefined"
    execution_phase: Literal["collect_inputs", "review_inputs", "await_approval", "prepare_execution"] = "collect_inputs"
    next_action: Literal["collect_inputs", "prepare_backtest", "manual_review"] = "collect_inputs"
    approval_handoff: Literal["operator_review", "risk_signoff", "not_ready"] = "not_ready"


class BrainExecutionContract(BaseModel):
    template: Literal["generic_analysis", "quant_backtest", "research_review", "policy_review"]
    readiness: Literal["ready", "review_required", "blocked"] = "review_required"
    current_phase: Literal["inputs", "review", "approval", "execution", "plan"] = "plan"
    next_owner: Literal["operator", "risk_reviewer", "research_reviewer", "policy_reviewer", "system"] = "system"
    memory_context_strength: Literal["none", "light", "strong"] = "none"
    review_intensity: Literal["standard", "heightened"] = "standard"
    suggested_workflow_mode: Literal["task", "branch", "group"] = "task"
    required_inputs: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    checkpoints: list[BrainApprovalCheckpoint] = Field(default_factory=list)
    suggested_runtime_mode: Literal["plan", "task", "workflow"] = "plan"
    notes: list[str] = Field(default_factory=list)
    quant_backtest: BrainQuantBacktestContract | None = None


class BrainBuilderAction(BaseModel):
    id: str
    kind: str
    title: str
    description: str
    auto_apply: bool = False
    status: Literal["ready", "manual", "already_aligned"] = "ready"
    target_field: str | None = None
    patch: dict[str, object] = Field(default_factory=dict)


class BrainBuilderActionModel(BaseModel):
    summary: str
    auto_actions: list[BrainBuilderAction] = Field(default_factory=list)
    manual_actions: list[BrainBuilderAction] = Field(default_factory=list)
    apply_all_patch: dict[str, object] = Field(default_factory=dict)


class BrainModelRecommendation(BaseModel):
    """Inline copy of the model recommendation for the response payload."""

    tier: Literal["heavy", "standard", "light"] = "standard"
    reason: str = ""
    suggested_capabilities: list[str] = Field(default_factory=list)
    fallback_tier: Literal["heavy", "standard", "light"] = "standard"


class BrainResponse(BaseModel):
    plan: BrainPlan
    analysis: BrainAnalysis
    module_reports: list[BrainModuleReport] = Field(default_factory=list)
    decision: BrainDecision
    execution_contract: BrainExecutionContract
    builder_action_model: BrainBuilderActionModel = Field(default_factory=lambda: BrainBuilderActionModel(summary="No builder actions generated."))
    strategy_graph: StrategyGraph
    strategy_validation: StrategyGraphValidationReport
    model_recommendation: BrainModelRecommendation | None = None
