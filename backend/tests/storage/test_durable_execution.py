"""Tests for the dependency-free durable-execution layer.

Covers the three Temporal-inspired guarantees OctoAgent provides on top of
LangGraph: idempotent activities (deterministic replay), explicit saga
compensation on failure, and an auditable replay journal.
"""

from __future__ import annotations

import pytest

from src.storage.workflow.durable_execution import (
    IdempotentRunner,
    Saga,
    SagaAborted,
    StepStatus,
    make_idempotency_key,
)


def test_idempotency_key_is_stable_and_argument_sensitive() -> None:
    k1 = make_idempotency_key("charge", 100, currency="USD")
    k2 = make_idempotency_key("charge", 100, currency="USD")
    k3 = make_idempotency_key("charge", 200, currency="USD")
    assert k1 == k2
    assert k1 != k3
    assert k1.startswith("charge:")


def test_idempotent_runner_executes_once_then_replays() -> None:
    runner = IdempotentRunner()
    calls = {"n": 0}

    def activity() -> int:
        calls["n"] += 1
        return 42

    key = make_idempotency_key("activity")
    first = runner.run(key, activity, name="activity")
    second = runner.run(key, activity, name="activity")

    assert first == 42
    assert second == 42
    # Side effect ran exactly once; the second call replayed the recorded result.
    assert calls["n"] == 1
    assert len(runner.store) == 1


def test_saga_runs_all_steps_and_records_journal() -> None:
    saga = Saga()
    order: list[str] = []

    saga.step("a", lambda: order.append("a") or "ra")
    saga.step("b", lambda: order.append("b") or "rb")

    result = saga.execute()

    assert order == ["a", "b"]
    assert result.completed_steps == ["a", "b"]
    assert result.results == {"a": "ra", "b": "rb"}
    assert saga.journal.statuses() == [StepStatus.COMPLETED, StepStatus.COMPLETED]


def test_saga_compensates_in_reverse_on_failure() -> None:
    saga = Saga()
    events: list[str] = []

    def boom() -> None:
        raise ValueError("step c failed")

    saga.step("a", lambda: events.append("do-a"), compensation=lambda: events.append("undo-a"))
    saga.step("b", lambda: events.append("do-b"), compensation=lambda: events.append("undo-b"))
    saga.step("c", boom, compensation=lambda: events.append("undo-c"))

    with pytest.raises(SagaAborted) as exc_info:
        saga.execute()

    # Forward actions a,b ran; c failed (its compensation must NOT run since its
    # action never succeeded); completed steps roll back in reverse order.
    assert events == ["do-a", "do-b", "undo-b", "undo-a"]
    assert exc_info.value.failed_step == "c"
    journal = exc_info.value.journal.statuses()
    assert journal == [
        StepStatus.COMPLETED,
        StepStatus.COMPLETED,
        StepStatus.FAILED,
        StepStatus.COMPENSATED,
        StepStatus.COMPENSATED,
    ]


def test_saga_shares_runner_for_cross_run_idempotency() -> None:
    runner = IdempotentRunner()
    calls = {"n": 0}

    def make_saga() -> Saga:
        saga = Saga(runner=runner)
        saga.step("charge", lambda: calls.__setitem__("n", calls["n"] + 1) or "ok", key="charge:fixed")
        return saga

    make_saga().execute()
    second = make_saga().execute()

    # The second run replays the recorded result instead of re-charging.
    assert calls["n"] == 1
    assert second.journal.statuses() == [StepStatus.REPLAYED]
