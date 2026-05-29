"""OpenHarness-compatible default toolset adapters.

This module exposes OpenHarness-style tool names so existing prompts/agents can
invoke them directly in OctoAgent.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import UTC, datetime
from html import unescape
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from langchain.tools import ToolRuntime, tool
from langgraph.typing import ContextT

from src.agents.lead_agent.prompt import (
    get_capability_guide_prompt_section,
    get_skills_prompt_section,
)
from src.agents.subagents import SubagentExecutor, get_subagent_config
from src.agents.subagents.catalog import get_subagent_names
from src.agents.subagents.executor import cleanup_background_task, get_background_task_result
from src.agents.subagents.policy import resolve_subagent_config
from src.agents.thread_state import ThreadState
from src.runtime.config import get_app_config
from src.runtime.config.paths import get_paths
from src.tools.sandbox.tools import (
    ensure_sandbox_initialized,
    ensure_thread_directories_exist,
    get_thread_data,
    is_local_sandbox,
    replace_virtual_path,
    replace_virtual_paths_in_command,
)

_CRON_JOBS: dict[str, dict] = {}
_TASK_META: dict[str, dict] = {}
_TEAMS: dict[str, dict] = {}

_BLOCKED_SEARCH_DOMAINS = {
    "support.google.com",
    "accounts.google.com",
    "policies.google.com",
    "play.google.com",
    "apps.microsoft.com",
    "microsoft.com",
    "xnxx.com",
}

_DISCUSSION_SEARCH_DOMAINS = {
    "zhihu.com",
    "reddit.com",
    "quora.com",
}

_FUND_QUERY_MARKERS = (
    "fund",
    "funds",
    "mutual fund",
    "mutual funds",
    "etf",
    "etfs",
    "reit",
    "reits",
    "total return",
    "dividend",
    "yield",
    "基金",
    "回报率",
    "收益率",
    "分红",
    "增长率",
)

_OFFICIAL_ONLY_QUERY_MARKERS = (
    "official",
    "official site",
    "official website",
    "官方网站",
    "官网",
    "只从官方网站",
)

_NEWSLIKE_SEARCH_DOMAINS = {
    "x.com",
    "twitter.com",
    "reuters.com",
    "bloomberg.com",
    "techcrunch.com",
    "theverge.com",
    "venturebeat.com",
    "openai.com",
    "anthropic.com",
    "blog.google",
    "deepmind.google",
    "huggingface.co",
    "github.com",
    "arstechnica.com",
    "wired.com",
    "cnbc.com",
    "ft.com",
}

_BLOCKED_SEARCH_TEXT_MARKERS = {
    "adult",
    "porn",
    "xhamster",
    "xnxx",
    "xxx",
}

_UNOFFICIAL_SOURCE_TEXT_MARKERS = {
    "coupon",
    "coupon code",
    "promo code",
    "deal",
    "discount",
    "reddit",
    "quora",
    "forum",
    "discussion",
    "comment thread",
    "贴吧",
    "论坛",
    "优惠券",
}

_AGENT_BENCHMARK_QUERY_MARKERS = (
    "agent benchmark",
    "agentbench",
    "agent bench",
    "agent evaluation",
    "autonomous agent evaluation",
    "swe-bench",
    "swebench",
    "gaia benchmark",
    "terminal-bench",
    "terminal bench",
    "webarena",
    "osworld",
    "智能体评测",
    "智能体基准",
    "agent测试",
    "agent 测试",
)

_AGENT_BENCHMARK_SEED_RESULTS = [
    {
        "title": "SWE-bench",
        "href": "https://www.swebench.com/",
        "snippet": "Software engineering agent benchmark and public leaderboard for autonomous coding agents that resolve real GitHub issues and are scored against repository tests.",
        "published": "",
    },
    {
        "title": "SWE-bench Leaderboards",
        "href": "https://www.swebench.com/#leaderboards",
        "snippet": "Official SWE-bench leaderboard pages for comparing agent systems on SWE-bench Verified, Lite, and related coding-agent task sets.",
        "published": "",
    },
    {
        "title": "Terminal-Bench",
        "href": "https://www.tbench.ai/",
        "snippet": "Terminal-based agent benchmark with tasks executed and graded in isolated environments, intended for autonomous agents that use shell and tools.",
        "published": "",
    },
    {
        "title": "GAIA benchmark on Hugging Face",
        "href": "https://huggingface.co/gaia-benchmark",
        "snippet": "General AI assistant benchmark covering real-world tasks requiring reasoning, web browsing, multimodal understanding, and tool use; public submissions and results are hosted on Hugging Face.",
        "published": "",
    },
    {
        "title": "WebArena",
        "href": "https://webarena.dev/",
        "snippet": "Realistic web task benchmark where autonomous agents interact with websites and are evaluated on task completion.",
        "published": "",
    },
    {
        "title": "OSWorld",
        "href": "https://os-world.github.io/",
        "snippet": "Benchmark for multimodal computer-use agents operating real desktop environments and receiving automated task scores.",
        "published": "",
    },
    {
        "title": "AgentBench",
        "href": "https://github.com/THUDM/AgentBench",
        "snippet": "Agent benchmark suite for evaluating LLM-as-agent performance across operating-system, database, web shopping, web browsing, game, and house-holding style environments.",
        "published": "",
    },
]

_NEWS_QUERY_MARKERS = (
    "news",
    "latest",
    "recent",
    "announcement",
    "announcements",
    "release",
    "releases",
    "launch",
    "launches",
    "update",
    "updates",
    "新闻",
    "资讯",
    "最新",
    "发布",
    "上线",
)

_TASK_QUERY_NOISE_PATTERNS = (
    r"抓取",
    r"获取",
    r"收集",
    r"整理",
    r"汇总",
    r"总结",
    r"搜索",
    r"查找",
    r"检索",
    r"请",
    r"帮我",
    r"关于",
    r"有关",
    r"上最新的?",
    r"最新的?\d+条",
    r"最新\d+条",
    r"\d+条",
    r"任务",
)

_ASCII_QUERY_STOPWORDS = {
    "about",
    "and",
    "fetch",
    "find",
    "for",
    "from",
    "get",
    "latest",
    "news",
    "of",
    "on",
    "recent",
    "site",
    "the",
    "top",
    "twitter",
    "x",
}


def _clean_search_text(text: str) -> str:
    normalized = re.sub(r"<[^>]+>", " ", unescape(text or ""))
    return re.sub(r"\s+", " ", normalized).strip()


def _search_domain(url: str) -> str:
    domain = (urlparse(url).netloc or "").lower()
    return domain[4:] if domain.startswith("www.") else domain


def _looks_like_news_query(query: str) -> bool:
    normalized = (query or "").lower()
    return any(marker in normalized for marker in _NEWS_QUERY_MARKERS)


def _looks_like_fund_query(query: str) -> bool:
    normalized = (query or "").lower()
    return any(marker in normalized for marker in _FUND_QUERY_MARKERS)


def _requires_official_sources(query: str) -> bool:
    normalized = (query or "").lower()
    return any(marker in normalized for marker in _OFFICIAL_ONLY_QUERY_MARKERS)


def _query_mentions_x(query: str) -> bool:
    normalized = (query or "").lower()
    return "x.com" in normalized or "twitter" in normalized or "site:x.com" in normalized


def _required_search_domain(query: str) -> str | None:
    return "x.com" if _query_mentions_x(query) else None


def _has_explicit_source_constraint(query: str) -> bool:
    lowered = (query or "").lower()
    return _requires_official_sources(query) or "site:" in lowered or "只从" in lowered or "only from" in lowered


def _looks_like_agent_benchmark_query(query: str) -> bool:
    normalized = (query or "").lower()
    return any(marker in normalized for marker in _AGENT_BENCHMARK_QUERY_MARKERS)


def _agent_benchmark_seed_results(query: str) -> list[dict[str, str]]:
    if not _looks_like_agent_benchmark_query(query):
        return []
    return [dict(item) for item in _AGENT_BENCHMARK_SEED_RESULTS]


def _search_items_include_domain(items: list[dict[str, str]], domain: str) -> bool:
    required = domain.lower()
    return any(_search_domain(item.get("href", "")) == required for item in items)


def _extract_search_topic_terms(query: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", query or "").strip()
    lowered = normalized.lower()
    ascii_tokens = [token for token in re.findall(r"[a-z0-9][a-z0-9._+-]*", lowered) if token not in _ASCII_QUERY_STOPWORDS and not token.isdigit() and token != "x.com"]
    topic_terms: list[str] = []
    if re.search(r"\b(ai|llm|gpt|claude|gemini)\b", lowered) or "人工智能" in normalized or "大模型" in normalized:
        topic_terms.append("AI")
    if re.search(r"\b(model|models|llm|llms)\b", lowered) or "模型" in normalized or "大模型" in normalized:
        topic_terms.append("model")
    if _looks_like_news_query(normalized):
        if re.search(r"\b(top|trending|headline|headlines)\b", lowered) or any(marker in normalized for marker in ("前十", "头条", "热门", "热搜", "十大")):
            topic_terms.append("trending")
        if re.search(r"\b(today|latest|recent)\b", lowered) or any(marker in normalized for marker in ("今天", "今日", "最新")):
            topic_terms.append("today")
    if not topic_terms:
        topic_terms.extend(token.upper() if token == "ai" else token for token in ascii_tokens[:3])
    if not topic_terms and _query_mentions_x(normalized) and _looks_like_news_query(normalized):
        topic_terms.extend(["today", "trending", "headlines"])
    deduped: list[str] = []
    seen: set[str] = set()
    for token in topic_terms:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(token)
    return deduped


def _build_search_query_candidates(query: str) -> list[str]:
    raw = re.sub(r"\s+", " ", query or "").strip()
    if not raw:
        return []

    normalized_task_query = raw
    for pattern in _TASK_QUERY_NOISE_PATTERNS:
        normalized_task_query = re.sub(pattern, " ", normalized_task_query, flags=re.IGNORECASE)
    normalized_task_query = re.sub(r"\s+", " ", normalized_task_query).strip(" ，。,:;；：")

    wants_news = _looks_like_news_query(raw)
    wants_x = _query_mentions_x(raw)
    wants_funds = _looks_like_fund_query(raw)
    topic_terms = _extract_search_topic_terms(raw)

    candidates: list[str] = [raw]
    if normalized_task_query and normalized_task_query != raw:
        candidates.append(normalized_task_query)

    if topic_terms:
        general_terms: list[str] = []
        if wants_news:
            general_terms.append("latest")
        general_terms.extend(topic_terms)
        if wants_news:
            general_terms.append("news")
        candidates.append(" ".join(general_terms))
        candidates.append(" ".join(topic_terms))
        if wants_x:
            x_terms = ["site:x.com"]
            if wants_news:
                x_terms.append("latest")
            x_terms.extend(topic_terms)
            if wants_news:
                x_terms.append("news")
            candidates.append(" ".join(x_terms))
            candidates.append(" ".join(["site:x.com", *topic_terms]))

    if wants_x and wants_news:
        candidates.extend(
            [
                "site:x.com latest news",
                "site:x.com today trending headlines",
                "site:x.com top news today",
                "x.com trending headlines today",
            ]
        )
        if topic_terms:
            candidates.extend(
                [
                    " ".join(["site:x.com", *topic_terms, "today", "news"]),
                    " ".join(["site:x.com", "trending", *topic_terms]),
                ]
            )

    if wants_funds:
        fund_terms = ["US", "funds", "total return", "dividend", "official"]
        candidates.append(" ".join(fund_terms))
        candidates.append("US mutual funds total return dividend official website")
        candidates.append("US ETF total return dividend official website")
        candidates.append("SEC fund prospectus total return dividend")

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized_candidate = re.sub(r"\s+", " ", candidate).strip()
        key = normalized_candidate.lower()
        if not normalized_candidate or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized_candidate)
    return deduped[:6]


def _parse_bing_rss(text: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    parsed: list[dict[str, str]] = []
    for item in root.findall("./channel/item"):
        title = _clean_search_text(item.findtext("title", default=""))
        href = _clean_search_text(item.findtext("link", default=""))
        snippet = _clean_search_text(item.findtext("description", default=""))
        published = _clean_search_text(item.findtext("pubDate", default=""))
        if title and href:
            parsed.append(
                {
                    "title": title,
                    "href": href,
                    "snippet": snippet,
                    "published": published,
                }
            )
    return parsed


def _parse_bing_html(html: str) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    blocks = re.findall(r'<li[^>]+class="b_algo"([\s\S]*?)</li>', html)
    for block in blocks:
        a_tags = re.findall(r'<a\s[^>]*href="(https?://[^"]+)"[^>]*>([\s\S]*?)</a>', block)
        if not a_tags:
            continue
        href, title_html = a_tags[0]
        title = _clean_search_text(title_html)
        snippet_match = re.search(r'<p[^>]*class="[^"]*b_[^"]*"[^>]*>([\s\S]*?)</p>', block)
        snippet = _clean_search_text(snippet_match.group(1)) if snippet_match else ""
        if title and href:
            parsed.append(
                {
                    "title": title,
                    "href": href,
                    "snippet": snippet,
                    "published": "",
                }
            )
    return parsed


def _parse_markdown_links(text: str) -> list[dict[str, str]]:
    links = re.findall(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", text)
    parsed: list[dict[str, str]] = []
    seen: set[str] = set()
    for title, href in links:
        clean_title = _clean_search_text(title)
        if href in seen:
            continue
        seen.add(href)
        if clean_title and href:
            parsed.append(
                {
                    "title": clean_title,
                    "href": href,
                    "snippet": "",
                    "published": "",
                }
            )
    return parsed


def _score_search_result(item: dict[str, str], original_query: str, candidate_query: str) -> int:
    haystack = " ".join(
        filter(
            None,
            [
                item.get("title", ""),
                item.get("snippet", ""),
                item.get("href", ""),
                item.get("published", ""),
            ],
        )
    ).lower()
    domain = _search_domain(item.get("href", ""))
    score = 0

    for token in _extract_search_topic_terms(original_query):
        if token.lower() in haystack:
            score += 4
    for token in _extract_search_topic_terms(candidate_query):
        if token.lower() in haystack:
            score += 2

    if _looks_like_news_query(original_query):
        if any(marker in haystack for marker in _NEWS_QUERY_MARKERS):
            score += 3
        if domain in _NEWSLIKE_SEARCH_DOMAINS:
            score += 5
        if domain in _DISCUSSION_SEARCH_DOMAINS:
            score -= 2

    if _query_mentions_x(original_query):
        if domain == "x.com":
            score += 8
        elif domain in _NEWSLIKE_SEARCH_DOMAINS:
            score += 1
        else:
            score -= 3

    if domain in _BLOCKED_SEARCH_DOMAINS:
        score -= 10
    if any(marker in haystack for marker in _BLOCKED_SEARCH_TEXT_MARKERS):
        score -= 20
    if _looks_like_fund_query(original_query):
        if any(marker in haystack for marker in ("fund", "funds", "etf", "reit", "total return", "dividend", "distribution", "基金", "收益率", "回报率", "分红")):
            score += 10
        if domain in _DISCUSSION_SEARCH_DOMAINS:
            score -= 15
    if _looks_like_agent_benchmark_query(original_query):
        if any(marker in haystack for marker in ("swe-bench", "swebench", "terminal-bench", "tbench", "gaia", "webarena", "osworld", "agentbench")):
            score += 12
        if domain in {"swebench.com", "tbench.ai", "huggingface.co", "webarena.dev", "os-world.github.io", "github.com"}:
            score += 8
    if item.get("published"):
        score += 1
    return score


def _satisfies_source_constraint(item: dict[str, str], query: str) -> bool:
    if not _has_explicit_source_constraint(query):
        return True
    href = item.get("href", "")
    domain = _search_domain(href)
    required_domain = _required_search_domain(query)
    if required_domain and domain != required_domain:
        return False
    haystack = " ".join(filter(None, [item.get("title", ""), item.get("snippet", ""), href])).lower()
    if domain in _DISCUSSION_SEARCH_DOMAINS:
        return False
    if any(marker in haystack for marker in _UNOFFICIAL_SOURCE_TEXT_MARKERS):
        return False
    return True


def _format_search_rows(items: list[dict[str, str]], max_results: int) -> str:
    rows: list[str] = []
    for idx, item in enumerate(items[: max(1, min(max_results, 10))], start=1):
        detail_lines = [f"{idx}. {item['title']}"]
        meta_parts = []
        domain = _search_domain(item["href"])
        if domain:
            meta_parts.append(domain)
        if item.get("published"):
            meta_parts.append(item["published"])
        if meta_parts:
            detail_lines.append(" | ".join(meta_parts))
        detail_lines.append(item["href"])
        if item.get("snippet"):
            detail_lines.append(item["snippet"])
        rows.append("\n".join(detail_lines))
    return "\n\n".join(rows)


def _safe_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _resolve_path(runtime: ToolRuntime[ContextT, ThreadState], path: str) -> str:
    if is_local_sandbox(runtime):
        thread_data = get_thread_data(runtime)
        return replace_virtual_path(path, thread_data)
    return path


async def _run_shell(runtime: ToolRuntime[ContextT, ThreadState], command: str) -> str:
    # ``Sandbox.execute_command`` is an async coroutine; callers used to invoke
    # this helper from sync tools and returned the coroutine object verbatim,
    # which generated the ``coroutine ... was never awaited`` warning and
    # caused the model to loop until LangGraph's recursion ceiling.
    sandbox = ensure_sandbox_initialized(runtime)
    ensure_thread_directories_exist(runtime)
    if is_local_sandbox(runtime):
        thread_data = get_thread_data(runtime)
        command = replace_virtual_paths_in_command(command, thread_data)
    return await sandbox.execute_command(command)


def _spawn_subagent_task(
    runtime: ToolRuntime[ContextT, ThreadState],
    prompt: str,
    *,
    subagent_type: str = "general-purpose",
    max_turns: int | None = None,
) -> str:
    subagent_type = subagent_type.strip()
    config = get_subagent_config(subagent_type)
    if config is None:
        raise ValueError(f"Unknown subagent type: {subagent_type}. Available: {', '.join(get_subagent_names())}")

    skills_section = get_skills_prompt_section()
    capability_section = get_capability_guide_prompt_section()
    prompt_sections = [section for section in (skills_section, capability_section) if section]
    if prompt_sections:
        config.system_prompt = config.system_prompt + "\n\n" + "\n\n".join(prompt_sections)
    config, _budget = resolve_subagent_config(config, max_turns=max_turns)

    sandbox_state = runtime.state.get("sandbox") if runtime and runtime.state else None
    thread_data = runtime.state.get("thread_data") if runtime and runtime.state else None
    thread_id = runtime.context.get("thread_id") if runtime else None
    metadata = runtime.config.get("metadata", {}) if runtime else {}
    parent_model = metadata.get("model_name")

    from src.tools import get_available_tools

    tools = get_available_tools(model_name=parent_model, subagent_enabled=False)
    executor = SubagentExecutor(
        config=config,
        tools=tools,
        parent_model=parent_model,
        sandbox_state=sandbox_state,
        thread_data=thread_data,
        thread_id=thread_id,
    )
    task_id = f"oh-task-{uuid.uuid4().hex[:12]}"
    executor.execute_async(prompt, task_id=task_id)
    _TASK_META[task_id] = {
        "task_id": task_id,
        "prompt": prompt,
        "status": "running",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "subagent_type": subagent_type,
    }
    return task_id


def _sync_task_status(task_id: str) -> dict:
    meta = _TASK_META.get(task_id)
    if meta is None:
        return {"task_id": task_id, "status": "not_found"}
    result = get_background_task_result(task_id)
    if result is None:
        return meta
    status = str(result.status.value)
    meta["status"] = status
    meta["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if result.error:
        meta["error"] = result.error
    if result.result:
        meta["result"] = result.result
    return meta


@tool("ask_user_question", parse_docstring=True)
def ask_user_question_tool(question: str) -> str:
    """Request clarification from the user.

    Args:
        question: The question to ask the user.
    """
    return f"User clarification required: {question}"


@tool("edit_file", parse_docstring=True)
def edit_file_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    path: str,
    old_text: str,
    new_text: str,
) -> str:
    """Edit a file by replacing one exact text block.

    Args:
        path: Absolute path to the file.
        old_text: Existing text to replace.
        new_text: Replacement text.
    """
    sandbox = ensure_sandbox_initialized(runtime)
    ensure_thread_directories_exist(runtime)
    path = _resolve_path(runtime, path)
    content = sandbox.read_file(path)
    if old_text not in content:
        return "Error: old_text not found"
    sandbox.write_file(path, content.replace(old_text, new_text, 1))
    return "OK"


@tool("glob", parse_docstring=True)
async def glob_tool(runtime: ToolRuntime[ContextT, ThreadState], pattern: str, root: str = "/mnt/user-data/workspace") -> str:
    """Find files by glob-like pattern.

    Args:
        pattern: Glob pattern (e.g. **/*.py).
        root: Root directory.
    """
    root = _resolve_path(runtime, root)
    cmd = f"cd {json.dumps(root)} && find . -path {json.dumps(pattern)} | sed 's#^./##'"
    return await _run_shell(runtime, cmd)


@tool("grep", parse_docstring=True)
async def grep_tool(runtime: ToolRuntime[ContextT, ThreadState], query: str, root: str = "/mnt/user-data/workspace") -> str:
    """Search text in files.

    Args:
        query: Regex or keyword.
        root: Root directory to search.
    """
    root = _resolve_path(runtime, root)
    cmd = f"cd {json.dumps(root)} && (rg -n --hidden --glob '!.git' {json.dumps(query)} . || true)"
    return await _run_shell(runtime, cmd)


@tool("web_search", parse_docstring=True)
def web_search_tool(query: str, max_results: int = 5) -> str:
    """Search the web and return top results.

    Args:
        query: Search query.
        max_results: Maximum result count.
    """
    queries = _build_search_query_candidates(query)
    if not queries:
        return "Search query is empty."

    errors: list[str] = []
    ranked_results: dict[str, dict[str, str | int]] = {}
    fallback_pool: list[dict[str, str]] = []
    required_domain = _required_search_domain(query)
    strict_domain_match = bool(required_domain and _looks_like_news_query(query))
    has_source_constraint = _has_explicit_source_constraint(query)

    def _record_results(items: list[dict[str, str]], candidate_query: str) -> None:
        for item in items:
            href = item.get("href", "")
            if not href:
                continue
            score = _score_search_result(item, query, candidate_query)
            if score > 0:
                existing = ranked_results.get(href)
                if existing is None or score > int(existing["score"]):
                    ranked_results[href] = {**item, "score": score}
            if len(fallback_pool) < 20:
                fallback_pool.append(item)

    seed_results = _agent_benchmark_seed_results(query)
    if seed_results:
        _record_results(seed_results, query)

    for candidate_query in queries:
        q = quote_plus(candidate_query)

        # Backend 1: Bing RSS (stable, structured, includes description + pubDate)
        try:
            req = Request(
                url=f"https://www.bing.com/search?format=rss&q={q}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urlopen(req, timeout=8) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
            parsed = _parse_bing_rss(text)
            if parsed:
                _record_results(parsed, candidate_query)
                if len(ranked_results) >= max_results:
                    continue
            else:
                errors.append(f"bing_rss:{candidate_query}:no_results")
        except Exception as exc:
            errors.append(f"bing_rss:{candidate_query}:{type(exc).__name__}")

        # Backend 2: Bing HTML fallback
        try:
            req = Request(
                url=f"https://www.bing.com/search?q={q}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urlopen(req, timeout=8) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            parsed = _parse_bing_html(html)
            if parsed:
                _record_results(parsed, candidate_query)
                if len(ranked_results) >= max_results:
                    continue
            else:
                errors.append(f"bing_html:{candidate_query}:no_results")
        except Exception as exc:
            errors.append(f"bing_html:{candidate_query}:{type(exc).__name__}")

        # Backend 3: direct DuckDuckGo HTML
        try:
            req = Request(
                url=f"https://duckduckgo.com/html/?q={q}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urlopen(req, timeout=8) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            links = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html)
            parsed = [{"title": _clean_search_text(title_html), "href": href, "snippet": "", "published": ""} for href, title_html in links if href and _clean_search_text(title_html)]
            if parsed:
                _record_results(parsed, candidate_query)
                if len(ranked_results) >= max_results:
                    continue
            else:
                errors.append(f"duckduckgo:{candidate_query}:no_results")
        except Exception as exc:
            errors.append(f"duckduckgo:{candidate_query}:{type(exc).__name__}")

        # Backend 4: jina search proxy fallback (text/markdown response)
        try:
            req = Request(
                url=f"https://s.jina.ai/{q}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urlopen(req, timeout=10) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
            parsed = _parse_markdown_links(text)
            if parsed:
                _record_results(parsed, candidate_query)
            else:
                errors.append(f"jina:{candidate_query}:no_results")
        except Exception as exc:
            errors.append(f"jina:{candidate_query}:{type(exc).__name__}")

    if ranked_results:
        ranked = sorted(
            ranked_results.values(),
            key=lambda item: (int(item["score"]), bool(item.get("published"))),
            reverse=True,
        )
        if strict_domain_match and required_domain:
            ranked = [item for item in ranked if _search_domain(str(item.get("href", ""))) == required_domain]
            if not ranked:
                return f"Search results unavailable: required domain {required_domain} not found for strict query. Query: {query}"
        if has_source_constraint:
            ranked = [item for item in ranked if _satisfies_source_constraint(item, query)]
            if not ranked:
                return (
                    "Search results unavailable: no relevant results satisfied the explicit source constraint. "
                    "Use a narrower query with a known issuer, ticker, organization, domain, or official page if the task requires verified official sources. "
                    f"Query: {query}"
                )
        return _format_search_rows(
            [
                {
                    "title": str(item["title"]),
                    "href": str(item["href"]),
                    "snippet": str(item.get("snippet", "")),
                    "published": str(item.get("published", "")),
                }
                for item in ranked
            ],
            max_results,
        )

    if fallback_pool:
        deduped_pool: list[dict[str, str]] = []
        seen_pool: set[str] = set()
        for item in fallback_pool:
            href = item.get("href", "")
            if not href or href in seen_pool:
                continue
            seen_pool.add(href)
            deduped_pool.append(item)
        if strict_domain_match and required_domain:
            if not _search_items_include_domain(deduped_pool, required_domain):
                return f"Search results unavailable: required domain {required_domain} not found for strict query. Query: {query}"
            deduped_pool = [item for item in deduped_pool if _search_domain(item.get("href", "")) == required_domain]
        if has_source_constraint:
            constrained_pool = [item for item in deduped_pool if _satisfies_source_constraint(item, query) and _score_search_result(item, query, query) > 0]
            if not constrained_pool:
                return f"Search results unavailable: fallback results did not satisfy the explicit source constraint or relevance threshold. They were suppressed to avoid spending tool calls on unrelated pages. Query: {query}"
            deduped_pool = constrained_pool
        return _format_search_rows(deduped_pool, max_results)

    # Do not raise here. Tool exceptions crash LangGraph runs.
    # Return deterministic fallback links so agents can still continue evidence collection.
    if has_source_constraint:
        return (
            "Search backend unavailable: this query includes an explicit source constraint, and no relevant constrained results were found. "
            "Ask for a narrower organization, ticker, domain, or official page, or retry later. "
            f"Tried backends: {', '.join(errors)}"
        )

    fallback_links = [
        {
            "title": "Hugging Face model search",
            "href": f"https://huggingface.co/models?search={quote_plus(query)}",
            "snippet": "Browse public model releases and trending model pages.",
            "published": "",
        },
        {
            "title": "OpenRouter model catalog",
            "href": "https://openrouter.ai/models",
            "snippet": "Catalog of public frontier and open models.",
            "published": "",
        },
        {
            "title": "Papers With Code SOTA",
            "href": "https://paperswithcode.com/sota",
            "snippet": "Track state-of-the-art model updates and benchmarks.",
            "published": "",
        },
        {
            "title": "GitHub trending repositories",
            "href": "https://github.com/trending",
            "snippet": "Manual verification source for newly trending AI repositories.",
            "published": "",
        },
    ]
    header = f"Search backend unavailable right now; returning fallback public sources for manual verification. Tried backends: {', '.join(errors)}"
    return header + "\n\n" + _format_search_rows(fallback_links, max_results)


@tool("tool_search", parse_docstring=True)
def tool_search_tool(query: str) -> str:
    """Search available tool names and descriptions.

    Args:
        query: Keyword to match.
    """
    from src.tools import get_available_tools

    q = query.lower().strip()
    tools = get_available_tools(subagent_enabled=True)
    hits = []
    for t in tools:
        text = f"{t.name} {getattr(t, 'description', '')}".lower()
        if q in text:
            hits.append(f"- {t.name}: {getattr(t, 'description', '')}")
    return "\n".join(hits[:50]) if hits else "No matching tools."


@tool("lsp", parse_docstring=True)
async def lsp_tool(runtime: ToolRuntime[ContextT, ThreadState], symbol: str, root: str = "/mnt/user-data/workspace") -> str:
    """Find symbol references with a fast text fallback.

    Args:
        symbol: Symbol or identifier name.
        root: Workspace root.
    """
    root = _resolve_path(runtime, root)
    cmd = f"cd {json.dumps(root)} && (rg -n --hidden --glob '!.git' --word-regexp {json.dumps(symbol)} . || true)"
    return await _run_shell(runtime, cmd)


@tool("notebook_edit", parse_docstring=True)
def notebook_edit_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    path: str,
    cell_index: int,
    new_source: str,
) -> str:
    """Edit a notebook code/markdown cell by index.

    Args:
        path: Notebook .ipynb absolute path.
        cell_index: Zero-based cell index.
        new_source: New source text for that cell.
    """
    sandbox = ensure_sandbox_initialized(runtime)
    ensure_thread_directories_exist(runtime)
    path = _resolve_path(runtime, path)
    raw = sandbox.read_file(path)
    data = json.loads(raw)
    cells = data.get("cells", [])
    if cell_index < 0 or cell_index >= len(cells):
        return f"Error: cell_index out of range (0..{max(0, len(cells) - 1)})"
    cells[cell_index]["source"] = [line + "\n" for line in new_source.splitlines()]
    sandbox.write_file(path, json.dumps(data, ensure_ascii=False, indent=2))
    return "OK"


@tool("config", parse_docstring=True)
def config_tool() -> str:
    """Show active model/tool configuration summary."""
    app = get_app_config()
    mem = getattr(app, "memory", None)
    if isinstance(mem, dict):
        memory_enabled = mem.get("enabled", False)
    else:
        memory_enabled = getattr(mem, "enabled", False) if mem is not None else False
    return _safe_json(
        {
            "models": [m.name for m in app.models],
            "tool_count": len(app.tools),
            "tool_groups": [g.name for g in app.tool_groups],
            "memory_enabled": memory_enabled,
            "sandbox": app.sandbox.use,
        }
    )


@tool("brief", parse_docstring=True)
def brief_tool(text: str, max_chars: int = 600) -> str:
    """Create a concise brief summary.

    Args:
        text: Source text.
        max_chars: Max output length.
    """
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3] + "..."


@tool("sleep", parse_docstring=True)
def sleep_tool(seconds: int) -> str:
    """Pause execution for a short duration.

    Args:
        seconds: Sleep seconds (max 30).
    """
    duration = max(0, min(seconds, 30))
    time.sleep(duration)
    return f"Slept for {duration} second(s)."


@tool("enter_plan_mode", parse_docstring=True)
def enter_plan_mode_tool(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    """Enable plan mode for this thread runtime."""
    runtime.state["openharness_plan_mode"] = True
    return "Plan mode enabled."


@tool("exit_plan_mode", parse_docstring=True)
def exit_plan_mode_tool(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    """Disable plan mode for this thread runtime."""
    runtime.state["openharness_plan_mode"] = False
    return "Plan mode disabled."


@tool("enter_worktree", parse_docstring=True)
def enter_worktree_tool(runtime: ToolRuntime[ContextT, ThreadState], path: str) -> str:
    """Set active worktree path in runtime context.

    Args:
        path: Worktree absolute path.
    """
    runtime.state["openharness_worktree"] = path
    return f"Worktree set to {path}"


@tool("exit_worktree", parse_docstring=True)
def exit_worktree_tool(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    """Clear active worktree path."""
    runtime.state.pop("openharness_worktree", None)
    return "Worktree cleared."


@tool("todo_write", parse_docstring=True)
def todo_write_tool(runtime: ToolRuntime[ContextT, ThreadState], item: str, done: bool = False, path: str = "/mnt/user-data/workspace/TODO.md") -> str:
    """Append a TODO item to a markdown file.

    Args:
        item: Todo content.
        done: Whether item is completed.
        path: Target TODO markdown path.
    """
    sandbox = ensure_sandbox_initialized(runtime)
    ensure_thread_directories_exist(runtime)
    path = _resolve_path(runtime, path)
    prefix = "- [x]" if done else "- [ ]"
    line = f"{prefix} {item}\n"
    try:
        old = sandbox.read_file(path)
    except Exception:
        old = "# TODO\n\n"
    sandbox.write_file(path, old + line)
    return "OK"


@tool("cron_create", parse_docstring=True)
def cron_create_tool(cron_expr: str, action: str, enabled: bool = True) -> str:
    """Create a logical cron job entry.

    Args:
        cron_expr: Cron expression.
        action: Trigger action text.
        enabled: Initial enabled status.
    """
    job_id = f"cron-{uuid.uuid4().hex[:8]}"
    _CRON_JOBS[job_id] = {
        "id": job_id,
        "cron": cron_expr,
        "action": action,
        "enabled": enabled,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    return _safe_json(_CRON_JOBS[job_id])


@tool("cron_list", parse_docstring=True)
def cron_list_tool() -> str:
    """List all logical cron jobs."""
    return _safe_json(list(_CRON_JOBS.values()))


@tool("cron_delete", parse_docstring=True)
def cron_delete_tool(job_id: str) -> str:
    """Delete a logical cron job.

    Args:
        job_id: Cron job id.
    """
    existed = _CRON_JOBS.pop(job_id, None)
    return "OK" if existed else f"Error: job not found: {job_id}"


@tool("cron_toggle", parse_docstring=True)
def cron_toggle_tool(job_id: str, enabled: bool) -> str:
    """Enable or disable a cron job.

    Args:
        job_id: Cron job id.
        enabled: New enabled state.
    """
    job = _CRON_JOBS.get(job_id)
    if job is None:
        return f"Error: job not found: {job_id}"
    job["enabled"] = enabled
    return _safe_json(job)


@tool("remote_trigger", parse_docstring=True)
def remote_trigger_tool(trigger_id: str, payload: str = "") -> str:
    """Trigger a logical remote action.

    Args:
        trigger_id: Trigger or cron job id.
        payload: Optional payload.
    """
    job = _CRON_JOBS.get(trigger_id)
    if job is None:
        return _safe_json({"trigger_id": trigger_id, "status": "accepted", "payload": payload})
    return _safe_json({"trigger_id": trigger_id, "status": "accepted", "action": job["action"], "payload": payload})


@tool("task_create", parse_docstring=True)
def task_create_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    prompt: str,
    subagent_type: str = "general-purpose",
    max_turns: int | None = None,
) -> str:
    """Create an asynchronous subagent task.

    Args:
        prompt: Task prompt.
        subagent_type: Subagent type.
        max_turns: Optional max turns.
    """
    task_id = _spawn_subagent_task(runtime, prompt, subagent_type=subagent_type, max_turns=max_turns)
    return _safe_json({"task_id": task_id, "status": "running"})


@tool("task_get", parse_docstring=True)
def task_get_tool(task_id: str) -> str:
    """Get task status by id.

    Args:
        task_id: Task id.
    """
    return _safe_json(_sync_task_status(task_id))


@tool("task_list", parse_docstring=True)
def task_list_tool() -> str:
    """List known tasks and statuses."""
    for task_id in list(_TASK_META.keys()):
        _sync_task_status(task_id)
    return _safe_json(list(_TASK_META.values()))


@tool("task_output", parse_docstring=True)
def task_output_tool(task_id: str) -> str:
    """Get task result output if available.

    Args:
        task_id: Task id.
    """
    meta = _sync_task_status(task_id)
    if meta.get("result"):
        return str(meta["result"])
    if meta.get("error"):
        return f"Error: {meta['error']}"
    return f"Task {task_id} status: {meta.get('status', 'unknown')}"


@tool("task_stop", parse_docstring=True)
def task_stop_tool(task_id: str) -> str:
    """Stop/cleanup a background task by id.

    Args:
        task_id: Task id.
    """
    cleanup_background_task(task_id)
    meta = _TASK_META.get(task_id)
    if meta is not None:
        meta["status"] = "stopped"
        meta["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return "OK"


@tool("task_update", parse_docstring=True)
def task_update_tool(task_id: str, note: str) -> str:
    """Update local task metadata note.

    Args:
        task_id: Task id.
        note: Metadata note.
    """
    meta = _TASK_META.get(task_id)
    if meta is None:
        return f"Error: task not found: {task_id}"
    meta["note"] = note
    meta["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return _safe_json(meta)


@tool("agent", parse_docstring=True)
def agent_tool(role: str, objective: str) -> str:
    """Create a logical agent entry.

    Args:
        role: Agent role.
        objective: Agent objective.
    """
    agent_id = f"agent-{uuid.uuid4().hex[:8]}"
    return _safe_json({"agent_id": agent_id, "role": role, "objective": objective})


@tool("send_message", parse_docstring=True)
def send_message_tool(agent_id: str, message: str) -> str:
    """Send a message to a logical agent handle.

    Args:
        agent_id: Agent id.
        message: Message text.
    """
    return _safe_json({"agent_id": agent_id, "delivered": True, "message": message})


@tool("team_create", parse_docstring=True)
def team_create_tool(name: str, members: str = "") -> str:
    """Create a logical team.

    Args:
        name: Team name.
        members: Comma-separated members.
    """
    team_id = f"team-{uuid.uuid4().hex[:8]}"
    _TEAMS[team_id] = {
        "team_id": team_id,
        "name": name,
        "members": [item.strip() for item in members.split(",") if item.strip()],
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    return _safe_json(_TEAMS[team_id])


@tool("team_delete", parse_docstring=True)
def team_delete_tool(team_id: str) -> str:
    """Delete a logical team.

    Args:
        team_id: Team id.
    """
    existed = _TEAMS.pop(team_id, None)
    return "OK" if existed else f"Error: team not found: {team_id}"


@tool("skill", parse_docstring=True)
def skill_tool(name: str) -> str:
    """Load skill markdown content by skill folder name.

    Args:
        name: Skill name (folder name).
    """
    base = get_paths().base_dir
    # Primary location: {base_dir}/skills/{name}/SKILL.md
    candidates = [base / "skills" / name / "SKILL.md"]
    # Fallback: project-level skills directories (public/private)
    project_root = base.parent.parent
    for sub in ["public", "private", ""]:
        p = (project_root / "skills" / sub / name / "SKILL.md") if sub else (project_root / "skills" / name / "SKILL.md")
        candidates.append(p)
    for skill_file in candidates:
        if skill_file.exists():
            return skill_file.read_text(encoding="utf-8")
    return f"Error: skill not found: {name}"


@tool("mcp_auth", parse_docstring=True)
def mcp_auth_tool(server: str) -> str:
    """Show MCP authentication guidance for a server.

    Args:
        server: MCP server name.
    """
    return f"MCP auth is configured via extensions_config.json env/oauth settings. Server='{server}'. Please configure token/env and reinitialize MCP tools."


@tool("list_mcp_resources", parse_docstring=True)
def list_mcp_resources_tool() -> str:
    """List MCP-style tool resources available in current cache."""
    from src.tools.mcp.cache import get_cached_mcp_tools

    tools = get_cached_mcp_tools()
    rows = [{"name": t.name, "description": getattr(t, "description", "")} for t in tools]
    return _safe_json(rows)


@tool("read_mcp_resource", parse_docstring=True)
def read_mcp_resource_tool(resource: str) -> str:
    """Read an MCP resource reference (compat fallback).

    Args:
        resource: MCP resource URI or key.
    """
    return f"Direct MCP resource read is transport-specific in this build. Use MCP tool calls directly or inspect available tools. Requested: {resource}"


@tool("mcp_tool", parse_docstring=True)
def mcp_tool_proxy(tool_name: str, arguments_json: str = "{}") -> str:
    """Invoke a cached MCP tool by name with JSON arguments.

    Args:
        tool_name: MCP tool name.
        arguments_json: JSON object arguments.
    """
    from src.tools.mcp.cache import get_cached_mcp_tools

    args = json.loads(arguments_json or "{}")
    for mcp_t in get_cached_mcp_tools():
        if mcp_t.name != tool_name:
            continue
        try:
            # LangChain BaseTool interface
            return str(mcp_t.invoke(args))
        except Exception as exc:
            return f"Error invoking MCP tool '{tool_name}': {exc}"
    return f"Error: MCP tool not found: {tool_name}"


# ── Missing OpenHarness tools: bash, file_read, file_write, web_fetch ─────────


@tool("bash", parse_docstring=True)
def bash_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    command: str,
    cwd: str = "/mnt/user-data/workspace",
) -> str:
    """Execute a shell command and return its output.

    Use for: running scripts, installing packages, file system ops, git commands.
    The command runs in the sandbox with the given working directory.

    Args:
        command: Shell command to execute.
        cwd: Working directory (default: workspace root).
    """
    cwd = _resolve_path(runtime, cwd)
    full_cmd = f"cd {json.dumps(cwd)} && {command}"
    return _run_shell(runtime, full_cmd)


@tool("file_read", parse_docstring=True)
def file_read_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    path: str,
    offset: int = 0,
    limit: int = 2000,
) -> str:
    """Read the content of a file.

    Args:
        path: Absolute path to the file.
        offset: Start line number (0-indexed).
        limit: Maximum number of lines to return.
    """
    sandbox = ensure_sandbox_initialized(runtime)
    ensure_thread_directories_exist(runtime)
    path = _resolve_path(runtime, path)
    try:
        content = sandbox.read_file(path)
    except Exception as exc:
        return f"Error reading file: {exc}"
    lines = content.splitlines()
    slice_ = lines[offset : offset + limit]
    suffix = f"\n…[{len(lines) - offset - limit} more lines not shown]" if offset + limit < len(lines) else ""
    return "\n".join(slice_) + suffix


@tool("file_write", parse_docstring=True)
def file_write_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    path: str,
    content: str,
) -> str:
    """Write content to a file (creates or overwrites).

    Args:
        path: Absolute path to the file.
        content: New file content.
    """
    sandbox = ensure_sandbox_initialized(runtime)
    ensure_thread_directories_exist(runtime)
    path = _resolve_path(runtime, path)
    try:
        sandbox.write_file(path, content)
        return "OK"
    except Exception as exc:
        return f"Error writing file: {exc}"


@tool("web_fetch", parse_docstring=True)
def web_fetch_tool(url: str, max_chars: int = 12000) -> str:
    """Fetch a web page and return compact readable text.

    Alias for read_webpage — preferred tool name matching OpenHarness conventions.
    Use for: fetching news articles, API docs, search result pages, etc.

    Args:
        url: HTTP or HTTPS URL to fetch.
        max_chars: Maximum characters to return (default: 12000).
    """
    import re
    from urllib.request import Request, urlopen

    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (OctoAgent/1.0)"})
        with urlopen(req, timeout=20) as resp:
            ct = resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8", errors="ignore")
        if "html" in ct:
            # Strip scripts/styles then tags
            body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body)
            body = re.sub(r"<[^>]+>", " ", body)
            body = body.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            body = re.sub(r"[ \t\r\f\v]+", " ", body).replace(" \n", "\n").strip()
        if len(body) > max_chars:
            body = body[:max_chars].rstrip() + "\n…[truncated]"
        return f"URL: {url}\n\n{body}"
    except Exception as exc:
        return f"web_fetch failed: {exc}"


OPENHARNESS_COMPAT_TOOLS = [
    ask_user_question_tool,
    edit_file_tool,
    glob_tool,
    grep_tool,
    web_search_tool,
    tool_search_tool,
    lsp_tool,
    notebook_edit_tool,
    config_tool,
    brief_tool,
    sleep_tool,
    enter_plan_mode_tool,
    exit_plan_mode_tool,
    enter_worktree_tool,
    exit_worktree_tool,
    todo_write_tool,
    cron_create_tool,
    cron_list_tool,
    cron_delete_tool,
    cron_toggle_tool,
    remote_trigger_tool,
    task_create_tool,
    task_get_tool,
    task_list_tool,
    task_output_tool,
    task_stop_tool,
    task_update_tool,
    agent_tool,
    send_message_tool,
    team_create_tool,
    team_delete_tool,
    skill_tool,
    mcp_auth_tool,
    list_mcp_resources_tool,
    read_mcp_resource_tool,
    mcp_tool_proxy,
    # New tools (bash, file I/O, web_fetch)
    bash_tool,
    file_read_tool,
    file_write_tool,
    web_fetch_tool,
]
