"""Conversation-integrity regression tests."""

from langchain_core.messages import AIMessage

from src.agents.middlewares.conversation_integrity_middleware import (
    ConversationIntegrityMiddleware,
    _sanitize,
)


def test_sanitize_collapses_repeated_sentences() -> None:
    text = "Let me fetch that again. " * 5
    cleaned = _sanitize(text)
    assert cleaned is not None
    assert cleaned.count("Let me fetch that again") == 1


def test_sanitize_leaves_normal_text_untouched() -> None:
    assert _sanitize("The service is healthy and the model is ready.") is None


def test_after_model_replaces_in_place_with_same_id() -> None:
    middleware = ConversationIntegrityMiddleware()
    message = AIMessage(content=("Retrying now.\n" * 5), id="abc")
    result = middleware._maybe_fix({"messages": [message]})
    assert result is not None
    fixed = result["messages"][0]
    assert fixed.id == "abc"
    assert len(fixed.content) < len(message.content)


def test_after_model_skips_message_without_id() -> None:
    middleware = ConversationIntegrityMiddleware()
    message = AIMessage(content="Repeated.\n" * 5)
    assert middleware._maybe_fix({"messages": [message]}) is None

def test_after_model_skips_tool_calling_turn() -> None:
    middleware = ConversationIntegrityMiddleware()
    message = AIMessage(
        content="Repeated.\n" * 5,
        id="t1",
        tool_calls=[{"name": "get_weather", "args": {}, "id": "c1"}],
    )
    assert middleware._maybe_fix({"messages": [message]}) is None
