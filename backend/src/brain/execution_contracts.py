"""Execution contract builder for Brain Core responses."""

from __future__ import annotations

from typing import Literal

from .contracts import (
    BrainAnalysis,
    BrainApprovalCheckpoint,
    BrainDecision,
    BrainExecutionContract,
    BrainQuantBacktestContract,
    BrainTaskContext,
)

MemoryContextStrength = Literal["none", "light", "strong"]
ReviewIntensity = Literal["standard", "heightened"]
Readiness = Literal["ready", "review_required", "blocked"]
CurrentPhase = Literal["inputs", "review", "approval", "execution", "plan"]
NextOwner = Literal["operator", "risk_reviewer", "research_reviewer", "policy_reviewer", "system"]
ExecutionPhase = Literal["collect_inputs", "review_inputs", "await_approval", "prepare_execution"]
NextAction = Literal["collect_inputs", "prepare_backtest", "manual_review"]
ApprovalHandoff = Literal["operator_review", "risk_signoff", "not_ready"]


class BrainExecutionContractBuilder:
    """Translate Brain analysis and policy output into an execution template contract."""

    def build(
        self,
        context: BrainTaskContext,
        analysis: BrainAnalysis,
        decision: BrainDecision,
    ) -> BrainExecutionContract:
        if context.preferred_mode == "quant":
            return self._build_quant_contract(context, analysis, decision)
        if context.preferred_mode == "research":
            return self._build_research_contract(context, analysis, decision)
        if context.preferred_mode == "policy":
            return self._build_policy_contract(context, analysis, decision)
        return self._build_generic_contract(context, analysis, decision)

    def _memory_context_strength(
        self,
        context: BrainTaskContext,
    ) -> MemoryContextStrength:
        if len(context.memory_hints) >= 3:
            return "strong"
        if context.memory_hints:
            return "light"
        return "none"

    def _review_intensity(
        self,
        *,
        decision: BrainDecision,
        missing_inputs: list[str],
        memory_context_strength: MemoryContextStrength,
    ) -> ReviewIntensity:
        if missing_inputs or decision.risk_level == "high":
            return "heightened"
        if decision.recommendation.startswith("Require manual review"):
            return "heightened" if memory_context_strength == "none" else "standard"
        return "heightened" if memory_context_strength == "none" else "standard"

    def _memory_contract_note(
        self,
        *,
        memory_context_strength: MemoryContextStrength,
        hint_count: int,
    ) -> str:
        return (
            "Memory context: "
            f"strength={memory_context_strength}, "
            f"hint_count={hint_count}."
        )

    def _build_quant_contract(
        self,
        context: BrainTaskContext,
        analysis: BrainAnalysis,
        decision: BrainDecision,
    ) -> BrainExecutionContract:
        required_inputs = ["evidence", "factor_candidates", "risk_limits"]
        missing_inputs: list[str] = []
        if not context.evidence:
            missing_inputs.append("evidence")
        if not context.factor_candidates:
            missing_inputs.append("factor_candidates")
        if not context.risk_limits:
            missing_inputs.append("risk_limits")

        checkpoints = [
            BrainApprovalCheckpoint(
                id="checkpoint-evidence",
                title="Evidence baseline ready",
                status="ready" if context.evidence else "blocked",
                phase="inputs",
                reason=None if context.evidence else "Backtest framing still lacks evidence.",
                handoff_kind="evidence_review",
                owner_role="research_reviewer",
                next_step="Confirm evidence quality before backtest framing.",
            ),
            BrainApprovalCheckpoint(
                id="checkpoint-risk-budget",
                title="Risk budget declared",
                status="ready" if context.risk_limits else "blocked",
                phase="review",
                reason=None if context.risk_limits else "Quant execution needs explicit risk limits.",
                handoff_kind="risk_signoff",
                owner_role="risk_reviewer",
                next_step="Review risk guardrails and sign off on bounded exposure.",
            ),
            BrainApprovalCheckpoint(
                id="checkpoint-operator",
                title="Operator approval",
                status=(
                    "pending"
                    if decision.recommendation.startswith("Proceed with bounded quant exploration")
                    else "blocked"
                ),
                phase="approval",
                reason=(
                    None
                    if decision.recommendation.startswith("Proceed with bounded quant exploration")
                    else "Execution path is not ready for operator approval yet."
                ),
                handoff_kind="operator_review",
                owner_role="operator",
                next_step="Approve the bounded backtest run or return for revision.",
            ),
        ]

        readiness, execution_phase, next_action, approval_handoff = (
            self._resolve_quant_execution_state(
                missing_inputs=missing_inputs,
                decision=decision,
            )
        )

        current_phase = self._resolve_contract_phase(execution_phase)
        next_owner = self._resolve_contract_owner(approval_handoff)
        memory_context_strength = self._memory_context_strength(context)
        review_intensity = self._review_intensity(
            decision=decision,
            missing_inputs=missing_inputs,
            memory_context_strength=memory_context_strength,
        )

        return BrainExecutionContract(
            template="quant_backtest",
            readiness=readiness,
            current_phase=current_phase,
            next_owner=next_owner,
            memory_context_strength=memory_context_strength,
            review_intensity=review_intensity,
            suggested_workflow_mode="task",
            required_inputs=required_inputs,
            missing_inputs=missing_inputs,
            checkpoints=[
                *checkpoints,
                BrainApprovalCheckpoint(
                    id="checkpoint-memory-context",
                    title="Historical quant assumptions reconciled",
                    status="ready" if context.memory_hints else "pending",
                    phase="review",
                    reason=None if context.memory_hints else "No durable memory hints were supplied for previous quant decisions.",
                    handoff_kind="risk_signoff",
                    owner_role="risk_reviewer",
                    next_step="Verify that current factor and risk framing is consistent with prior runs.",
                ),
            ],
            suggested_runtime_mode="workflow",
            notes=[
                self._format_contract_summary_note(
                    readiness=readiness,
                    current_phase=current_phase,
                    next_owner=next_owner,
                ),
                self._memory_contract_note(
                    memory_context_strength=memory_context_strength,
                    hint_count=len(context.memory_hints),
                ),
                self._format_quant_execution_state_note(
                    execution_phase=execution_phase,
                    next_action=next_action,
                    approval_handoff=approval_handoff,
                ),
                "Use this template for bounded backtest and factor triage workflows.",
                f"Confidence score: {analysis.confidence:.2f}",
            ],
            quant_backtest=BrainQuantBacktestContract(
                factor_count=len(context.factor_candidates),
                evidence_count=len(context.evidence),
                risk_guardrail_count=len(context.risk_limits),
                factor_candidates=context.factor_candidates[:5],
                risk_guardrails=context.risk_limits[:5],
                suggested_universe=(
                    "constrained" if context.constraints or context.risk_limits else "broad_market"
                ),
                execution_phase=execution_phase,
                next_action=next_action,
                approval_handoff=approval_handoff,
            ),
        )

    def _resolve_quant_execution_state(
        self,
        *,
        missing_inputs: list[str],
        decision: BrainDecision,
    ) -> tuple[
        Readiness,
        ExecutionPhase,
        NextAction,
        ApprovalHandoff,
    ]:
        if missing_inputs:
            return ("blocked", "collect_inputs", "collect_inputs", "not_ready")
        if decision.recommendation.startswith("Require manual review"):
            return ("review_required", "review_inputs", "manual_review", "risk_signoff")
        return ("ready", "await_approval", "prepare_backtest", "operator_review")

    def _format_quant_execution_state_note(
        self,
        *,
        execution_phase: ExecutionPhase,
        next_action: NextAction,
        approval_handoff: ApprovalHandoff,
    ) -> str:
        return (
            "Execution state: "
            f"phase={execution_phase}, "
            f"next_action={next_action}, "
            f"approval_handoff={approval_handoff}."
        )

    def _format_contract_summary_note(
        self,
        *,
        readiness: Readiness,
        current_phase: CurrentPhase,
        next_owner: NextOwner,
    ) -> str:
        return (
            "Contract state: "
            f"readiness={readiness}, "
            f"current_phase={current_phase}, "
            f"next_owner={next_owner}."
        )

    def _resolve_contract_phase(
        self,
        execution_phase: ExecutionPhase,
    ) -> CurrentPhase:
        if execution_phase == "collect_inputs":
            return "inputs"
        if execution_phase == "review_inputs":
            return "review"
        if execution_phase == "await_approval":
            return "approval"
        return "execution"

    def _resolve_contract_owner(
        self,
        approval_handoff: ApprovalHandoff,
    ) -> NextOwner:
        if approval_handoff == "operator_review":
            return "operator"
        if approval_handoff == "risk_signoff":
            return "risk_reviewer"
        return "system"

    def _resolve_review_contract_state(
        self,
        *,
        missing_inputs: list[str],
        review_needed: bool,
    ) -> tuple[
        Readiness,
        CurrentPhase,
    ]:
        if missing_inputs:
            return ("blocked", "inputs")
        if review_needed:
            return ("review_required", "review")
        return ("ready", "review")

    def _build_research_contract(
        self,
        context: BrainTaskContext,
        analysis: BrainAnalysis,
        decision: BrainDecision,
    ) -> BrainExecutionContract:
        review_needed = decision.recommendation.startswith("Require manual review")
        missing_inputs = [] if context.evidence else ["evidence"]
        readiness, current_phase = self._resolve_review_contract_state(
            missing_inputs=missing_inputs,
            review_needed=review_needed,
        )
        next_owner: NextOwner = "research_reviewer"
        memory_context_strength = self._memory_context_strength(context)
        review_intensity = self._review_intensity(
            decision=decision,
            missing_inputs=missing_inputs,
            memory_context_strength=memory_context_strength,
        )
        return BrainExecutionContract(
            template="research_review",
            readiness=readiness,
            current_phase=current_phase,
            next_owner=next_owner,
            memory_context_strength=memory_context_strength,
            review_intensity=review_intensity,
            suggested_workflow_mode="branch",
            required_inputs=["evidence"],
            missing_inputs=missing_inputs,
            checkpoints=[
                BrainApprovalCheckpoint(
                    id="checkpoint-research-evidence",
                    title="Research evidence collected",
                    status="ready" if context.evidence else "blocked",
                    phase="review" if context.evidence else "inputs",
                    reason=None if context.evidence else "Research review still lacks evidence.",
                    handoff_kind="evidence_review",
                    owner_role="research_reviewer",
                    next_step="Review evidence quality before synthesis.",
                ),
                BrainApprovalCheckpoint(
                    id="checkpoint-research-memory",
                    title="Cross-session research context reconciled",
                    status="ready" if context.memory_hints else "pending",
                    phase="review",
                    reason=None if context.memory_hints else "Research continuity lacks explicit memory hints.",
                    handoff_kind="evidence_review",
                    owner_role="research_reviewer",
                    next_step="Compare current evidence with prior research context before final synthesis.",
                ),
            ],
            suggested_runtime_mode="workflow",
            notes=[
                self._format_contract_summary_note(
                    readiness=readiness,
                    current_phase=current_phase,
                    next_owner=next_owner,
                ),
                self._memory_contract_note(
                    memory_context_strength=memory_context_strength,
                    hint_count=len(context.memory_hints),
                ),
                f"Confidence score: {analysis.confidence:.2f}",
            ],
        )

    def _build_policy_contract(
        self,
        context: BrainTaskContext,
        analysis: BrainAnalysis,
        decision: BrainDecision,
    ) -> BrainExecutionContract:
        review_needed = decision.recommendation.startswith("Require manual review")
        missing_inputs = [] if context.constraints else ["constraints"]
        readiness, current_phase = self._resolve_review_contract_state(
            missing_inputs=missing_inputs,
            review_needed=review_needed,
        )
        next_owner: NextOwner = "policy_reviewer"
        memory_context_strength = self._memory_context_strength(context)
        review_intensity = self._review_intensity(
            decision=decision,
            missing_inputs=missing_inputs,
            memory_context_strength=memory_context_strength,
        )
        return BrainExecutionContract(
            template="policy_review",
            readiness=readiness,
            current_phase=current_phase,
            next_owner=next_owner,
            memory_context_strength=memory_context_strength,
            review_intensity=review_intensity,
            suggested_workflow_mode="group",
            required_inputs=["constraints"],
            missing_inputs=missing_inputs,
            checkpoints=[
                BrainApprovalCheckpoint(
                    id="checkpoint-policy-constraints",
                    title="Policy constraints declared",
                    status="ready" if context.constraints else "blocked",
                    phase="review" if context.constraints else "inputs",
                    reason=None if context.constraints else "Policy review needs explicit constraints.",
                    handoff_kind="policy_signoff",
                    owner_role="policy_reviewer",
                    next_step="Confirm policy constraints before execution planning.",
                ),
                BrainApprovalCheckpoint(
                    id="checkpoint-policy-memory",
                    title="Policy continuity reconciled",
                    status="ready" if context.memory_hints else "pending",
                    phase="review",
                    reason=None if context.memory_hints else "Policy review lacks durable memory hints from prior decisions.",
                    handoff_kind="policy_signoff",
                    owner_role="policy_reviewer",
                    next_step="Confirm that the active policy constraints match prior durable decisions.",
                ),
            ],
            suggested_runtime_mode="plan",
            notes=[
                self._format_contract_summary_note(
                    readiness=readiness,
                    current_phase=current_phase,
                    next_owner=next_owner,
                ),
                self._memory_contract_note(
                    memory_context_strength=memory_context_strength,
                    hint_count=len(context.memory_hints),
                ),
                f"Confidence score: {analysis.confidence:.2f}",
            ],
        )

    def _build_generic_contract(
        self,
        context: BrainTaskContext,
        analysis: BrainAnalysis,
        decision: BrainDecision,
    ) -> BrainExecutionContract:
        review_needed = decision.recommendation.startswith("Require manual review")
        readiness: Readiness = (
            "review_required" if review_needed else "ready"
        )
        current_phase: CurrentPhase = "plan"
        next_owner: NextOwner = (
            "operator" if review_needed else "system"
        )
        memory_context_strength = self._memory_context_strength(context)
        review_intensity = self._review_intensity(
            decision=decision,
            missing_inputs=[],
            memory_context_strength=memory_context_strength,
        )
        return BrainExecutionContract(
            template="generic_analysis",
            readiness=readiness,
            current_phase=current_phase,
            next_owner=next_owner,
            memory_context_strength=memory_context_strength,
            review_intensity=review_intensity,
            suggested_workflow_mode="task",
            required_inputs=[],
            missing_inputs=[],
            checkpoints=[],
            suggested_runtime_mode="plan",
            notes=[
                self._format_contract_summary_note(
                    readiness=readiness,
                    current_phase=current_phase,
                    next_owner=next_owner,
                ),
                self._memory_contract_note(
                    memory_context_strength=memory_context_strength,
                    hint_count=len(context.memory_hints),
                ),
                f"Confidence score: {analysis.confidence:.2f}",
            ],
        )
