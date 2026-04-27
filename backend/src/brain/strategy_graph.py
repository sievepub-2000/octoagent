"""Strategy-fusion graph contracts and guardrails for Brain Core."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Literal

from pydantic import BaseModel, Field

EdgeKind = Literal["precedence", "causal", "feedback_lagged"]
ArbitrationMode = Literal["single_owner", "weighted_vote", "stacked_meta", "policy_gate", "veto"]


class StrategyNode(BaseModel):
    id: str
    title: str
    stage: Literal["observe", "infer", "score", "decide", "execute", "review"]
    produces: list[str] = Field(default_factory=list)
    consumes: list[str] = Field(default_factory=list)


class StrategyEdge(BaseModel):
    source: str
    target: str
    kind: EdgeKind
    lag: int = 0


class OutputArbitration(BaseModel):
    output_name: str
    mode: ArbitrationMode
    owners: list[str] = Field(default_factory=list)


class StrategyGraph(BaseModel):
    nodes: list[StrategyNode] = Field(default_factory=list)
    edges: list[StrategyEdge] = Field(default_factory=list)
    arbitrations: list[OutputArbitration] = Field(default_factory=list)


class StrategyGraphValidationReport(BaseModel):
    valid: bool
    execution_order: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _topological_order(node_ids: list[str], edges: list[tuple[str, str]]) -> tuple[list[str], bool]:
    indegree = {node_id: 0 for node_id in node_ids}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        outgoing[source].append(target)
        indegree[target] += 1

    queue = deque([node_id for node_id, degree in indegree.items() if degree == 0])
    ordered: list[str] = []
    while queue:
        node_id = queue.popleft()
        ordered.append(node_id)
        for target in outgoing[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    return ordered, len(ordered) == len(node_ids)


class StrategyGraphValidator:
    """Validate fusion graphs so strategies cannot silently conflict or loop."""

    def validate(self, graph: StrategyGraph) -> StrategyGraphValidationReport:
        node_map = {node.id: node for node in graph.nodes}
        errors: list[str] = []
        warnings: list[str] = []

        if len(node_map) != len(graph.nodes):
            errors.append("Strategy node IDs must be unique.")

        instantaneous_edges: list[tuple[str, str]] = []
        causal_edges: list[tuple[str, str]] = []

        for edge in graph.edges:
            if edge.source not in node_map or edge.target not in node_map:
                errors.append(f"Edge references unknown node: {edge.source} -> {edge.target}")
                continue
            if edge.kind == "feedback_lagged":
                if edge.lag < 1:
                    errors.append(
                        f"Lagged feedback edge must have lag >= 1: {edge.source} -> {edge.target}"
                    )
            else:
                if edge.lag != 0:
                    warnings.append(
                        f"Non-feedback edge should have lag 0: {edge.source} -> {edge.target}"
                    )
                instantaneous_edges.append((edge.source, edge.target))
                if edge.kind == "causal":
                    causal_edges.append((edge.source, edge.target))

        node_ids = list(node_map.keys())
        execution_order, execution_acyclic = _topological_order(node_ids, instantaneous_edges)
        if not execution_acyclic:
            errors.append("Instantaneous execution graph contains a cycle.")

        _, causal_acyclic = _topological_order(node_ids, causal_edges)
        if not causal_acyclic:
            errors.append("Causal graph contains a cycle. Convert feedback edges to lagged feedback.")

        producers: dict[str, list[str]] = defaultdict(list)
        for node in graph.nodes:
            for output_name in node.produces:
                producers[output_name].append(node.id)

        arbitration_map = {item.output_name: item for item in graph.arbitrations}
        for output_name, owners in producers.items():
            if len(owners) <= 1:
                continue
            arbitration = arbitration_map.get(output_name)
            if arbitration is None:
                errors.append(
                    f"Output '{output_name}' is produced by multiple strategies {owners} without arbitration."
                )
                continue
            missing = sorted(set(owners) - set(arbitration.owners))
            if missing:
                errors.append(
                    f"Arbitration for '{output_name}' does not cover all owners: missing {missing}."
                )
            if arbitration.mode == "single_owner":
                errors.append(
                    f"Output '{output_name}' has multiple producers but arbitration mode is single_owner."
                )
            if arbitration.mode == "weighted_vote":
                warnings.append(
                    f"Output '{output_name}' uses weighted_vote. Prefer stacked_meta or policy_gate for high-risk decisions."
                )

        return StrategyGraphValidationReport(
            valid=len(errors) == 0,
            execution_order=execution_order if len(errors) == 0 else [],
            errors=errors,
            warnings=warnings,
        )
