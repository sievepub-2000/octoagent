from __future__ import annotations

from src.storage.skill_evolution import trust_score


def test_trust_observer_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SKILL_TRUST_OBSERVATION_ENABLED", raising=False)

    assert trust_score.is_enabled() is True


def test_trust_observer_can_be_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SKILL_TRUST_OBSERVATION_ENABLED", "0")

    written = trust_score.record_invocation(
        "skill_example",
        success=True,
        latency_ms=12.5,
        ledger_path=tmp_path / "trust_scores.jsonl",
    )

    assert written is False


def test_trust_score_summary_reads_ledger(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SKILL_TRUST_OBSERVATION_ENABLED", "1")
    ledger = tmp_path / "trust_scores.jsonl"

    assert trust_score.record_invocation("skill_example", success=True, latency_ms=10, ledger_path=ledger)
    assert trust_score.record_invocation("skill_example", success=False, latency_ms=20, ledger_path=ledger)

    summary = trust_score.summarize_scores(ledger)

    assert summary["skill_example"]["total"] == 2
    assert summary["skill_example"]["successes"] == 1
    assert summary["skill_example"]["success_rate"] == 0.5
    assert summary["skill_example"]["p95_latency_ms"] == 10.0
    assert 0 <= summary["skill_example"]["trust_score"] <= 1
