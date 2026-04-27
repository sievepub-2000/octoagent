"""Planner module for the Brain Core skeleton."""

from __future__ import annotations

from .contracts import BrainPlan, BrainPlanStep, BrainTaskContext
from .strategy_graph import OutputArbitration, StrategyEdge, StrategyGraph, StrategyNode


class BrainPlanner:
    """Create a minimal structured plan from normalized user intent."""

    def _status_for_required_inputs(self, values: list[str], *, ready_when_present: bool = False) -> str:
        if not values:
            return "blocked"
        return "ready" if ready_when_present else "pending"

    def _describe_missing_input(self, *, base: str, values: list[str], missing_label: str) -> str:
        if values:
            return base
        return f"{base} Missing required input: {missing_label}."

    def _score_node_ids_for_mode(self, context: BrainTaskContext) -> list[str]:
        if context.preferred_mode == "quant":
            return ["score_fast", "score_safe", "score_quant"]
        if context.preferred_mode == "research":
            return ["score_fast", "score_safe", "score_causal"]
        if context.preferred_mode == "policy":
            return ["score_safe", "score_policy"]
        return ["score_fast", "score_safe"]

    def build_plan(self, context: BrainTaskContext) -> BrainPlan:
        steps = [
            BrainPlanStep(
                id="brain-step-1",
                title="Clarify target",
                description=f"Confirm the target outcome for: {context.user_goal}",
                status="ready",
            ),
            BrainPlanStep(
                id="brain-step-2",
                title="Collect evidence",
                description=self._describe_missing_input(
                    base="Gather the minimum evidence needed before execution.",
                    values=context.evidence,
                    missing_label="evidence",
                ),
                status=self._status_for_required_inputs(
                    context.evidence,
                    ready_when_present=True,
                ),
            ),
            BrainPlanStep(
                id="brain-step-3",
                title="Choose execution path",
                description="Select the safest execution path based on evidence and constraints.",
                status="pending",
            ),
        ]
        if context.preferred_mode == "quant":
            steps.insert(
                2,
                BrainPlanStep(
                    id="brain-step-quant-factors",
                    title="Triage factors",
                    description=self._describe_missing_input(
                        base="Rank factor candidates, remove weak signals, and define the first backtest slice.",
                        values=context.factor_candidates,
                        missing_label="factor_candidates",
                    ),
                    status=self._status_for_required_inputs(context.factor_candidates),
                ),
            )
            steps.append(
                BrainPlanStep(
                    id="brain-step-quant-risk",
                    title="Set quant guardrails",
                    description=self._describe_missing_input(
                        base="Translate risk limits into a bounded execution and review budget.",
                        values=context.risk_limits,
                        missing_label="risk_limits",
                    ),
                    status=self._status_for_required_inputs(context.risk_limits),
                )
            )
        return BrainPlan(summary=f"Structured plan for: {context.user_goal}", steps=steps)

    def build_strategy_graph(self, context: BrainTaskContext) -> StrategyGraph:
        score_node_ids = self._score_node_ids_for_mode(context)

        nodes = [
            StrategyNode(
                id="observe",
                title="Observe",
                stage="observe",
                produces=["features", "constraints_snapshot"],
            ),
            StrategyNode(
                id="memory_reasoner",
                title="Memory Reasoner",
                stage="infer",
                consumes=["features"],
                produces=["memory_context"],
            ),
            StrategyNode(
                id="infer",
                title="Infer",
                stage="infer",
                consumes=["features", "memory_context"],
                produces=["context_hypothesis"],
            ),
        ]

        if context.preferred_mode in {"research", "policy"}:
            nodes.append(
                StrategyNode(
                    id="causal_map",
                    title="Causal Map",
                    stage="infer",
                    consumes=["features", "context_hypothesis", "memory_context"],
                    produces=["causal_hypothesis"],
                )
            )

        for node_id in score_node_ids:
            consumes = ["features", "context_hypothesis", "memory_context"]
            if node_id in {"score_causal", "score_policy"}:
                consumes.append("causal_hypothesis")
            if node_id == "score_quant":
                consumes.append("factor_candidates")
            nodes.append(
                StrategyNode(
                    id=node_id,
                    title=node_id.replace("_", " ").title(),
                    stage="score",
                    consumes=consumes,
                    produces=["candidate_signal"],
                )
            )

        nodes.extend(
            [
                StrategyNode(
                    id="decide",
                    title="Decide",
                    stage="decide",
                    consumes=["candidate_signal", "constraints_snapshot", "risk_budget"],
                    produces=["allocation_decision"],
                ),
                StrategyNode(
                    id="risk_gate",
                    title="Risk Gate",
                    stage="decide",
                    consumes=["allocation_decision", "risk_budget"],
                    produces=["approved_allocation"],
                ),
                StrategyNode(
                    id="execute",
                    title="Execute",
                    stage="execute",
                    consumes=["approved_allocation"],
                    produces=["execution_report"],
                ),
                StrategyNode(
                    id="review",
                    title="Review",
                    stage="review",
                    consumes=["execution_report"],
                    produces=["review_notes"],
                ),
            ]
        )

        edges = [
            StrategyEdge(source="observe", target="memory_reasoner", kind="precedence"),
            StrategyEdge(source="memory_reasoner", target="infer", kind="causal"),
            StrategyEdge(source="observe", target="infer", kind="precedence"),
            StrategyEdge(source="infer", target="decide", kind="causal"),
            StrategyEdge(source="decide", target="risk_gate", kind="precedence"),
            StrategyEdge(source="risk_gate", target="execute", kind="precedence"),
            StrategyEdge(source="execute", target="review", kind="precedence"),
            StrategyEdge(source="review", target="observe", kind="feedback_lagged", lag=1),
        ]
        if context.preferred_mode in {"research", "policy"}:
            edges.append(StrategyEdge(source="infer", target="causal_map", kind="causal"))
        for node_id in score_node_ids:
            edges.append(StrategyEdge(source="observe", target=node_id, kind="precedence"))
            edges.append(StrategyEdge(source="infer", target=node_id, kind="causal"))
            if node_id in {"score_causal", "score_policy"}:
                edges.append(StrategyEdge(source="causal_map", target=node_id, kind="causal"))
            edges.append(StrategyEdge(source=node_id, target="decide", kind="causal"))

        arbitrations = [
            OutputArbitration(
                output_name="candidate_signal",
                mode="stacked_meta",
                owners=score_node_ids,
            ),
            OutputArbitration(
                output_name="allocation_decision",
                mode="policy_gate",
                owners=["decide"],
            ),
            OutputArbitration(
                output_name="approved_allocation",
                mode="veto",
                owners=["risk_gate"],
            ),
        ]

        if context.preferred_mode == "policy":
            arbitrations.append(
                OutputArbitration(
                    output_name="execution_report",
                    mode="veto",
                    owners=["execute"],
                )
            )

        return StrategyGraph(nodes=nodes, edges=edges, arbitrations=arbitrations)
