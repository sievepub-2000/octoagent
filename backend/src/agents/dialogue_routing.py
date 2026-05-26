"""Shared dialogue route classification for OctoAgent runtime decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass

ROUTE_DIRECT_ANSWER = "direct_answer"
ROUTE_CURRENT_SNAPSHOT = "current_snapshot"
ROUTE_CURRENT_RESEARCH = "current_research"
ROUTE_TOOL_ACTION = "tool_action"
ROUTE_DEEP_AGENT = "deep_agent"

FAST_ROUTES = {ROUTE_DIRECT_ANSWER, ROUTE_CURRENT_SNAPSHOT}


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
    r"主机|机器|继续|接着|接下来|下一步|然后|去做|开始干|开始执行|启动|按计划|"
    r"完成它|完成任务|搞定|搞一下|落实|推进|推一下|做完|继续干",
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
    r"\b(today|latest|current|news|price|stock|weather|forecast|search|web|internet|lookup)\b|今天|最新|当前|現在|新闻|新聞|查询|搜尋|搜索|联网|网络",
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

    if explicit_route:
        return _route_from_kind(explicit_route, reason="client_explicit_route")

    stripped = text.strip()
    if has_files:
        return DialogueRoute(ROUTE_TOOL_ACTION, "attachments_require_file_tools", needs_tools=True, needs_memory=True)
    if mode in {"thinking", "pro", "ultra"}:
        return DialogueRoute(ROUTE_DEEP_AGENT, "user_selected_deep_mode", needs_tools=True, needs_memory=True, needs_deep_agent=mode == "ultra")
    if not stripped:
        return DialogueRoute(ROUTE_DIRECT_ANSWER, "empty_or_whitespace")

    if _TOOL_ACTION_RE.search(stripped) or _TOOL_ACTION_ZH_RE.search(stripped):
        return DialogueRoute(ROUTE_TOOL_ACTION, "action_or_workspace_keywords", needs_tools=True, needs_memory=True)
    if _DEEP_RE.search(stripped) or len(stripped) > 420:
        return DialogueRoute(ROUTE_DEEP_AGENT, "deep_analysis_keywords_or_long_request", needs_tools=True, needs_memory=True, needs_deep_agent=True)
    if _CURRENT_WEATHER_RE.search(stripped) or _CURRENT_X_TRENDS_RE.search(stripped) or _SYSTEM_TOOLS_RE.search(stripped):
        return DialogueRoute(ROUTE_CURRENT_SNAPSHOT, "server_snapshot_supported_current_info")
    if _CURRENT_RESEARCH_RE.search(stripped):
        return DialogueRoute(ROUTE_CURRENT_RESEARCH, "general_current_info_requires_research", needs_tools=True)
    return DialogueRoute(ROUTE_DIRECT_ANSWER, "short_clear_question")


def _route_from_kind(kind: str, *, reason: str) -> DialogueRoute:
    if kind == ROUTE_DIRECT_ANSWER:
        return DialogueRoute(kind, reason)
    if kind == ROUTE_CURRENT_SNAPSHOT:
        return DialogueRoute(kind, reason)
    if kind == ROUTE_CURRENT_RESEARCH:
        return DialogueRoute(kind, reason, needs_tools=True)
    if kind == ROUTE_TOOL_ACTION:
        return DialogueRoute(kind, reason, needs_tools=True, needs_memory=True)
    if kind == ROUTE_DEEP_AGENT:
        return DialogueRoute(kind, reason, needs_tools=True, needs_memory=True, needs_deep_agent=True)
    return DialogueRoute(ROUTE_TOOL_ACTION, f"unknown_route:{kind}", needs_tools=True, needs_memory=True)
