"""Unit tests for the native StateGraph adapter scaffold."""

from __future__ import annotations

import pytest

from src.storage.workflow.native_state_graph import (
    WORKFLOW_NATIVE_GRAPH_ENV,
    CardEdgeSpec,
    CardNodeSpec,
    FeatureDisabledError,
    compile_native_graph,
    is_native_graph_enabled,
    plan_from_cards,
)


def test_feature_flag_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(WORKFLOW_NATIVE_GRAPH_ENV, raising=False)
    assert is_native_graph_enabled() is False


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes", "on"])
def test_feature_flag_enabled(monkeypatch: pytest.MonkeyPatch, truthy: str) -> None:
    monkeypatch.setenv(WORKFLOW_NATIVE_GRAPH_ENV, truthy)
    assert is_native_graph_enabled() is True


@pytest.mark.parametrize("falsy", ["", "0", "false", "off", "no"])
def test_feature_flag_disabled_values(monkeypatch: pytest.MonkeyPatch, falsy: str) -> None:
    monkeypatch.setenv(WORKFLOW_NATIVE_GRAPH_ENV, falsy)
    assert is_native_graph_enabled() is False


def test_plan_detects_entry_and_joins() -> None:
    nodes = [
        CardNodeSpec(card_id="a", name="A"),
        CardNodeSpec(card_id="b", name="B"),
        CardNodeSpec(card_id="c", name="C"),
        CardNodeSpec(card_id="d", name="D"),
    ]
    edges = [
        CardEdgeSpec(source_card_id="a", target_card_id="b"),
        CardEdgeSpec(source_card_id="a", target_card_id="c"),
        CardEdgeSpec(source_card_id="b", target_card_id="d"),
        CardEdgeSpec(source_card_id="c", target_card_id="d"),
    ]
    plan = plan_from_cards(nodes, edges)
    assert plan.entry_card_id == "a"
    assert plan.join_node_ids == ["d"]


def test_compile_requires_feature_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(WORKFLOW_NATIVE_GRAPH_ENV, raising=False)
    plan = plan_from_cards([CardNodeSpec(card_id="x", name="X")], [])
    with pytest.raises(FeatureDisabledError):
        compile_native_graph(plan)


def test_compile_with_flag_runs_linear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(WORKFLOW_NATIVE_GRAPH_ENV, "1")
    nodes = [
        CardNodeSpec(card_id="a", name="A"),
        CardNodeSpec(card_id="b", name="B"),
    ]
    edges = [CardEdgeSpec(source_card_id="a", target_card_id="b")]
    plan = plan_from_cards(nodes, edges)

    calls: list[str] = []

    def executor(spec, _state):
        calls.append(spec.card_id)
        return {"card_id": spec.card_id, "status": "ok"}

    graph = compile_native_graph(plan, node_executor=executor)
    final_state = graph.invoke({})
    assert calls == ["a", "b"]
    assert final_state["last_card_id"] == "b"
    assert set(final_state["outputs"]) == {"a", "b"}


def test_plan_summarize_is_data_only() -> None:
    plan = plan_from_cards(
        [CardNodeSpec(card_id="x", name="X", agent_id="research")],
        [],
    )
    summary = plan.summarize()
    assert summary == {
        "nodes": [{"id": "x", "name": "X", "agent": "research"}],
        "edges": [],
        "entry": "x",
        "joins": [],
    }
