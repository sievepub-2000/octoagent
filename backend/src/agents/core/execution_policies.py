"""Agent execution policies and evaluation helpers (Slice F extraction).

Pure functions that determine execution budgets, evaluate outcomes,
assess research needs, and resolve execution roles.  These do not
import heavy runtime deps — only ``task_workspaces.contracts`` types.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.agents.core.instruction_contracts import detect_instruction_contract
from src.agents.core.roles import is_management_role, split_execution_roles

if TYPE_CHECKING:
    from src.storage.task_workspaces.contracts import AgentHandle, TaskWorkspace

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_MAX_AGENT_RETRIES = 3

# 3-3-6 escalation stages (user-spec: 子agent 3 次 → 主agent 优化方案再 3 次 → 主agent 亲自 1 次)
_ESCALATION_STAGE1_LIMIT = 3  # attempts 1..3: worker self-analysis retries
_ESCALATION_STAGE2_LIMIT = 6  # attempts 4..6: lead-optimized plan, worker re-executes
_ESCALATION_TOTAL_ATTEMPTS = 7  # attempt 7: lead takes over direct execution


def get_escalation_stage(attempt: int) -> int:
    """Return the 3-3-6 escalation stage (1..3) for the given 1-based attempt index."""
    if attempt <= _ESCALATION_STAGE1_LIMIT:
        return 1
    if attempt <= _ESCALATION_STAGE2_LIMIT:
        return 2
    return 3


_FAILURE_MARKERS = (
    "failed",
    "failure",
    "error",
    "exception",
    "traceback",
    "timed out",
    "timeout",
    "cannot",
    "can't",
    "unable",
    "未完成",
    "失败",
    "错误",
    "异常",
    "超时",
    "无法",
)

_HARD_FAILURE_MARKERS = (
    "network is unreachable",
    "newconnectionerror",
    "connection refused",
    "name or service not known",
    "web_fetch failed",
    "web_search failed",
    "tool fallback executed by server because the model produced no tool calls",
    "tool fallback could not run due to server error",
    "search backend unavailable right now",
    "returning fallback public sources for manual verification",
    "duckduckgo:urlerror",
    "jina:urlerror",
    "无法获取",
    "无法访问",
    "无法建立新连接",
    "网络不可达",
    "请求均失败",
    "请求失败",
    "联网失败",
)

_RESEARCH_HINT_MARKERS = (
    "latest",
    "current",
    "today",
    "recent",
    "news",
    "internet",
    "web search",
    "website",
    "search engine",
    "search the web",
    "search online",
    "查阅",
    "网站",
    "联网",
    "最新",
    "当前",
    "实时",
    "检索",
    "搜索引擎",
    "网络搜索",
)

_AI_NEWS_QUERY_MARKERS = ("news", "latest", "recent", "新闻", "资讯", "最新", "发布", "上线")
_AI_MODEL_QUERY_MARKERS = (
    "ai",
    "model",
    "models",
    "llm",
    "gpt",
    "claude",
    "gemini",
    "openai",
    "anthropic",
    "deepmind",
    "huggingface",
    "mistral",
    "llama",
    "qwen",
    "模型",
    "大模型",
    "人工智能",
)


# ------------------------------------------------------------------
# Execution budget
# ------------------------------------------------------------------


def get_execution_retry_budget(workspace: TaskWorkspace) -> int:
    """Return the maximum number of execution attempts for a workspace.

    The 3-3-6 escalation requires up to 7 attempts (3 worker self-analysis +
    3 lead-optimized + 1 lead direct execution).  When auto_iterate is
    disabled we still honor the user's 1-attempt intent.
    """
    metadata = workspace.metadata or {}
    if "auto_iterate" not in metadata:
        return _ESCALATION_TOTAL_ATTEMPTS
    if not bool(metadata.get("auto_iterate")):
        return 1
    raw_iterations = metadata.get("max_iterations", _ESCALATION_TOTAL_ATTEMPTS)
    try:
        iterations = int(raw_iterations)
    except (TypeError, ValueError):
        iterations = _ESCALATION_TOTAL_ATTEMPTS
    return max(1, iterations)


# ------------------------------------------------------------------
# Execution role resolution (delegates to agent_core.roles)
# ------------------------------------------------------------------


def resolve_execution_roles(
    workspace: TaskWorkspace,
) -> tuple[AgentHandle, list[AgentHandle], AgentHandle | None]:
    """Resolve lead, worker, and optional reviewer agents for a workspace."""
    return split_execution_roles(workspace)


# ------------------------------------------------------------------
# Outcome evaluation
# ------------------------------------------------------------------


def output_indicates_hard_failure(output: str | None) -> bool:
    """Return True if *output* contains markers of an unrecoverable failure."""
    if not output:
        return False
    lower_output = output.lower()
    return any(marker in lower_output for marker in _HARD_FAILURE_MARKERS)


def normalize_text(value: str | None) -> str:
    """Return a whitespace-collapsed, lowercased version of *value*."""
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


def looks_like_ai_model_news_query(value: str | None) -> bool:
    """Return True when *value* asks for current AI model news updates."""
    normalized = normalize_text(value)
    mentions_news = any(marker in normalized for marker in _AI_NEWS_QUERY_MARKERS)
    mentions_ai_model = any(marker in normalized for marker in _AI_MODEL_QUERY_MARKERS)
    return mentions_news and mentions_ai_model


def _required_domain_for_workspace(workspace: TaskWorkspace) -> str | None:
    normalized_goal = normalize_text(workspace.goal)
    if looks_like_ai_model_news_query(normalized_goal):
        return None
    if any(marker in normalized_goal for marker in ("x.com", "twitter", "site:x.com")):
        return "x.com"
    return None


def _output_contains_domain_evidence(output: str, domain: str) -> bool:
    lower_output = (output or "").lower()
    return f"https://{domain}" in lower_output or f"http://{domain}" in lower_output or f"site:{domain}" in lower_output


def _extract_unique_urls(output: str) -> list[str]:
    urls = re.findall(r"https?://[^\s<>)\]}\"']+", output or "", flags=re.IGNORECASE)
    cleaned: list[str] = []
    seen: set[str] = set()
    for url in urls:
        normalized = url.rstrip(".,，。；;:：")
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
    return cleaned


def _source_url_count(output: str, required_domains: tuple[str, ...]) -> int:
    urls = _extract_unique_urls(output)
    if not required_domains:
        return len(urls)
    count = 0
    for url in urls:
        lowered = url.lower()
        if any(f"://{domain}" in lowered or f"://www.{domain}" in lowered for domain in required_domains):
            count += 1
    return count


def extract_expected_keywords(workspace: TaskWorkspace) -> list[str]:
    """Extract expected-output keywords from workspace metadata."""
    metadata = workspace.metadata or {}
    raw_keywords = metadata.get("expected_keywords")
    if isinstance(raw_keywords, list):
        return [str(item).strip().lower() for item in raw_keywords if str(item).strip()]
    raw_expected = metadata.get("expected_result") or metadata.get("acceptance_criteria")
    if not raw_expected and workspace.summary:
        summary = workspace.summary.strip()
        for prefix in ("expected:", "expected result:", "acceptance:", "预期:", "预期结果:", "验收标准:"):
            if summary.lower().startswith(prefix.lower()):
                raw_expected = summary[len(prefix) :]
                break
    if not raw_expected:
        return []
    tokens = [token.strip().lower() for token in re.split(r"[,;\n|，；、]+", str(raw_expected)) if token.strip()]
    return [token for token in tokens if len(token) >= 2]


def evaluate_task_outcome(
    workspace: TaskWorkspace,
    assistant_output: str,
) -> tuple[str, str | None]:
    """Evaluate whether an agent's output satisfies the task requirements.

    Returns ``("completed", None)`` on success, or
    ``("failed", "<reason>")`` on failure.
    """
    normalized_output = normalize_text(assistant_output)
    if not normalized_output:
        return "failed", "Agent returned empty output."
    if _is_status_audit_task(workspace) and _looks_like_substantive_status_report(assistant_output):
        return "completed", None
    fatal_prefixes = ("execution failed", "task failed", "run failed", "运行失败", "任务失败")
    if normalized_output.startswith(fatal_prefixes):
        return "failed", "Output indicates execution failure (fatal prefix)."
    if output_indicates_hard_failure(assistant_output):
        return "failed", "Output indicates execution failure (network/tool error)."

    has_failure_marker = any(marker in normalized_output for marker in _FAILURE_MARKERS)
    has_evidence_links = ("http://" in normalized_output) or ("https://" in normalized_output)
    explicit_failure_phrases = (
        "unable to complete",
        "unable to verify",
        "could not complete",
        "cannot complete",
        "can't complete",
        "未能完成",
        "无法完成",
    )
    leading_window = normalized_output[:240]
    has_explicit_failure = any(phrase in leading_window for phrase in explicit_failure_phrases)
    if has_failure_marker and not has_evidence_links and has_explicit_failure and len(normalized_output) < 1200:
        return "failed", "Output indicates execution failure (error/exception/timeout)."

    if has_explicit_failure and "x.com" in normalized_output and "site:x.com" in normalized_output:
        return "failed", "Output indicates execution failure (target website evidence was not retrieved)."

    required_domain = _required_domain_for_workspace(workspace)
    if required_domain and not _output_contains_domain_evidence(assistant_output, required_domain):
        return "failed", f"Output does not include required domain evidence: {required_domain}."

    expected_keywords = extract_expected_keywords(workspace)
    if expected_keywords:
        missing = [kw for kw in expected_keywords if kw not in normalized_output]
        coverage = 1 - (len(missing) / len(expected_keywords))
        if coverage < 0.6:
            preview = ", ".join(missing[:5])
            suffix = "..." if len(missing) > 5 else ""
            return "failed", f"Output does not match expected result. Missing keywords: {preview}{suffix}"
    else:
        # Guard against silent success from the generic server-side fallback that
        # returns unrelated web search results (e.g. "URL 是什么" when the goal is
        # about weather).  When no explicit acceptance criteria were provided we
        # fall back to auto-derived goal tokens: if the generic fallback banner
        # is present AND none of the goal's salient tokens appear, reject.
        if _is_generic_fallback_banner(normalized_output):
            # A generic server-side fallback banner is emitted only when the model
            # produced no tool calls and no real work was done -- the runtime merely
            # stitched in an unverified public-web snippet.  Such output must never
            # be reported as "completed"; route it to soft-handoff review unless the
            # goal semantics are genuinely satisfied (e.g. a weather forecast that
            # actually covers every requested city and day).  The previous
            # `any(token in output)` escape hatch was too weak: incidental token
            # overlap (a self-check goal mentioning "CPU"/"GPU" matching an unrelated
            # CPU/GPU news page) let fake completions slip through.
            if not _goal_semantics_are_satisfied(workspace, normalized_output):
                goal_tokens = derive_goal_tokens(workspace)
                preview = ", ".join(goal_tokens[:5]) if goal_tokens else (workspace.goal or workspace.name or "")[:60]
                return (
                    "failed",
                    f"Output is a generic server-side fallback (model produced no tool calls); not accepted as completed (goal: {preview}).",
                )

    contract = detect_instruction_contract(
        workspace.goal or workspace.name,
        metadata=getattr(workspace, "metadata", None),
    )
    if contract.requires_tool_evidence:
        source_count = _source_url_count(assistant_output, contract.required_domains)
        if source_count < contract.min_evidence_links:
            return (
                "failed",
                f"Output includes {source_count} source URLs, expected at least {contract.min_evidence_links}.",
            )
    return "completed", None


def _is_status_audit_task(workspace: TaskWorkspace) -> bool:
    text = normalize_text("\n".join([workspace.name or "", workspace.goal or "", workspace.summary or ""]))
    audit_markers = ("检查", "测试", "状态", "status", "health", "汇总", "报告", "report", "audit")
    ecosystem_markers = ("skill", "skills", "mcp", "hook", "hooks", "插件", "plugin", "plugins")
    return any(marker in text for marker in audit_markers) and any(marker in text for marker in ecosystem_markers)


def _looks_like_substantive_status_report(output: str) -> bool:
    normalized_output = normalize_text(output)
    if len(normalized_output) < 120:
        return False
    report_markers = ("报告", "汇总", "summary", "status", "状态", "检查", "测试", "结果")
    ecosystem_markers = ("skill", "skills", "mcp", "hook", "hooks", "插件", "plugin", "plugins")
    evidence_markers = ("通过", "正常", "失败", "错误", "异常", "degraded", "failed", "passed", "ok", "可用", "不可用")
    return any(marker in normalized_output for marker in report_markers) and any(marker in normalized_output for marker in ecosystem_markers) and any(marker in normalized_output for marker in evidence_markers)


_GENERIC_FALLBACK_BANNERS = (
    "server-side research fallback collected public web results",
    "服务端兜底",
    "tool fallback executed by server",
)


def _is_generic_fallback_banner(normalized_output: str) -> bool:
    head = normalized_output[:400]
    return any(marker in head for marker in _GENERIC_FALLBACK_BANNERS)


_WEATHER_GOAL_ALIASES = (
    ("东京", "東京", "tokyo"),
    ("大阪", "osaka"),
    ("京都", "kyoto"),
    ("济南", "濟南", "jinan"),
)


def _goal_semantics_are_satisfied(workspace: TaskWorkspace, normalized_output: str) -> bool:
    goal_text = normalize_text(workspace.goal or workspace.name or "")
    if any(marker in goal_text for marker in ("天气", "天氣", "氣象", "weather", "forecast")):
        return _weather_goal_is_satisfied(goal_text, normalized_output)
    return False


def _weather_goal_is_satisfied(goal_text: str, normalized_output: str) -> bool:
    requested_alias_groups = [aliases for aliases in _WEATHER_GOAL_ALIASES if any(alias in goal_text for alias in aliases)]
    if not requested_alias_groups:
        return False

    city_hits = sum(1 for aliases in requested_alias_groups if any(alias in normalized_output for alias in aliases))
    if city_hits < max(1, len(requested_alias_groups)):
        return False

    has_weather_signal = any(
        marker in normalized_output
        for marker in (
            "天气",
            "天氣",
            "预报",
            "forecast",
            "weather",
            "condition",
            "temperature",
            "°c",
            "℃",
            "open-meteo",
        )
    )
    if not has_weather_signal:
        return False

    if any(marker in goal_text for marker in ("三天", "3天", "3 天", "three days", "next 3")):
        has_three_day_signal = len(re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", normalized_output)) >= 3 or any(marker in normalized_output for marker in ("未来 3", "未来3", "三天", "next 3", "3 forecast days"))
        if not has_three_day_signal:
            return False

    return True


_STOP_TOKENS = {
    # Chinese / Japanese function words that are not task-specific.
    "的",
    "了",
    "和",
    "与",
    "或",
    "及",
    "以及",
    "对",
    "向",
    "为",
    "对于",
    "关于",
    "给出",
    "请",
    "列出",
    "包含",
    "包括",
    "提供",
    "分析",
    "研究",
    "查询",
    "查找",
    "搜索",
    "检索",
    "今天",
    "明天",
    "后天",
    "未来",
    "目前",
    "最新",
    "当前",
    "实时",
    "数据",
    "结果",
    "url",
    "urls",
    "每",
    "日",
    "天",
    "地",
    "处",
    "位",
    "个",
    "条",
    "份",
    "种",
    # English stop-ish tokens.
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "at",
    "by",
    "with",
    "from",
    "a",
    "an",
    "is",
    "are",
    "be",
    "please",
    "provide",
    "list",
    "show",
    "current",
    "latest",
    "today",
    "tomorrow",
    "next",
    "day",
    "days",
    "url",
    "source",
    "sources",
}


def derive_goal_tokens(workspace: TaskWorkspace) -> list[str]:
    """Derive salient lowercase tokens from the workspace goal.

    Extracts CJK nominal spans (2-4 chars) and alphanumeric words (>=3 chars).
    Used only as a lightweight guard against unrelated-fallback false positives;
    not a substitute for explicit ``expected_keywords`` metadata.
    """
    text = (workspace.goal or workspace.name or "").lower().strip()
    if not text:
        return []
    tokens: list[str] = []
    seen: set[str] = set()
    # CJK nominal spans (length 2-4) split on punctuation / ASCII.
    for span in re.findall(r"[\u4e00-\u9fff]{2,4}", text):
        if span in _STOP_TOKENS or span in seen:
            continue
        seen.add(span)
        tokens.append(span)
    # Alphanumeric words (length >= 3).
    for word in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", text):
        if word in _STOP_TOKENS or word in seen:
            continue
        seen.add(word)
        tokens.append(word)
    return tokens[:12]


# ------------------------------------------------------------------
# Research / delegation policies
# ------------------------------------------------------------------


def requires_tool_backed_research(workspace: TaskWorkspace, prompt: str) -> bool:
    """Return True if the prompt warrants tool-backed research."""
    metadata = workspace.metadata or {}
    if metadata.get("tool_research") is False:
        return False
    contract = detect_instruction_contract(
        workspace.goal or prompt,
        metadata=metadata,
    )
    if contract.requires_tool_evidence:
        return True
    lower_prompt = prompt.lower()
    return any(marker in lower_prompt for marker in _RESEARCH_HINT_MARKERS)


def agent_supports_subagent_delegation(
    workspace: TaskWorkspace | None,
    agent_id: str,
) -> bool:
    """Return True if the given agent can delegate to sub-agents."""
    if workspace is None or workspace.mode not in {"branch", "group"}:
        return False
    target_agent = next((agent for agent in workspace.agents if agent.agent_id == agent_id), None)
    return target_agent is not None and is_management_role(target_agent.role)


__all__ = [
    "_ESCALATION_STAGE1_LIMIT",
    "_ESCALATION_STAGE2_LIMIT",
    "_ESCALATION_TOTAL_ATTEMPTS",
    "agent_supports_subagent_delegation",
    "derive_goal_tokens",
    "evaluate_task_outcome",
    "extract_expected_keywords",
    "_extract_unique_urls",
    "get_escalation_stage",
    "get_execution_retry_budget",
    "looks_like_ai_model_news_query",
    "normalize_text",
    "output_indicates_hard_failure",
    "requires_tool_backed_research",
    "resolve_execution_roles",
]
