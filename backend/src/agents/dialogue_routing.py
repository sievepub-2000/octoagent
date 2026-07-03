"""Shared dialogue route classification for OctoAgent runtime decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass

ROUTE_DIRECT_ANSWER = "direct_answer"
ROUTE_CONTROL_COMMAND = "control_command"
ROUTE_PLAN_ONLY = "plan_only"
ROUTE_CURRENT_SNAPSHOT = "current_snapshot"
ROUTE_CURRENT_RESEARCH = "current_research"
ROUTE_TOOL_ACTION = "tool_action"
ROUTE_DEEP_AGENT = "deep_agent"

FAST_ROUTES = {ROUTE_DIRECT_ANSWER, ROUTE_CONTROL_COMMAND, ROUTE_PLAN_ONLY, ROUTE_CURRENT_SNAPSHOT}


@dataclass(frozen=True, slots=True)
class DialogueRoute:
    kind: str
    reason: str
    needs_tools: bool = False
    needs_memory: bool = False
    needs_deep_agent: bool = False


_TOOL_ACTION_RE = re.compile(
    r"\b(shell|bash|powershell|ssh|scp|git|commit|push|deploy|run|execute|delete|remove|write|edit|create|build|test|open|read|file|repo|repository)\b",
    re.IGNORECASE,
)
_TOOL_ACTION_ZH_RE = re.compile(
    r"执行|运行|删除|修改|创建|部署|提交|同步|测试|修复|重构|检查|读取|文件|仓库|项目|"
    r"主机|机器|去做|开始干|开始执行|启动|按计划|"
    r"完成它|完成任务|搞定|搞一下|落实|推进|推一下|做完|继续干",
)
_CONTROL_COMMAND_RE = re.compile(
    r"^\s*(?:/(?:new|stop|pause|resume|continue|status)|"
    r"(?:new|stop|pause|resume|continue|status)\s*)\s*$",
    re.IGNORECASE,
)
_CONTROL_COMMAND_ZH_RE = re.compile(
    r"^\s*(?:"
    r"(?:开启|打开|新建|创建|开)(?:个|一个)?新(?:对话|会话|聊天)|"
    r"新(?:对话|会话|聊天)|"
    r"暂停|停止|停下|中止|取消|继续|接着|恢复|状态|进度|"
    r"开启个新对话/new|开启新对话/new"
    r")\s*[。.!！?？]*\s*$",
)
_PLAN_ONLY_RE = re.compile(
    r"\b(?:plan only|planning only|do not execute|don't execute|no execution|wait for confirmation|only analyze|only assess|proposal first|plan first)\b",
    re.IGNORECASE,
)
_PLAN_ONLY_ZH_RE = re.compile(
    r"先(?:给|出|写|提供|做)?(?:方案|计划|评估|分析|报告)|"
    r"(?:等|待).{0,8}(?:我)?确认|"
    r"确认后(?:再)?(?:执行|做|修改|开始)|"
    r"不要(?:执行|动手|修改|提交|推送)|"
    r"别(?:执行|动手|修改|提交|推送)|"
    r"只(?:给|做|写)?(?:方案|计划|评估|分析|报告)|"
    r"先评估|先分析|先不要(?:执行|动手|修改)",
)
_CURRENT_WEATHER_RE = re.compile(r"\b(weather|forecast)\b|天气|天氣|氣象", re.IGNORECASE)
_CURRENT_X_TRENDS_RE = re.compile(
    r"(?=.*(?:\bx\.com\b|\btwitter\b|推特))(?=.*(?:\btrend\b|\bhot\b|热门|热点|趋势))",
    re.IGNORECASE,
)
_SYSTEM_TOOLS_RE = re.compile(
    r"\b(available tools?|tool inventory|tool status|system tools?)\b|系统工具|工具情况|可用工具|工具列表|工具清单|工具状态",
    re.IGNORECASE,
)
_CURRENT_RESEARCH_RE = re.compile(
    r"\b(today|latest|current|news|price|stock|weather|forecast|search|web|internet|lookup|export|import|trade record|production volume)\b|"
    r"今天|最新|当前|現在|新闻|新聞|查询|搜尋|搜索|联网|网络|查一下|查查|查找|调查|"
    r"贸易记录|貿易記錄|出口国家|出口國家|出口量|进口量|進口量|产量|產量|货源地|貨源地|到中国|到中國|到岸|CIF",
    re.IGNORECASE,
)
_STRONG_CURRENT_RESEARCH_RE = re.compile(
    r"\b(search|lookup|export|import|trade record|production volume)\b|"
    r"查一下|查查|查找|帮我查|幫我查|贸易记录|貿易記錄|出口国家|出口國家|出口量|进口量|進口量|产量|產量|货源地|貨源地|到中国|到中國",
    re.IGNORECASE,
)
_DEEP_RE = re.compile(
    r"\b(analy[sz]e|architecture|refactor|optimi[sz]e|design|plan|compare|investigate|debug|diagnose|complex|comprehensive)\b|深度|整体|架构|重构|优化|分析|评估|彻底|复杂|长期|多模块",
    re.IGNORECASE,
)


def classify_dialogue_route(
    text: str,
    *,
    mode: str | None = None,
    has_files: bool = False,
    explicit_route: str | None = None,
) -> DialogueRoute:
    """Classify a user turn into the cheapest route that can satisfy it."""

    stripped = text.strip()
    if explicit_route and stripped and _STRONG_CURRENT_RESEARCH_RE.search(stripped):
        if _DEEP_RE.search(stripped) or len(stripped) > 420:
            return DialogueRoute(
                ROUTE_DEEP_AGENT,
                "server_research_intent_overrides_client_route",
                needs_tools=True,
                needs_memory=True,
                needs_deep_agent=True,
            )
        return DialogueRoute(ROUTE_CURRENT_RESEARCH, "server_research_intent_overrides_client_route", needs_tools=True)
    if stripped and _is_control_command(stripped):
        return DialogueRoute(ROUTE_CONTROL_COMMAND, "conversation_control_command")
    if stripped and _is_plan_only_request(stripped):
        return DialogueRoute(ROUTE_PLAN_ONLY, "planning_only_or_confirmation_gated", needs_memory=True)
    if explicit_route:
        return _route_from_kind(explicit_route, reason="client_explicit_route")

    if has_files:
        return DialogueRoute(ROUTE_TOOL_ACTION, "attachments_require_file_tools", needs_tools=True, needs_memory=True)
    if mode in {"thinking", "pro", "ultra"}:
        return DialogueRoute(ROUTE_DEEP_AGENT, "user_selected_deep_mode", needs_tools=True, needs_memory=True, needs_deep_agent=mode == "ultra")
    if not stripped:
        return DialogueRoute(ROUTE_DIRECT_ANSWER, "empty_or_whitespace")

    if _is_control_command(stripped):
        return DialogueRoute(ROUTE_CONTROL_COMMAND, "conversation_control_command")
    if _is_plan_only_request(stripped):
        return DialogueRoute(ROUTE_PLAN_ONLY, "planning_only_or_confirmation_gated", needs_memory=True)
    if _STRONG_CURRENT_RESEARCH_RE.search(stripped):
        if _DEEP_RE.search(stripped) or len(stripped) > 420:
            return DialogueRoute(ROUTE_DEEP_AGENT, "deep_research_keywords", needs_tools=True, needs_memory=True, needs_deep_agent=True)
        return DialogueRoute(ROUTE_CURRENT_RESEARCH, "strong_current_research_keywords", needs_tools=True)
    if _TOOL_ACTION_RE.search(stripped) or _TOOL_ACTION_ZH_RE.search(stripped):
        return DialogueRoute(ROUTE_TOOL_ACTION, "action_or_workspace_keywords", needs_tools=True, needs_memory=True)
    if _DEEP_RE.search(stripped) or len(stripped) > 420:
        return DialogueRoute(ROUTE_DEEP_AGENT, "deep_analysis_keywords_or_long_request", needs_tools=True, needs_memory=True, needs_deep_agent=True)
    if _CURRENT_WEATHER_RE.search(stripped):
        return DialogueRoute(ROUTE_CURRENT_RESEARCH, "weather_requires_current_research", needs_tools=True)
    if _CURRENT_X_TRENDS_RE.search(stripped) or _SYSTEM_TOOLS_RE.search(stripped):
        return DialogueRoute(ROUTE_CURRENT_SNAPSHOT, "server_snapshot_supported_current_info")
    if _CURRENT_RESEARCH_RE.search(stripped):
        return DialogueRoute(ROUTE_CURRENT_RESEARCH, "general_current_info_requires_research", needs_tools=True)
    return DialogueRoute(ROUTE_DIRECT_ANSWER, "short_clear_question")


def _route_from_kind(kind: str, *, reason: str) -> DialogueRoute:
    if kind == ROUTE_DIRECT_ANSWER:
        return DialogueRoute(kind, reason)
    if kind == ROUTE_CONTROL_COMMAND:
        return DialogueRoute(kind, reason)
    if kind == ROUTE_PLAN_ONLY:
        return DialogueRoute(kind, reason, needs_memory=True)
    if kind == ROUTE_CURRENT_SNAPSHOT:
        return DialogueRoute(kind, reason)
    if kind == ROUTE_CURRENT_RESEARCH:
        return DialogueRoute(kind, reason, needs_tools=True)
    if kind == ROUTE_TOOL_ACTION:
        return DialogueRoute(kind, reason, needs_tools=True, needs_memory=True)
    if kind == ROUTE_DEEP_AGENT:
        return DialogueRoute(kind, reason, needs_tools=True, needs_memory=True, needs_deep_agent=True)
    return DialogueRoute(ROUTE_TOOL_ACTION, f"unknown_route:{kind}", needs_tools=True, needs_memory=True)


def _is_control_command(text: str) -> bool:
    return bool(_CONTROL_COMMAND_RE.search(text) or _CONTROL_COMMAND_ZH_RE.search(text))


def _is_plan_only_request(text: str) -> bool:
    return bool(_PLAN_ONLY_RE.search(text) or _PLAN_ONLY_ZH_RE.search(text))
