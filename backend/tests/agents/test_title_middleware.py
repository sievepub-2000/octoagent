from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

import src.agents.middlewares.title_middleware as title_middleware
from src.agents.middlewares.title_middleware import TitleMiddleware
from src.runtime.config.title_config import TitleConfig, set_title_config


def teardown_function() -> None:
    set_title_config(TitleConfig())


def test_placeholder_chat_title_falls_back_to_first_user_message() -> None:
    set_title_config(TitleConfig(max_chars=60))

    title = TitleMiddleware._normalize_title(
        "Chat 1234abcd",
        "请检查系统设置中的技能进化信任评分观察器",
    )

    assert title == "请检查系统设置中的技能进化信任评分观察器"


def test_title_generation_uses_configured_title_model(monkeypatch) -> None:
    calls: list[str | None] = []

    class FakeTitleModel:
        def invoke(self, prompt: str) -> AIMessage:
            return AIMessage(content="技能进化信任评分检查")

    def fake_create_chat_model(*, name: str | None = None, thinking_enabled: bool = False):
        calls.append(name)
        assert thinking_enabled is False
        return FakeTitleModel()

    monkeypatch.setattr(title_middleware, "create_chat_model", fake_create_chat_model)
    set_title_config(TitleConfig(model_name="title-summary-model"))

    middleware = TitleMiddleware()
    title = middleware._generate_title_sync(
        {
            "messages": [
                HumanMessage(content="检查技能进化信任评分观察器"),
                AIMessage(content="我会检查相关模块。"),
            ]
        }
    )

    assert title == "技能进化信任评分检查"
    assert calls == ["title-summary-model"]
