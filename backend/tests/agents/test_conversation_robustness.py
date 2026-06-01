"""Regression tests locking in the Phase-3 conversation-robustness fix.

Root cause that these guard against: ``ClientCommandMiddleware`` used to bypass
the model for ``current_snapshot`` (real-time/weather) turns by returning a
pre-baked or parroted answer. When snapshots were absent the small flash model
parroted a previous assistant turn (e.g. answering 北海道 with the earlier 大阪
reply) and emitted degenerate repeated preambles ("让我重新获取 ..." x5).

The fix has two invariants, both asserted here so the anti-pattern cannot
silently regress:

1. ``current_snapshot`` turns NEVER short-circuit the model — every city /
   real-time question must flow through the model + tool loop on its own turn.
2. ``ConversationIntegrityMiddleware`` deterministically collapses degenerate
   repeated output in the final answer.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.middlewares.client_command_middleware import _build_instant_client_answer
from src.agents.middlewares.conversation_integrity_middleware import (
    ConversationIntegrityMiddleware,
    _sanitize,
)

# --- Invariant 1: current_snapshot must not bypass the model -----------------

_CURRENT_SNAPSHOT = {"dialogue_route": {"kind": "current_snapshot"}}


@pytest.mark.parametrize(
    "user_text",
    [
        "大阪今天天气怎么样",
        "北海道现在天气如何",
        "冰岛雷克雅未克今天冷吗",
        "济南今天的天气",
        "北京明天会下雨吗",
        "现在几点了",  # non-weather real-time snapshot
    ],
)
def test_current_snapshot_never_short_circuits_model(user_text: str) -> None:
    messages = [HumanMessage(content=user_text)]
    answer = _build_instant_client_answer(messages, _CURRENT_SNAPSHOT)
    # None => the middleware defers to the model + tool loop (fresh, grounded
    # answer for THIS turn) instead of returning a fabricated/parroted reply.
    assert answer is None


def test_control_command_still_fast_paths() -> None:
    messages = [HumanMessage(content="/status")]
    answer = _build_instant_client_answer(messages, {"dialogue_route": {"kind": "control_command"}})
    assert answer is not None
    assert "控制命令" in answer


def test_direct_arithmetic_fast_path_preserved() -> None:
    messages = [HumanMessage(content="2+2")]
    answer = _build_instant_client_answer(messages, {"dialogue_route": {"kind": "direct_answer"}})
    assert answer is not None
    assert "4" in answer


# --- Invariant 2: degenerate repetition is collapsed -------------------------


def test_sanitize_collapses_repeated_sentences() -> None:
    text = "让我重新获取天气信息。" * 5
    cleaned = _sanitize(text)
    assert cleaned is not None
    assert cleaned.count("让我重新获取天气信息") == 1


def test_sanitize_leaves_normal_text_untouched() -> None:
    text = "大阪今天多云，气温 18-24℃。建议带一件薄外套。"
    assert _sanitize(text) is None


def test_after_model_replaces_in_place_with_same_id() -> None:
    mw = ConversationIntegrityMiddleware()
    msg = AIMessage(content="让我重新获取。\n让我重新获取。\n让我重新获取。\n让我重新获取。", id="abc")
    result = mw._maybe_fix({"messages": [msg]})
    assert result is not None
    fixed = result["messages"][0]
    assert fixed.id == "abc"  # same id => reducer overwrites instead of appending
    assert len(fixed.content) < len(msg.content)


def test_after_model_skips_message_without_id() -> None:
    mw = ConversationIntegrityMiddleware()
    msg = AIMessage(content="重复。\n重复。\n重复。\n重复。")  # no id
    assert mw._maybe_fix({"messages": [msg]}) is None


def test_after_model_skips_tool_calling_turn() -> None:
    mw = ConversationIntegrityMiddleware()
    msg = AIMessage(
        content="重复。\n重复。\n重复。\n重复。",
        id="t1",
        tool_calls=[{"name": "get_weather", "args": {}, "id": "c1"}],
    )
    assert mw._maybe_fix({"messages": [msg]}) is None
