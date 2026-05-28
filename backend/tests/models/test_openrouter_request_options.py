from __future__ import annotations

from typing import Any, ClassVar

from langchain_core.language_models.chat_models import BaseChatModel as CoreBaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult

from src.models import factory
from src.models.openrouter import (
    apply_openrouter_request_options,
    is_openrouter_base_url,
    openrouter_app_attribution_headers,
)
from src.runtime.config.model_config import ModelConfig


class _FakeConfig:
    def __init__(self, models: list[ModelConfig]) -> None:
        self.models = models

    def get_model_config(self, name: str) -> ModelConfig | None:
        return next((model for model in self.models if model.name == name), None)


class _CapturingChatModel(CoreBaseChatModel):
    captured_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, **kwargs: Any) -> None:
        type(self).captured_kwargs = kwargs
        super().__init__()

    @property
    def _llm_type(self) -> str:
        return "capturing-chat-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError


def test_openrouter_base_url_detection() -> None:
    assert is_openrouter_base_url("https://openrouter.ai/api/v1") is True
    assert is_openrouter_base_url("https://api.openrouter.ai/v1") is True
    assert is_openrouter_base_url("https://api.openai.com/v1") is False


def test_openrouter_attribution_headers_default(monkeypatch) -> None:
    monkeypatch.delenv("OCTOAGENT_OPENROUTER_APP_URL", raising=False)
    monkeypatch.delenv("OCTOAGENT_OPENROUTER_APP_TITLE", raising=False)

    assert openrouter_app_attribution_headers() == {
        "HTTP-Referer": "https://github.com/sievepub-2000/octoagent",
        "X-Title": "OctoAgent",
    }


def test_openrouter_request_options_merge_headers_and_usage(monkeypatch) -> None:
    monkeypatch.setenv("OCTOAGENT_OPENROUTER_APP_URL", "https://octoagent.example")
    monkeypatch.setenv("OCTOAGENT_OPENROUTER_APP_TITLE", "OctoAgent Test")

    model_settings, runtime_kwargs = apply_openrouter_request_options(
        model_settings_from_config={
            "default_headers": {"x-existing": "from-config"},
            "extra_body": {"usage": {"include": False, "details": True}},
        },
        runtime_kwargs={
            "default_headers": {"x-runtime": "from-runtime"},
            "extra_body": {"provider": {"order": ["openai"]}},
        },
    )

    assert runtime_kwargs == {}
    assert model_settings["default_headers"] == {
        "x-runtime": "from-runtime",
        "x-existing": "from-config",
        "HTTP-Referer": "https://octoagent.example",
        "X-Title": "OctoAgent Test",
    }
    assert model_settings["extra_body"] == {
        "provider": {"order": ["openai"]},
        "usage": {"include": True, "details": True},
    }


def test_factory_applies_openrouter_options_to_chat_model(monkeypatch) -> None:
    openrouter_model = ModelConfig(
        name="openrouter-test",
        display_name="OpenRouter Test",
        model="openai/gpt-oss-20b:free",
        interface_type="openai_compatible",
        provider_name="openrouter",
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        temperature=0.85,
    )
    monkeypatch.setattr(factory, "get_app_config", lambda: _FakeConfig([openrouter_model]))
    monkeypatch.setattr(factory, "resolve_class", lambda use, base_class: _CapturingChatModel)
    monkeypatch.setattr(factory, "is_tracing_enabled", lambda: False)

    factory._create_chat_model("openrouter-test", enable_fallback=False)

    assert _CapturingChatModel.captured_kwargs["default_headers"]["HTTP-Referer"]
    assert _CapturingChatModel.captured_kwargs["default_headers"]["X-Title"] == "OctoAgent"
    assert _CapturingChatModel.captured_kwargs["extra_body"]["usage"]["include"] is True
