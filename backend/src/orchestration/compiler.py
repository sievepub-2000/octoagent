"""Compiled task-graph generation for orchestration."""

from __future__ import annotations

from .card_templates import OrchestrationCardTemplateFactory
from .contracts import BudgetPolicy, CompiledTaskGraph, RuntimeBinding, RuntimeHandoff


class OrchestrationCompiler:
    """Compile Brain responses into orchestration graphs."""

    def __init__(self):
        self._cards = OrchestrationCardTemplateFactory()

    def get_seed_graph(self) -> CompiledTaskGraph:
        return CompiledTaskGraph(
            graph_id="compiled-graph-seed",
            task_id=None,
            source_plan_summary=(
                "Compile a Brain plan into a task graph with agent, browser, research, and review cards."
            ),
            cards=[
                self._cards.create(
                    card_id="card-plan-review",
                    title="Review normalized plan",
                    kind="review",
                    runtime_binding=RuntimeBinding(
                        binding_id="binding-plan-review",
                        kind="review",
                        target="operator_review",
                        state="ready",
                        notes=["Verify task graph before side effects."],
                    ),
                    ui={"variant": "review", "icon": "shield-check"},
                ),
                self._cards.create(
                    card_id="card-browser-discovery",
                    title="Browser discovery pass",
                    kind="browser",
                    dependencies=["card-plan-review"],
                    runtime_binding=RuntimeBinding(
                        binding_id="binding-browser-discovery",
                        kind="browser",
                        target="agent_browser",
                        state="planned",
                        notes=["Uses accessibility snapshot oriented flow."],
                    ),
                    ui={"variant": "browser", "icon": "globe"},
                ),
                self._cards.create(
                    card_id="card-research-loop",
                    title="Bounded experiment loop",
                    kind="research",
                    dependencies=["card-plan-review"],
                    runtime_binding=RuntimeBinding(
                        binding_id="binding-research-loop",
                        kind="research",
                        target="program-bounded-autoresearch",
                        state="planned",
                        notes=["Trials operate within a fixed iteration and time budget."],
                    ),
                    ui={"variant": "research", "icon": "search"},
                ),
            ],
            handoffs=[
                RuntimeHandoff(
                    handoff_id="handoff-chat-to-agent",
                    source="agent_chat",
                    destination="agent_runtime",
                    summary="Promote reviewed operator chat into a live task-scoped agent session.",
                    status="ready",
                ),
                RuntimeHandoff(
                    handoff_id="handoff-brain-to-research",
                    source="brain",
                    destination="research_runtime",
                    summary="Convert experimentation branches into bounded research trials.",
                    status="planned",
                ),
            ],
            budget_policy=BudgetPolicy(
                token_budget=120000,
                tool_call_budget=48,
                browser_step_budget=24,
                research_trial_budget=3,
                approval_mode="soft",
            ),
        )

    def compile_brain_response(self, response, *, task_id: str, mode) -> CompiledTaskGraph:
        cards = [
            self._cards.create(
                card_id=f"{task_id}-review",
                title="Review Brain Recommendation",
                kind="review",
                runtime_binding=RuntimeBinding(
                    binding_id=f"{task_id}-review-binding",
                    kind="review",
                    target=response.execution_contract.next_owner,
                    state="ready" if response.execution_contract.readiness != "blocked" else "blocked",
                    notes=response.decision.rationale or response.execution_contract.notes,
                ),
                ui={"variant": "review", "risk": response.decision.risk_level},
            )
        ]
        handoffs = [
            RuntimeHandoff(
                handoff_id=f"{task_id}-brain-handoff",
                task_id=task_id,
                source="brain",
                destination="agent_runtime",
                summary=response.decision.recommendation,
                status="ready" if response.execution_contract.readiness != "blocked" else "blocked",
            )
        ]

        previous_card_id = cards[0].card_id
        previous_state = cards[0].runtime_binding.state if cards[0].runtime_binding is not None else "ready"
        for index, step in enumerate(response.plan.steps, start=1):
            lowered = f"{step.title} {step.description}".lower()
            kind, target = self._runtime_target_for_step(lowered, response.execution_contract.template)
            dependency_ids = [previous_card_id]
            runtime_state = self._binding_state_for_step(
                dependency_ids=dependency_ids,
                step_status=step.status,
                previous_state=previous_state,
            )
            cards.append(
                self._cards.create(
                    card_id=f"{task_id}-step-{index}",
                    title=step.title,
                    kind=kind,
                    dependencies=dependency_ids,
                    runtime_binding=RuntimeBinding(
                        binding_id=f"{task_id}-binding-{index}",
                        kind=("system" if kind == "tooling" else kind),
                        target=target,
                        state=runtime_state,
                        notes=[
                            step.description,
                            (
                                f"Dependency gate: waits for '{previous_card_id}' before execution."
                                if dependency_ids
                                else "Dependency gate: none."
                            ),
                        ],
                    ),
                    ui={"variant": kind, "sequence": index, "target": target},
                )
            )
            previous_card_id = f"{task_id}-step-{index}"
            previous_state = runtime_state

        for index, checkpoint in enumerate(response.execution_contract.checkpoints, start=1):
            checkpoint_card_id = f"{task_id}-checkpoint-card-{index}"
            checkpoint_state = "blocked" if checkpoint.status == "blocked" else "planned"
            cards.append(
                self._cards.create(
                    card_id=checkpoint_card_id,
                    title=checkpoint.title,
                    kind="checkpoint",
                    dependencies=[previous_card_id],
                    runtime_binding=RuntimeBinding(
                        binding_id=f"{task_id}-checkpoint-binding-{index}",
                        kind="review",
                        target=checkpoint.owner_role or checkpoint.handoff_kind or "review_queue",
                        state=checkpoint_state,
                        notes=[
                            f"Checkpoint phase: {checkpoint.phase}",
                            f"Handoff kind: {checkpoint.handoff_kind}",
                            (
                                f"Next step: {checkpoint.next_step}"
                                if checkpoint.next_step is not None
                                else "Next step: not specified."
                            ),
                        ],
                    ),
                    ui={"variant": "checkpoint", "phase": checkpoint.phase},
                )
            )
            handoffs.append(
                RuntimeHandoff(
                    handoff_id=f"{task_id}-checkpoint-{index}",
                    task_id=task_id,
                    source="task_workspace" if mode != "single" else "brain",
                    destination="review_queue",
                    summary=f"{checkpoint.title} ({checkpoint.phase})",
                    status="ready" if checkpoint.status != "blocked" else "blocked",
                )
            )

        if mode in {"branch", "group"}:
            cards.append(
                self._cards.create(
                    card_id=f"{task_id}-final-review",
                    title="Final Workspace Review",
                    kind="review",
                    dependencies=[previous_card_id],
                    runtime_binding=RuntimeBinding(
                        binding_id=f"{task_id}-final-review-binding",
                        kind="review",
                        target="review_queue",
                        state="planned" if previous_state != "blocked" else "blocked",
                        notes=[
                            "Multi-agent work must converge through final review before claiming completion.",
                            f"Execution mode: {mode}",
                        ],
                    ),
                    ui={"variant": "review.final", "mode": mode},
                )
            )
            handoffs.append(
                RuntimeHandoff(
                    handoff_id=f"{task_id}-final-review-handoff",
                    task_id=task_id,
                    source="task_workspace",
                    destination="review_queue",
                    summary="Route merged workspace result to final review before completion.",
                    status="ready" if previous_state != "blocked" else "blocked",
                )
            )

        return CompiledTaskGraph(
            graph_id=f"compiled-{task_id}",
            task_id=task_id,
            source_plan_summary=response.plan.summary,
            cards=cards,
            handoffs=handoffs,
            budget_policy=BudgetPolicy(
                token_budget=120000 if mode == "single" else 180000,
                tool_call_budget=48 if mode == "single" else 72,
                browser_step_budget=24,
                research_trial_budget=3,
                approval_mode="strict" if response.decision.risk_level == "high" else "soft",
            ),
        )

    def _runtime_target_for_step(self, lowered: str, template: str) -> tuple[str, str]:
        if "research" in lowered or template == "research_review":
            return ("research", "research_runtime")
        if "review" in lowered or "approve" in lowered or "signoff" in lowered:
            return ("review", "operator_review")
        if any(token in lowered for token in ["browser", "page", "web", "url"]):
            return ("browser", "agent_browser")
        if any(token in lowered for token in ["tool", "shell", "command", "system", "file"]):
            return ("tooling", "system_execution")
        return ("agent", "lead_agent")

    def _binding_state_for_step(
        self,
        *,
        dependency_ids: list[str],
        step_status: str,
        previous_state: str,
    ) -> str:
        if step_status == "blocked":
            return "blocked"
        if dependency_ids:
            return "planned" if previous_state != "blocked" else "blocked"
        return "ready"
