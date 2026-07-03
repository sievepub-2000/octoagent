"""Tests for dialogue routing — ensures continuation/imperative keywords trigger tool_action."""

from __future__ import annotations

from src.agents.dialogue_routing import (
    FAST_ROUTES,
    ROUTE_CONTROL_COMMAND,
    ROUTE_CURRENT_RESEARCH,
    ROUTE_DEEP_AGENT,
    ROUTE_DIRECT_ANSWER,
    ROUTE_PLAN_ONLY,
    ROUTE_TOOL_ACTION,
    classify_dialogue_route,
)


def _route(text: str, **kw) -> str:
    return classify_dialogue_route(text, **kw).kind


class TestContinuationKeywords:
    def test_chinese_control_words_route_to_control_command(self):
        for word in ["继续", "接着", "恢复", "暂停", "停止", "状态", "开启个新对话/new", "新建一个新对话"]:
            assert _route(word) == ROUTE_CONTROL_COMMAND, f"{word!r} should route to control_command, got {_route(word)}"

    def test_chinese_explicit_action_words_still_route_to_tool_action(self):
        for word in ["继续干", "推进一下", "搞定它", "去做", "开始执行", "落实下来"]:
            assert _route(word) == ROUTE_TOOL_ACTION, f"{word!r} should route to tool_action, got {_route(word)}"

    def test_english_tool_action_keywords(self):
        for word in ["run the build", "deploy to prod", "git commit", "open the file"]:
            assert _route(word) == ROUTE_TOOL_ACTION

    def test_short_neutral_question_is_direct_answer(self):
        assert _route("1+1=?") == ROUTE_DIRECT_ANSWER
        assert _route("你好") == ROUTE_DIRECT_ANSWER

    def test_attachments_force_tool_action(self):
        assert _route("看这张图", has_files=True) == ROUTE_TOOL_ACTION

    def test_explicit_mode_overrides_to_deep_agent(self):
        assert _route("你好", mode="thinking") == ROUTE_DEEP_AGENT
        assert _route("你好", mode="ultra") == ROUTE_DEEP_AGENT

    def test_long_message_promoted_to_deep(self):
        long_text = "a" * 500
        assert _route(long_text) == ROUTE_DEEP_AGENT

    def test_fast_routes_are_only_two(self):
        assert FAST_ROUTES == {"direct_answer", "control_command", "plan_only", "current_snapshot"}

    def test_explicit_route_param_honoured(self):
        assert classify_dialogue_route("你好", explicit_route="direct_answer").kind == ROUTE_DIRECT_ANSWER

    def test_control_command_overrides_bad_client_route(self):
        assert classify_dialogue_route("继续", explicit_route="direct_answer").kind == ROUTE_CONTROL_COMMAND

    def test_plan_only_confirmation_gate_beats_tool_keywords(self):
        for text in [
            "先给出整体优化方案，等我确认后再执行",
            "只评估一下当前系统，不要修改文件",
            "plan first, do not execute",
        ]:
            route = classify_dialogue_route(text)
            assert route.kind == ROUTE_PLAN_ONLY
            assert route.needs_tools is False
            assert route.needs_memory is True


class TestNeedsFlags:
    def test_tool_action_needs_tools_and_memory(self):
        r = classify_dialogue_route("继续干")
        assert r.needs_tools and r.needs_memory and not r.needs_deep_agent

    def test_direct_answer_no_tools(self):
        r = classify_dialogue_route("hi")
        assert not r.needs_tools and not r.needs_memory and not r.needs_deep_agent

class TestResearchIntentRouting:
    def test_trade_record_query_is_current_research(self):
        route = classify_dialogue_route(
            "帮我查一下上面的炼油厂LPG产品主要出口国家是哪些，产量和出口量是多大？另外查一下有没有到中国的贸易记录"
        )
        assert route.kind == ROUTE_CURRENT_RESEARCH
        assert route.needs_tools is True

    def test_weather_forecast_requires_current_research_tools(self):
        route = classify_dialogue_route("查一下济南、纽约明天的天气预报，汇总报告")

        assert route.kind == ROUTE_CURRENT_RESEARCH
        assert route.needs_tools is True
        assert route.reason in {"weather_requires_current_research", "strong_current_research_keywords"}

    def test_short_weather_forecast_uses_weather_route(self):
        route = classify_dialogue_route("明天纽约天气")

        assert route.kind == ROUTE_CURRENT_RESEARCH
        assert route.needs_tools is True
        assert route.reason == "weather_requires_current_research"

    def test_research_intent_overrides_bad_client_route(self):
        route = classify_dialogue_route(
            "帮我查一下阿特劳炼油厂LPG出口量和到中国贸易记录",
            explicit_route="direct_answer",
        )
        assert route.kind == ROUTE_CURRENT_RESEARCH
        assert route.needs_tools is True
        assert route.reason == "server_research_intent_overrides_client_route"

    def test_long_trade_assessment_stays_deep_with_tools(self):
        route = classify_dialogue_route(
            "详细评估分析一下阿特劳炼油厂LPG出口到青岛港CIF业务的可行性、客观风险、产量和出口国家。"
        )
        assert route.kind == ROUTE_DEEP_AGENT
        assert route.needs_tools is True
