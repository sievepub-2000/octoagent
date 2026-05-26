"""Card-graph → native LangGraph StateGraph adapter (FEATURE-FLAGGED).

This module is **not wired into the default execution path**. It exists as a
forward-compatible scaffold so that an opt-in native LangGraph subgraph runner
can be developed and validated incrementally without disturbing the existing
TaskWorkspaceExecutionController → MessageExecutor pipeline.

Activate by setting environment variable ``WORKFLOW_NATIVE_GRAPH=1``.
When the flag is off (default), all public helpers either no-op or raise a
clear ``FeatureDisabledError``; nothing else in the codebase imports this
module today.

Design notes (matches WORKFLOW_GRAPH_REDESIGN.md Phase 1+2 goals):
- Each card becomes a graph node ``card::<id>`` that delegates to the existing
  agent runtime executor for that card.
- Card-graph edges (``CardGraphEdge``) become typed graph edges; conditional
  edges fall back to ``add_edge`` when no condition is present.
- A ``join`` node is inserted whenever a card has >=2 incoming edges so that
  parallel branches in "group" mode rendezvous before the next card.
- State schema is intentionally narrow to avoid leaking card-graph internals
  into LangGraph checkpoints prematurely.

Status: Phase 0 scaffold. Real execution wiring is deferred until the
feature flag is exercised in staging.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


WORKFLOW_NATIVE_GRAPH_ENV = "WORKFLOW_NATIVE_GRAPH"


class FeatureDisabledError(RuntimeError):
    """Raised when a native-graph helper is invoked while the feature is off."""


def is_native_graph_enabled() -> bool:
    """Return ``True`` only when ``WORKFLOW_NATIVE_GRAPH=1`` is set in the env.

    Any other value (unset, ``0``, ``false``) keeps the flag disabled.
    """
    value = os.getenv(WORKFLOW_NATIVE_GRAPH_ENV, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CardNodeSpec:
    """Minimal projection of a workflow card needed to build a graph node."""

    card_id: str
    name: str
    agent_id: str | None = None
    skill: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CardEdgeSpec:
    """Projection of a card-graph edge."""

    source_card_id: str
    target_card_id: str
    condition_key: str | None = None  # reserved for typed-edge contracts


@dataclass
class NativeGraphPlan:
    """Static plan produced from a card-graph projection.

    Pure data; no LangGraph imports here so callers can preview the plan
    without paying the StateGraph compilation cost.
    """

    nodes: list[CardNodeSpec]
    edges: list[CardEdgeSpec]
    entry_card_id: str | None = None
    join_node_ids: list[str] = field(default_factory=list)

    def node_id(self, card_id: str) -> str:
        return f"card__{card_id}"

    def summarize(self) -> dict[str, Any]:
        return {
            "nodes": [{"id": n.card_id, "name": n.name, "agent": n.agent_id} for n in self.nodes],
            "edges": [{"src": e.source_card_id, "dst": e.target_card_id} for e in self.edges],
            "entry": self.entry_card_id,
            "joins": list(self.join_node_ids),
        }


def plan_from_cards(
    nodes: list[CardNodeSpec],
    edges: list[CardEdgeSpec],
    *,
    entry_card_id: str | None = None,
) -> NativeGraphPlan:
    """Build a ``NativeGraphPlan`` from card/edge projections.

    Detects nodes with >=2 in-degree and records them as join points so a
    future compiler step can insert barrier nodes for parallel branches.
    Does not require the feature flag (planning is always safe; only
    compilation/execution is gated).
    """
    indeg: dict[str, int] = {n.card_id: 0 for n in nodes}
    for edge in edges:
        indeg[edge.target_card_id] = indeg.get(edge.target_card_id, 0) + 1
    joins = sorted(card_id for card_id, deg in indeg.items() if deg >= 2)

    resolved_entry = entry_card_id
    if resolved_entry is None:
        candidates = [card_id for card_id, deg in indeg.items() if deg == 0]
        resolved_entry = candidates[0] if candidates else (nodes[0].card_id if nodes else None)

    return NativeGraphPlan(
        nodes=list(nodes),
        edges=list(edges),
        entry_card_id=resolved_entry,
        join_node_ids=joins,
    )


def compile_native_graph(
    plan: NativeGraphPlan,
    *,
    node_executor: Callable[[CardNodeSpec, dict[str, Any]], dict[str, Any]] | None = None,
) -> Any:
    """Compile ``plan`` into a runnable LangGraph ``StateGraph``.

    This is the only function that actually imports ``langgraph`` and that
    the feature flag gates. ``node_executor`` is the per-card executor the
    runtime injects; when omitted, nodes default to a no-op identity step
    so unit tests can validate graph topology without a model server.
    """
    if not is_native_graph_enabled():
        raise FeatureDisabledError(f"Native workflow graph disabled. Set {WORKFLOW_NATIVE_GRAPH_ENV}=1 to enable.")

    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    class _GraphState(TypedDict, total=False):
        outputs: dict[str, Any]
        last_card_id: str | None

    builder: StateGraph = StateGraph(_GraphState)

    def _make_node(spec: CardNodeSpec) -> Callable[[_GraphState], _GraphState]:
        executor = node_executor

        def _run(state: _GraphState) -> _GraphState:
            outputs = dict(state.get("outputs") or {})
            if executor is not None:
                result = executor(spec, state) or {}
            else:
                result = {"card_id": spec.card_id, "status": "noop"}
            outputs[spec.card_id] = result
            return {"outputs": outputs, "last_card_id": spec.card_id}

        return _run

    for node in plan.nodes:
        builder.add_node(plan.node_id(node.card_id), _make_node(node))

    if plan.entry_card_id:
        builder.add_edge(START, plan.node_id(plan.entry_card_id))

    out_edges: dict[str, list[str]] = {}
    for edge in plan.edges:
        out_edges.setdefault(edge.source_card_id, []).append(edge.target_card_id)
        builder.add_edge(plan.node_id(edge.source_card_id), plan.node_id(edge.target_card_id))

    terminal_card_ids = [n.card_id for n in plan.nodes if not out_edges.get(n.card_id)]
    for terminal_card_id in terminal_card_ids:
        builder.add_edge(plan.node_id(terminal_card_id), END)

    logger.info(
        "native_state_graph compiled: nodes=%d edges=%d joins=%d entry=%s",
        len(plan.nodes),
        len(plan.edges),
        len(plan.join_node_ids),
        plan.entry_card_id,
    )
    return builder.compile()


__all__ = [
    "CardEdgeSpec",
    "CardNodeSpec",
    "FeatureDisabledError",
    "NativeGraphPlan",
    "WORKFLOW_NATIVE_GRAPH_ENV",
    "compile_native_graph",
    "is_native_graph_enabled",
    "plan_from_cards",
    "project_workspace_card_graph",
]


def project_workspace_card_graph(workspace) -> NativeGraphPlan:
    """Project a TaskWorkspace.card_graph into a planning-time NativeGraphPlan.

    Pure data; safe to call at any time (no LangGraph imports, no env flag
    required). Used by the auto-execute controller in shadow mode to log
    the would-be native-graph topology without affecting execution.
    """
    cards = []
    edges = []
    graph = getattr(workspace, "card_graph", None)
    if graph is None:
        return plan_from_cards([], [])
    for card in getattr(graph, "nodes", []) or []:
        meta = getattr(card, "metadata", {}) or {}
        cards.append(
            CardNodeSpec(
                card_id=getattr(card, "card_id", "") or "",
                name=getattr(card, "title", None) or getattr(card, "name", None) or getattr(card, "card_id", "?"),
                agent_id=getattr(card, "agent_id", None),
                skill=getattr(card, "skill", None),
                metadata=dict(meta) if isinstance(meta, dict) else {},
            )
        )
    for edge in getattr(graph, "edges", []) or []:
        edges.append(
            CardEdgeSpec(
                source_card_id=getattr(edge, "source_card_id", "") or "",
                target_card_id=getattr(edge, "target_card_id", "") or "",
            )
        )
    return plan_from_cards(cards, edges)
