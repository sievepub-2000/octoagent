from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from src.runtime.context_budget import (
    SYSTEM_SESSION_CONTINUE_PROMPT,
    estimate_text_tokens,
    trim_messages_to_budget,
    truncate_oversized_messages,
)


def test_estimator_handles_ascii_and_cjk_with_one_shared_rule() -> None:
    assert estimate_text_tokens("abcd", minimum=1) == 1
    assert estimate_text_tokens("你好世界", minimum=1) >= 2


def test_trim_messages_keeps_bounded_system_and_recent_context() -> None:
    messages = [
        SystemMessage(content="primary system " + ("s" * 4000)),
        SystemMessage(content="old checkpoint " + ("c" * 4000)),
        *[HumanMessage(content=f"turn {index} " + ("x" * 1000)) for index in range(20)],
    ]

    result = trim_messages_to_budget(messages, 700, keep_recent_messages=4, force=True)

    assert result.changed
    assert result.dropped_count > 0
    assert any(message.content == SYSTEM_SESSION_CONTINUE_PROMPT for message in result.messages if message.type == "system")
    assert result.final_tokens <= 700
    assert "turn 19" in result.messages[-1].content


def test_truncate_oversized_messages_uses_shared_continuation_marker() -> None:
    [message], changed = truncate_oversized_messages([HumanMessage(content="x" * 30_000)])

    assert changed
    assert SYSTEM_SESSION_CONTINUE_PROMPT in message.content
    assert len(message.content) < 30_000
