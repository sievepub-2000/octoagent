from types import SimpleNamespace

from src.agents.memory.prompt import format_memory_for_injection
from src.agents.memory.updater import _fact_retention_key
from src.agents.middlewares.memory_middleware import _should_skip_heavy_memory_for_fast_turn


def _message(content: str):
    return SimpleNamespace(content=content, type="human")


def test_explicit_correction_is_never_skipped_as_a_fast_turn() -> None:
    assert not _should_skip_heavy_memory_for_fast_turn(
        runtime_context={"dialogue_route": {"kind": "direct_answer"}, "mode": "flash"},
        user_messages=[_message("纠正一个错误：以后全量检查必须验证真实运行数据源。")],
        assistant_messages=[SimpleNamespace(content="收到", type="ai")],
    )


def test_ordinary_short_direct_answer_can_skip_heavy_review() -> None:
    assert _should_skip_heavy_memory_for_fast_turn(
        runtime_context={"dialogue_route": {"kind": "direct_answer"}, "mode": "flash"},
        user_messages=[_message("现在几点？")],
        assistant_messages=[SimpleNamespace(content="十二点", type="ai")],
    )


def test_durable_preferences_are_promoted_in_injected_context() -> None:
    prompt = format_memory_for_injection(
        {
            "facts": [
                {"id": "context", "content": "User opened a project.", "category": "context", "confidence": 1.0},
                {"id": "preference", "content": "User requires evidence-backed full audits.", "category": "preference", "confidence": 0.9},
            ]
        }
    )

    assert "User Preferences:" in prompt
    assert prompt.index("evidence-backed") < prompt.index("opened a project")


def test_bounded_profile_retains_preferences_before_generic_history() -> None:
    facts = [
        {"content": "A high-confidence generic detail", "category": "knowledge", "confidence": 1.0, "createdAt": "2026-07-15T00:00:00Z"},
        {"content": "Use concise Chinese reports", "category": "preference", "confidence": 0.9, "createdAt": "2026-07-14T00:00:00Z"},
    ]

    retained = sorted(facts, key=_fact_retention_key, reverse=True)[0]

    assert retained["category"] == "preference"
