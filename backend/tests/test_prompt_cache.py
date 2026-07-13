"""Tests for PromptCache: base prompt stability and dynamic section injection."""

from __future__ import annotations

import hashlib

import pytest


def _make_cache(config_version: str = "1"):
    from src.agents.core.prompt_cache import PromptCache
    return PromptCache(config_version=config_version)


def test_base_prompt_is_deterministic() -> None:
    cache = _make_cache()
    first = cache.build_base_prompt()
    second = cache.build_base_prompt()
    assert first == second
    assert first.startswith("<!-- config_version=1 -->")


def test_base_prompt_contains_config_version_marker() -> None:
    cache = _make_cache(config_version="2")
    prompt = cache.build_base_prompt()
    assert "config_version=2" in prompt


def test_different_versions_produce_different_prompts() -> None:
    cache_v1 = _make_cache(config_version="1")
    cache_v2 = _make_cache(config_version="2")
    assert cache_v1.build_base_prompt() != cache_v2.build_base_prompt()


def test_cache_key_is_sha256_hexdigest() -> None:
    from src.agents.core.prompt_cache import PromptCache

    key = PromptCache.get_cache_key("test prompt content")
    expected = hashlib.sha256(b"test prompt content").hexdigest()
    assert key == expected


def test_is_cached_returns_false_before_build() -> None:
    cache = _make_cache()
    assert not cache.is_cached()


def test_is_cached_returns_true_after_build() -> None:
    cache = _make_cache()
    cache.build_base_prompt()
    assert cache.is_cached()


def test_dynamic_section_injects_skills_memory_state() -> None:
    cache = _make_cache()
    section = cache.build_dynamic_section(
        context={
            "skills": "## Active Skills\n- bash\n- file_read",
            "memory": "User prefers concise answers.",
            "session_state": "Current task: write a report.",
        }
    )
    assert "bash" in section
    assert "prefers concise" in section
    assert "write a report" in section


def test_dynamic_section_uses_placeholders_for_missing_keys() -> None:
    cache = _make_cache()
    section = cache.build_dynamic_section(context={})
    assert "\uff08\u6682\u65e0\u65b0\u589e\u6280\u80fd\uff09" in section  # (暂无新增技能)


def test_build_messages_assembles_system_user_history() -> None:
    messages_module = pytest.importorskip("langchain_core.messages", reason="langchain_core not installed")

    cache = _make_cache()
    messages = cache.build_messages(
        context={"skills": "bash"},
        conversation_history=[
            messages_module.HumanMessage(content="hi"),
            messages_module.AIMessage(content="hello back"),
        ],
    )
    assert len(messages) == 4  # system + dynamic user + human + ai
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "human"
    assert messages[3]["role"] == "ai"


def test_build_messages_handles_dict_history() -> None:
    messages_module = pytest.importorskip("langchain_core.messages", reason="langchain_core not installed")

    cache = _make_cache()
    messages = cache.build_messages(
        conversation_history=[messages_module.HumanMessage(content="hello")],
    )
    human_msgs = [m for m in messages if m.get("role") == "human" and m.get("content") == "hello"]
    assert len(human_msgs) == 1
