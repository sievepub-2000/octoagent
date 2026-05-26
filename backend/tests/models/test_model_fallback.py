from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from src.runtime.config.model_config import ModelConfig
from src.models import factory
from src.models.error_contracts import NormalizedModelError, normalize_model_exception


class _FakeConfig:
    def __init__(self, models: list[ModelConfig]) -> None:
        self.models = models

    def get_model_config(self, name: str) -> ModelConfig | None:
        return next((model for model in self.models if model.name == name), None)


def test_google_not_found_error_is_normalized_as_model_not_found() -> None:
    error = normalize_model_exception(
        Exception("Error calling model 'GoogleAi/gemini-3.1-pro-preview' (Not Found): 404 Not Found"),
        model_name="gemini-3.1-pro-preview",
        provider_name="google",
        interface_type="google_genai",
        adapter_type="google_genai",
    )

    assert error.status_code == 404
    assert error.code == "model_not_found"
    assert error.retryable is True


def test_model_not_found_errors_are_fallbackable() -> None:
    error = NormalizedModelError(
        code="model_not_found",
        message="404 Not Found",
        retryable=True,
        status_code=404,
        model_name="gemini-3.1-pro-preview",
        provider_name="google",
    )

    assert factory._should_fallback_model(error) is True


def test_effective_fallbacks_add_non_paid_matching_candidates(monkeypatch) -> None:
    primary = ModelConfig(
        name="gemini-3.1-pro-preview",
        display_name="Gemini",
        model="GoogleAi/gemini-3.1-pro-preview",
        interface_type="google_genai",
        provider_name="google",
        supports_thinking=True,
        fallback_models=[],
    )
    free_candidate = ModelConfig(
        name="free-thinking-model",
        display_name="Free Thinking",
        model="free/model",
        interface_type="openai_compatible",
        provider_name="openrouter",
        supports_thinking=True,
        priority=10,
    )
    paid_candidate = ModelConfig(
        name="paid-thinking-model-paid",
        display_name="Paid Thinking (Paid)",
        model="paid/model",
        interface_type="openai_compatible",
        provider_name="openai",
        supports_thinking=True,
        priority=99,
    )
    non_thinking_candidate = ModelConfig(
        name="non-thinking-model",
        display_name="Non Thinking",
        model="basic/model",
        interface_type="openai_compatible",
        provider_name="openrouter",
        supports_thinking=False,
        priority=50,
    )
    monkeypatch.setattr(
        factory,
        "get_app_config",
        lambda: _FakeConfig([primary, paid_candidate, non_thinking_candidate, free_candidate]),
    )
    monkeypatch.setattr(factory, "_embedded_backup_enabled", lambda: False)

    fallbacks = factory.resolve_effective_fallback_model_names(
        "gemini-3.1-pro-preview",
        thinking_enabled=True,
    )

    assert fallbacks == ["free-thinking-model"]


def test_context_safety_trim_uses_model_context_window() -> None:
    messages = [SystemMessage(content="System prompt")]
    for index in range(40):
        messages.append(HumanMessage(content=f"message {index} " + ("x" * 260)))

    trimmed = factory._trim_messages_if_needed(messages, max_context_tokens=1_000)

    assert len(trimmed) < len(messages)
    assert any(message.content == factory.SYSTEM_SESSION_CONTINUE_PROMPT for message in trimmed)
    assert factory._estimate_message_tokens(trimmed) <= 750


def test_context_safety_trim_budgets_runtime_system_messages() -> None:
    messages = [SystemMessage(content="Primary system prompt " + ("s" * 1200))]
    for index in range(30):
        messages.append(SystemMessage(content=f"runtime checkpoint {index} " + ("c" * 1200)))
        messages.append(HumanMessage(content=f"user {index} " + ("u" * 200)))

    trimmed = factory._trim_messages_if_needed(messages, max_context_tokens=1_000, force=True)

    assert len([message for message in trimmed if message.type == "system"]) < len([message for message in messages if message.type == "system"])
    assert any(message.content == factory.SYSTEM_SESSION_CONTINUE_PROMPT for message in trimmed)
    assert factory._estimate_message_tokens(trimmed) <= 750


def test_context_retry_trim_has_hard_safety_cap() -> None:
    messages = [SystemMessage(content="System prompt")]
    for index in range(120):
        messages.append(HumanMessage(content=f"message {index} " + ("x" * 1000)))

    trimmed = factory._aggressive_context_retry_messages(messages, max_context_tokens=65_536)

    assert factory._estimate_message_tokens(trimmed) <= factory._CONTEXT_RETRY_MAX_TOKENS


def test_context_length_error_retries_same_model_with_aggressive_trim(monkeypatch) -> None:
    class RetryAfterContextTrimModel:
        def __init__(self) -> None:
            self.calls: list[int] = []

        def _generate(self, messages, **kwargs):
            self.calls.append(factory._estimate_message_tokens(messages))
            if len(self.calls) == 1:
                raise NormalizedModelError(
                    code="context_length_exceeded",
                    message="context window exceeded",
                    retryable=False,
                    status_code=400,
                    model_name="tiny-model",
                    provider_name="test",
                )
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    retry_model = RetryAfterContextTrimModel()
    fallback = factory.FallbackChatModel(
        primary_model_name="tiny-model",
        candidate_model_names=["tiny-model"],
    )
    monkeypatch.setattr(factory.FallbackChatModel, "_candidate_model", lambda self, name: retry_model)
    monkeypatch.setattr(factory, "_context_window_for_model", lambda name: 1_000)

    messages = [SystemMessage(content="System prompt")]
    for index in range(80):
        messages.append(HumanMessage(content=f"message {index} " + ("x" * 260)))

    result = fallback._generate(messages)

    assert result.generations[0].message.content == "ok"
    assert len(retry_model.calls) == 2
    assert retry_model.calls[1] <= 500
    assert retry_model.calls[1] < retry_model.calls[0]


def test_context_window_errors_are_normalized() -> None:
    error = normalize_model_exception(
        Exception("The request exceeded the model context window token budget."),
        model_name="tiny-model",
        provider_name="test",
        interface_type="openai_compatible",
        adapter_type="test",
    )

    assert error.code == "context_length_exceeded"
    assert error.status_code == 400
