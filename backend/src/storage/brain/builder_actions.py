"""Builder action model generation for Brain -> workflow builder alignment."""

from __future__ import annotations

from typing import Any, Literal

from .contracts import (
    BrainAnalysis,
    BrainBuilderAction,
    BrainBuilderActionModel,
    BrainDecision,
    BrainExecutionContract,
    BrainTaskContext,
)

ExecutionTemplate = Literal[
    "generic_analysis",
    "quant_backtest",
    "research_review",
    "policy_review",
]
PreferredMode = Literal["plan", "research", "quant", "policy"]


class BrainBuilderActionModelBuilder:
    """Translate Brain planning output into workflow-builder actions."""

    def build(
        self,
        context: BrainTaskContext,
        analysis: BrainAnalysis,
        decision: BrainDecision,
        execution_contract: BrainExecutionContract,
    ) -> BrainBuilderActionModel:
        auto_actions: list[BrainBuilderAction] = []
        manual_actions: list[BrainBuilderAction] = []

        current_workflow_mode = self._read_constraint(context.constraints, "workflow_mode") or "task"
        current_on_final_failure = self._read_constraint(context.constraints, "on_final_failure")
        current_max_total_steps = self._read_constraint(context.constraints, "max_total_steps")
        suggested_brain_mode = self._brain_mode_for_template(execution_contract.template)

        if current_workflow_mode != execution_contract.suggested_workflow_mode:
            auto_actions.append(
                BrainBuilderAction(
                    id="set-workflow-mode",
                    kind="set_workflow_mode",
                    title="Align workflow mode",
                    description=(f"Switch workflow mode from {current_workflow_mode} to {execution_contract.suggested_workflow_mode} to match the Brain contract."),
                    auto_apply=True,
                    patch={"mode": execution_contract.suggested_workflow_mode},
                )
            )

        if context.preferred_mode != suggested_brain_mode:
            auto_actions.append(
                BrainBuilderAction(
                    id="set-brain-mode",
                    kind="set_brain_mode",
                    title="Align Brain mode",
                    description=(f"Switch preferred Brain mode to {suggested_brain_mode} based on the {execution_contract.template} contract template."),
                    auto_apply=True,
                    patch={"brainConfig": {"preferredMode": suggested_brain_mode}},
                )
            )

        failure_policy_patch = self._failure_policy_patch(execution_contract, decision)
        suggested_on_final_failure = failure_policy_patch["failurePolicy"]["onFinalFailure"]
        suggested_max_total_steps = failure_policy_patch["failurePolicy"]["maxTotalSteps"]
        if current_on_final_failure != suggested_on_final_failure or current_max_total_steps != str(suggested_max_total_steps):
            auto_actions.append(
                BrainBuilderAction(
                    id="align-failure-policy",
                    kind="set_failure_policy",
                    title="Align failure policy",
                    description="Apply Brain-derived bounded failure and review guardrails.",
                    auto_apply=True,
                    patch=failure_policy_patch,
                )
            )

        mode_specific_patch = self._mode_specific_patch(execution_contract)
        if mode_specific_patch:
            auto_actions.append(
                BrainBuilderAction(
                    id="configure-builder-shape",
                    kind="configure_builder_shape",
                    title="Apply builder shape",
                    description="Seed the workflow structure that best matches the current Brain execution contract.",
                    auto_apply=True,
                    patch=mode_specific_patch,
                )
            )

        if execution_contract.memory_context_strength != "none" and not context.memory_hints:
            manual_actions.append(
                BrainBuilderAction(
                    id="supply-memory-hints",
                    kind="resolve_missing_input",
                    title="Add memory hints",
                    description="Brain expects durable memory context, but the workflow builder currently has no memory hints.",
                    auto_apply=False,
                    target_field="memory_hints",
                )
            )

        for missing_input in execution_contract.missing_inputs:
            manual_actions.append(
                BrainBuilderAction(
                    id=f"resolve-{missing_input}",
                    kind="resolve_missing_input",
                    title=f"Resolve missing input: {missing_input}",
                    description=self._manual_resolution_description(missing_input),
                    auto_apply=False,
                    target_field=missing_input,
                )
            )

        if execution_contract.checkpoints:
            pending_required = [checkpoint.title for checkpoint in execution_contract.checkpoints if checkpoint.required and checkpoint.status != "ready"]
            if pending_required:
                manual_actions.append(
                    BrainBuilderAction(
                        id="review-checkpoints",
                        kind="review_checkpoints",
                        title="Review approval checkpoints",
                        description=("The workflow still has unresolved approval gates: " + "; ".join(pending_required[:3])),
                        auto_apply=False,
                        target_field="checkpoints",
                    )
                )

        apply_all_patch = self._merge_patches([action.patch for action in auto_actions if action.patch])

        summary = f"Brain generated {len(auto_actions)} auto-applicable builder actions and {len(manual_actions)} manual follow-ups for the {execution_contract.template} contract."

        return BrainBuilderActionModel(
            summary=summary,
            auto_actions=auto_actions,
            manual_actions=manual_actions,
            apply_all_patch=apply_all_patch,
        )

    def _brain_mode_for_template(
        self,
        template: ExecutionTemplate,
    ) -> PreferredMode:
        return {
            "quant_backtest": "quant",
            "research_review": "research",
            "policy_review": "policy",
            "generic_analysis": "plan",
        }[template]

    def _failure_policy_patch(
        self,
        execution_contract: BrainExecutionContract,
        decision: BrainDecision,
    ) -> dict[str, Any]:
        if execution_contract.readiness == "blocked":
            return {
                "failurePolicy": {
                    "maxStepAttempts": 2,
                    "maxNoProgressRounds": 1,
                    "maxTotalSteps": 6,
                    "onFinalFailure": "ask_user",
                }
            }
        if decision.risk_level == "high" or execution_contract.review_intensity == "heightened":
            return {
                "failurePolicy": {
                    "maxStepAttempts": 2,
                    "maxNoProgressRounds": 1,
                    "maxTotalSteps": 8,
                    "onFinalFailure": "ask_user",
                }
            }
        if execution_contract.template == "quant_backtest":
            return {
                "failurePolicy": {
                    "maxStepAttempts": 3,
                    "maxNoProgressRounds": 2,
                    "maxTotalSteps": 10,
                    "onFinalFailure": "fallback",
                }
            }
        return {
            "failurePolicy": {
                "maxStepAttempts": 3,
                "maxNoProgressRounds": 2,
                "maxTotalSteps": 8,
                "onFinalFailure": "fallback",
            }
        }

    def _mode_specific_patch(
        self,
        execution_contract: BrainExecutionContract,
    ) -> dict[str, Any]:
        if execution_contract.suggested_workflow_mode == "task":
            return {
                "agents": self._task_agents_for_template(execution_contract.template),
                "route": self._task_route_for_template(execution_contract.template),
            }
        if execution_contract.suggested_workflow_mode == "branch":
            return {
                "agents": ["lead_agent", "researcher", "coder", "reviewer"],
                "branches": self._branch_suggestions_for_template(execution_contract.template),
            }
        return {
            "agents": ["lead_agent", "policy_reviewer", "reviewer"],
            "collaborationStyle": ("deep_review" if execution_contract.review_intensity == "heightened" else "balanced"),
        }

    def _task_agents_for_template(
        self,
        template: ExecutionTemplate,
    ) -> list[str]:
        if template == "quant_backtest":
            return ["lead_agent", "researcher", "coder", "reviewer"]
        if template == "research_review":
            return ["lead_agent", "researcher", "reviewer"]
        if template == "policy_review":
            return ["lead_agent", "policy_reviewer", "reviewer"]
        return ["lead_agent", "executor", "reviewer"]

    def _task_route_for_template(
        self,
        template: ExecutionTemplate,
    ) -> list[str]:
        if template == "quant_backtest":
            return ["lead_agent", "researcher", "coder", "reviewer", "lead_agent"]
        if template == "research_review":
            return ["lead_agent", "researcher", "reviewer", "lead_agent"]
        if template == "policy_review":
            return ["lead_agent", "policy_reviewer", "reviewer", "lead_agent"]
        return ["lead_agent", "executor", "lead_agent"]

    def _branch_suggestions_for_template(
        self,
        template: ExecutionTemplate,
    ) -> list[dict[str, str]]:
        if template == "research_review":
            return [
                {
                    "id": "brain-branch-evidence",
                    "agentName": "researcher",
                    "responsibility": "Collect and synthesize evidence",
                },
                {
                    "id": "brain-branch-implementation",
                    "agentName": "coder",
                    "responsibility": "Produce an implementation or remediation candidate",
                },
                {
                    "id": "brain-branch-review",
                    "agentName": "reviewer",
                    "responsibility": "Review evidence quality and residual risks",
                },
            ]
        return [
            {
                "id": "brain-branch-fast",
                "agentName": "researcher",
                "responsibility": "Produce the fast-path analysis branch",
            },
            {
                "id": "brain-branch-safe",
                "agentName": "reviewer",
                "responsibility": "Stress test assumptions and risk controls",
            },
        ]

    def _manual_resolution_description(self, missing_input: str) -> str:
        if missing_input == "evidence":
            return "Add a concrete deliverable, sample output, or validation target in Expected Output."
        if missing_input == "factor_candidates":
            return "List the candidate factors or hypotheses that should be tested."
        if missing_input == "risk_limits":
            return "Declare explicit drawdown, leverage, exposure, or approval guardrails."
        if missing_input == "constraints":
            return "Add the policy or execution constraints that the workflow must obey."
        return f"Provide the missing input: {missing_input}."

    def _read_constraint(self, constraints: list[str], prefix: str) -> str | None:
        expected_prefix = f"{prefix}:"
        for item in constraints:
            if item.startswith(expected_prefix):
                return item[len(expected_prefix) :].strip() or None
        return None

    def _merge_patches(self, patches: list[dict[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for patch in patches:
            merged = self._deep_merge(merged, patch)
        return merged

    def _deep_merge(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        merged = dict(left)
        for key, value in right.items():
            existing = merged.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                merged[key] = self._deep_merge(existing, value)
            else:
                merged[key] = value
        return merged
