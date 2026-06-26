"""Server-side research fallback helpers for task workspace execution."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s)\\>\"'，。；：、）\]】]+")
_AI_MODEL_NEWS_RSS_SOURCES = [
    {
        "name": "OpenAI News",
        "url": "https://openai.com/news/rss.xml",
        "link_markers": ("openai.com/news/",),
    },
    {
        "name": "Google AI",
        "url": "https://blog.google/rss/",
        "link_markers": (
            "/innovation-and-ai/",
            "/products/gemini",
            "/products/notebooklm",
            "/models-and-research/",
        ),
    },
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "link_markers": ("techcrunch.com/",),
    },
    {
        "name": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
        "link_markers": ("theverge.com/ai", "theverge.com/202", "theverge.com/"),
    },
]
_AI_MODEL_NEWS_PAGE_SOURCES = [
    {
        "name": "Anthropic News",
        "url": "https://www.anthropic.com/news",
        "href_pattern": r"/(?:news|research)/[^\"#?]+",
    },
    {
        "name": "Anthropic Research",
        "url": "https://www.anthropic.com/research",
        "href_pattern": r"/(?:news|research)/[^\"#?]+",
    },
    {
        "name": "Google DeepMind",
        "url": "https://deepmind.google/discover/blog/",
        "href_pattern": r"(?:https://deepmind\.google)?/(?:discover/)?blog/[^\"#?]+|https://deepmind\.google/science/[^\"#?]+",
    },
]
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
_AI_NEWS_SOURCE_MARKERS = (
    "openai",
    "anthropic",
    "google ai",
    "google deepmind",
    "deepmind",
    "techcrunch ai",
    "the verge",
)
_AI_NEWS_SOURCE_PRIORITIES = {
    "OpenAI News": 50,
    "Google AI": 45,
    "Google DeepMind": 40,
    "Anthropic News": 35,
    "Anthropic Research": 30,
    "TechCrunch AI": 15,
    "The Verge": 10,
}
_AI_NEWS_FETCH_CONNECT_TIMEOUT = 5
_AI_NEWS_RSS_READ_TIMEOUT = 8
_AI_NEWS_PAGE_READ_TIMEOUT = 10
_SINA_NEWS_SOURCE_URLS = [
    {
        "name": "新浪新闻首页",
        "url": "https://news.sina.com.cn/",
    },
    {
        "name": "新浪国内新闻",
        "url": "https://news.sina.com.cn/china/",
    },
]
_SINA_NEWS_ARTICLE_RE = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*sina\.com\.cn/(?:(?:[a-z]/)?202\d-\d{2}-\d{2}/|article_/|roll/)[^\s\"'#]+",
    flags=re.IGNORECASE,
)
_SINA_NOISE_TITLES = {"更多", "详细", "专题", "新浪首页", "返回顶部"}


def _required_domain_for_query(query: str) -> str | None:
    normalized = (query or "").lower()
    if "x.com" in normalized or "twitter" in normalized or "site:x.com" in normalized:
        return "x.com"
    return None


def _output_contains_required_domain(output: str, domain: str) -> bool:
    required = domain.lower()
    for match in _URL_RE.findall(output or ""):
        if required in match.lower():
            return True
    return f"site:{required}" in (output or "").lower()


_OPEN_METEO_WEATHER_CODES = {
    0: "晴朗",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴天",
    45: "有雾",
    48: "冻雾",
    51: "小毛毛雨",
    53: "中毛毛雨",
    55: "大毛毛雨",
    56: "冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "中阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}

# ---------------------------------------------------------------------------
# Natural-language weather forecast fallback (Open-Meteo geocoding + forecast)
# ---------------------------------------------------------------------------

_WEATHER_QUERY_MARKERS = (
    "天气",
    "气温",
    "温度",
    "降水",
    "降雨",
    "下雨",
    "预报",
    "weather",
    "forecast",
    "temperature",
    "precipitation",
    "rain",
)
_WEATHER_EXCLUDE_MARKERS = (
    "编程",
    "程序",
    "algorithm",
    "code",
    "coding",
)
# Known multilingual city aliases → canonical English name (used by Open-Meteo geocoding).
# Keep conservative: only well-known cities where disambiguation is unambiguous.
_WEATHER_CITY_ALIASES: dict[str, str] = {
    "大阪": "Osaka",
    "大阪市": "Osaka",
    "osaka": "Osaka",
    "大坂": "Osaka",
    "东京": "Tokyo",
    "東京": "Tokyo",
    "tokyo": "Tokyo",
    "京都": "Kyoto",
    "京都市": "Kyoto",
    "kyoto": "Kyoto",
    "札幌": "Sapporo",
    "sapporo": "Sapporo",
    "名古屋": "Nagoya",
    "nagoya": "Nagoya",
    "福冈": "Fukuoka",
    "福岡": "Fukuoka",
    "fukuoka": "Fukuoka",
    "横滨": "Yokohama",
    "横浜": "Yokohama",
    "yokohama": "Yokohama",
    "神户": "Kobe",
    "神戸": "Kobe",
    "kobe": "Kobe",
    "北京": "Beijing",
    "beijing": "Beijing",
    "上海": "Shanghai",
    "shanghai": "Shanghai",
    "广州": "Guangzhou",
    "廣州": "Guangzhou",
    "guangzhou": "Guangzhou",
    "深圳": "Shenzhen",
    "shenzhen": "Shenzhen",
    "香港": "Hong Kong",
    "hong kong": "Hong Kong",
    "台北": "Taipei",
    "taipei": "Taipei",
    "首尔": "Seoul",
    "seoul": "Seoul",
    "新加坡": "Singapore",
    "singapore": "Singapore",
    "曼谷": "Bangkok",
    "bangkok": "Bangkok",
    "巴黎": "Paris",
    "paris": "Paris",
    "伦敦": "London",
    "london": "London",
    "纽约": "New York",
    "new york": "New York",
    "洛杉矶": "Los Angeles",
    "los angeles": "Los Angeles",
    "旧金山": "San Francisco",
    "san francisco": "San Francisco",
    "西雅图": "Seattle",
    "seattle": "Seattle",
    "柏林": "Berlin",
    "berlin": "Berlin",
}

_WEATHER_GEOCODE_ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search"
_WEATHER_FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"


def _looks_like_weather_query(query: str) -> bool:
    text = (query or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in _WEATHER_EXCLUDE_MARKERS):
        return False
    return any(marker in lowered for marker in _WEATHER_QUERY_MARKERS)


def _extract_weather_cities(query: str) -> list[str]:
    if not query:
        return []
    lowered = query.lower()
    found: list[str] = []
    seen: set[str] = set()
    for alias, canonical in _WEATHER_CITY_ALIASES.items():
        if canonical in seen:
            continue
        needle = alias if alias.isascii() else alias
        # For non-ASCII aliases, look in original string; for ASCII, look in lowered.
        source = lowered if alias.isascii() else query
        if needle in source:
            found.append(canonical)
            seen.add(canonical)
    return found


def _parse_forecast_days(query: str, default: int = 3, maximum: int = 7) -> int:
    if not query:
        return default
    text = query
    # Chinese: "未来三天" "未来7天" "3天内"
    zh_digits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}
    for ch, val in zh_digits.items():
        if f"未来{ch}天" in text or f"{ch}天内" in text:
            return min(max(val, 1), maximum)
    m = re.search(r"未来\s*(\d+)\s*天|(\d+)\s*天\s*内|next\s+(\d+)\s+day|(\d+)[\s-]*day", text, flags=re.IGNORECASE)
    if m:
        for grp in m.groups():
            if grp:
                try:
                    return min(max(int(grp), 1), maximum)
                except ValueError:
                    pass
    return default


def _geocode_city(city: str) -> dict[str, Any] | None:
    params = f"?name={urllib.parse.quote(city)}&count=1&language=en&format=json"
    url = _WEATHER_GEOCODE_ENDPOINT + params
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "OctoAgent/1.0"})
        with urllib.request.urlopen(request, timeout=8) as response:
            body = response.read().decode("utf-8", errors="ignore")
        payload = json.loads(body)
    except Exception:
        logger.exception("Open-Meteo geocoding failed for %s", city)
        return None
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or not results:
        return None
    top = results[0]
    return {
        "name": top.get("name") or city,
        "country": top.get("country") or "",
        "country_code": top.get("country_code") or "",
        "admin1": top.get("admin1") or "",
        "latitude": top.get("latitude"),
        "longitude": top.get("longitude"),
        "timezone": top.get("timezone") or "auto",
    }


def _fetch_daily_forecast(location: dict[str, Any], days: int) -> tuple[dict[str, Any] | None, str]:
    lat = location.get("latitude")
    lon = location.get("longitude")
    if lat is None or lon is None:
        return None, ""
    tz = location.get("timezone") or "auto"
    params = f"?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max&forecast_days={days}&timezone={urllib.parse.quote(tz)}"
    url = _WEATHER_FORECAST_ENDPOINT + params
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "OctoAgent/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            body = response.read().decode("utf-8", errors="ignore")
        payload = json.loads(body)
    except Exception:
        logger.exception("Open-Meteo forecast failed for %s", location.get("name"))
        return None, url
    if not isinstance(payload, dict):
        return None, url
    return payload, url


def _render_weather_city_block(location: dict[str, Any], forecast: dict[str, Any], url: str) -> str:
    daily = forecast.get("daily") or {}
    times = daily.get("time") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    codes = daily.get("weather_code") or []
    pops = daily.get("precipitation_probability_max") or []
    if not times:
        return ""

    header = f"### {location['name']}"
    if location.get("country"):
        header += f"（{location['country']}）"

    rows = [
        "| 日期 | 最高气温 | 最低气温 | 天气状况 | 最大降水概率 |",
        "| :-- | :-- | :-- | :-- | :-- |",
    ]
    for idx, day in enumerate(times):
        hi = tmax[idx] if idx < len(tmax) else None
        lo = tmin[idx] if idx < len(tmin) else None
        code = codes[idx] if idx < len(codes) else None
        pop = pops[idx] if idx < len(pops) else None
        weather_label = _OPEN_METEO_WEATHER_CODES.get(int(code), f"代码 {code}") if code is not None else "—"
        hi_txt = f"{hi}°C" if hi is not None else "—"
        lo_txt = f"{lo}°C" if lo is not None else "—"
        pop_txt = f"{pop}%" if pop is not None else "—"
        rows.append(f"| {day} | {hi_txt} | {lo_txt} | {weather_label} | {pop_txt} |")

    return "\n".join([header, "", *rows, "", f"数据来源：{url}"])


def _build_weather_forecast_fallback(query: str) -> str | None:
    if not _looks_like_weather_query(query):
        return None
    cities = _extract_weather_cities(query)
    if not cities:
        return None
    days = _parse_forecast_days(query)

    blocks: list[str] = []
    sources: list[str] = []
    failures: list[str] = []
    for city in cities:
        location = _geocode_city(city)
        if not location:
            failures.append(f"{city}（地理编码失败）")
            continue
        forecast, url = _fetch_daily_forecast(location, days)
        if not forecast:
            failures.append(f"{city}（预报 API 失败）")
            continue
        block = _render_weather_city_block(location, forecast, url)
        if block:
            blocks.append(block)
            sources.append(url)

    if not blocks:
        return None

    header_lines = [
        "以下结果通过服务端兜底（Open-Meteo 天气 API）收集，因为模型本轮未触发工具调用：",
        "",
        f"- 覆盖城市：{', '.join(cities)}",
        f"- 预报天数：未来 {days} 天",
    ]
    if failures:
        header_lines.append(f"- 未能获取：{', '.join(failures)}")
    header_lines.append("")

    trailer_lines = [
        "",
        "### 数据来源",
        "",
        "- Open-Meteo Geocoding API：https://geocoding-api.open-meteo.com/v1/search",
        "- Open-Meteo Forecast API：https://api.open-meteo.com/v1/forecast",
    ]
    for url in sources:
        trailer_lines.append(f"- {url}")

    return "\n".join(header_lines + blocks + trailer_lines)


def build_server_side_research_fallback(query: str) -> str:
    direct_fetch = _build_direct_url_fetch_fallback(query)
    if direct_fetch:
        return direct_fetch

    weather_fallback = _build_weather_forecast_fallback(query)
    if weather_fallback:
        return weather_fallback

    sina_news_fallback = _build_sina_top_news_fallback(query)
    if sina_news_fallback:
        return sina_news_fallback

    news_fallback = _build_ai_model_news_fallback(query)
    if news_fallback:
        return news_fallback

    try:
        from src.tools.builtins.web_tools import web_search_tool

        search_output = web_search_tool.invoke({"query": query, "max_results": 5})
        required_domain = _required_domain_for_query(query)
        if required_domain and not _output_contains_required_domain(search_output, required_domain):
            return f"Server-side research fallback failed because required domain evidence was not retrieved. Required domain: {required_domain}. Query: {query}. Search output: {search_output}"
        return f"Server-side research fallback collected public web results because the model produced no tool calls.\n\nCollected references:\n\n{search_output}"
    except Exception as exc:
        logger.exception("Server-side research fallback failed")
        return f"Tool fallback could not run due to server error. Please retry task execution. Details: {exc}"


async def build_server_side_research_fallback_async(query: str) -> str:
    return await asyncio.to_thread(build_server_side_research_fallback, query)


def _looks_like_ai_model_news_query(query: str) -> bool:
    normalized = (query or "").lower()
    mentions_news = any(marker in normalized for marker in _AI_NEWS_QUERY_MARKERS)
    mentions_ai_model = any(marker in normalized for marker in _AI_MODEL_QUERY_MARKERS)
    return mentions_news and mentions_ai_model


def _looks_like_sina_top_news_query(query: str) -> bool:
    normalized = (query or "").lower()
    mentions_sina = "新浪" in (query or "") or "sina" in normalized
    mentions_news = any(marker in normalized for marker in ("news", "headline", "headlines", "新闻", "资讯", "头条"))
    mentions_top = any(marker in normalized for marker in ("top 10", "top10", "top ten", "前十", "前10", "十大", "热榜", "热点"))
    return mentions_sina and mentions_news and mentions_top


def _extract_requested_result_count(query: str, default: int = 10) -> int:
    match = re.search(r"(\d+)", query or "")
    if not match:
        return default
    return max(3, min(int(match.group(1)), 10))


def _parse_feed_datetime(value: str) -> datetime | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    try:
        parsed = parsedate_to_datetime(cleaned)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except Exception:
        pass
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except Exception:
        return None


def _clean_feed_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", unescape(value))
    return re.sub(r"\s+", " ", text).strip()


def _extract_sina_news_entries(html: str, base_url: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen_links: set[str] = set()

    for match in re.finditer(
        r"<a[^>]+href=\"(?P<href>[^\"]+)\"[^>]*>(?P<title>[\s\S]*?)</a>",
        html,
        flags=re.IGNORECASE,
    ):
        href = urljoin(base_url, unescape(match.group("href")).strip())
        if href in seen_links or not _SINA_NEWS_ARTICLE_RE.match(href):
            continue
        title = _clean_feed_text(match.group("title"))
        if not title or title in _SINA_NOISE_TITLES or len(title) < 6 or len(title) > 80:
            continue
        seen_links.add(href)
        entries.append({"title": title, "link": href})

    return entries


def _build_sina_top_news_fallback(query: str) -> str | None:
    if not _looks_like_sina_top_news_query(query):
        return None

    requested = _extract_requested_result_count(query)
    collected: list[dict[str, str]] = []
    seen_links: set[str] = set()

    for source in _SINA_NEWS_SOURCE_URLS:
        try:
            response = requests.get(
                source["url"],
                headers={"User-Agent": "Mozilla/5.0 (OctoAgent/1.0)"},
                timeout=(_AI_NEWS_FETCH_CONNECT_TIMEOUT, _AI_NEWS_PAGE_READ_TIMEOUT),
            )
            response.raise_for_status()
            encoding = response.apparent_encoding or response.encoding or "utf-8"
            html = response.content.decode(encoding, errors="ignore")
        except Exception:
            logger.exception("Sina top news fallback source fetch failed", extra={"source": source["url"]})
            continue

        for entry in _extract_sina_news_entries(html, source["url"]):
            if entry["link"] in seen_links:
                continue
            seen_links.add(entry["link"])
            collected.append({**entry, "source": source["name"]})
            if len(collected) >= requested:
                break
        if len(collected) >= requested:
            break

    if not collected:
        return None

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "Server-side Sina news fallback collected headline candidates directly from Sina public pages because the LangGraph research run did not converge reliably.",
        f"Snapshot time: {timestamp}",
        "",
    ]
    for index, entry in enumerate(collected[:requested], start=1):
        lines.append(f"{index}. {entry['title']}")
        lines.append(str(entry["source"]))
        lines.append(entry["link"])
        lines.append("")
    return "\n".join(lines).strip()


def _entry_link_from_atom(entry: ET.Element) -> str:
    atom_ns = "{http://www.w3.org/2005/Atom}"
    for link in entry.findall(f"{atom_ns}link"):
        href = link.attrib.get("href", "").strip()
        rel = link.attrib.get("rel", "alternate")
        if href and rel in {"alternate", "self", ""}:
            return href
    return ""


def _entry_matches_ai_model_news(entry: dict[str, str]) -> bool:
    haystack = " ".join(
        filter(
            None,
            [entry.get("source", ""), entry.get("title", ""), entry.get("summary", ""), entry.get("link", "")],
        )
    ).lower()
    marker_hits = sum(1 for marker in _AI_MODEL_QUERY_MARKERS if marker in haystack)
    if any(marker in haystack for marker in _AI_NEWS_SOURCE_MARKERS):
        return marker_hits >= 1
    return marker_hits >= 2


def _entry_link_matches_source(entry: dict[str, str], source: dict[str, Any]) -> bool:
    markers = tuple(str(marker).lower() for marker in source.get("link_markers", ()))
    if not markers:
        return True
    link = entry.get("link", "").lower()
    return any(marker in link for marker in markers)


def _fetch_ai_news_rss_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    response = requests.get(
        source["url"],
        headers={"User-Agent": "Mozilla/5.0 (OctoAgent/1.0)"},
        timeout=(_AI_NEWS_FETCH_CONNECT_TIMEOUT, _AI_NEWS_RSS_READ_TIMEOUT),
    )
    response.raise_for_status()
    body = response.text

    root = ET.fromstring(body)
    entries: list[dict[str, Any]] = []

    for item in root.findall(".//item"):
        entry = {
            "source": source["name"],
            "title": _clean_feed_text(item.findtext("title")),
            "summary": _clean_feed_text(item.findtext("description")),
            "link": _clean_feed_text(item.findtext("link")),
            "published": _clean_feed_text(item.findtext("pubDate")),
        }
        entry["published_at"] = _parse_feed_datetime(entry["published"])
        if entry["title"] and entry["link"] and _entry_link_matches_source(entry, source) and _entry_matches_ai_model_news(entry):
            entries.append(entry)

    atom_ns = "{http://www.w3.org/2005/Atom}"
    for item in root.findall(f".//{atom_ns}entry"):
        entry = {
            "source": source["name"],
            "title": _clean_feed_text(item.findtext(f"{atom_ns}title")),
            "summary": _clean_feed_text(item.findtext(f"{atom_ns}summary") or item.findtext(f"{atom_ns}content")),
            "link": _clean_feed_text(_entry_link_from_atom(item)),
            "published": _clean_feed_text(item.findtext(f"{atom_ns}published") or item.findtext(f"{atom_ns}updated")),
        }
        entry["published_at"] = _parse_feed_datetime(entry["published"])
        if entry["title"] and entry["link"] and _entry_link_matches_source(entry, source) and _entry_matches_ai_model_news(entry):
            entries.append(entry)

    return entries


def _first_clean_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            cleaned = _clean_feed_text(match.group(1))
            if cleaned:
                return cleaned
    return ""


def _fetch_ai_news_page_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    response = requests.get(
        source["url"],
        headers={"User-Agent": "Mozilla/5.0 (OctoAgent/1.0)"},
        timeout=(_AI_NEWS_FETCH_CONNECT_TIMEOUT, _AI_NEWS_PAGE_READ_TIMEOUT),
    )
    response.raise_for_status()
    html = response.text

    title_patterns = [
        r"<h[1-6][^>]*>(.*?)</h[1-6]>",
        r"<span[^>]*class=\"[^\"]*title[^\"]*\"[^>]*>(.*?)</span>",
        r"<div[^>]*class=\"[^\"]*title[^\"]*\"[^>]*>(.*?)</div>",
    ]
    summary_patterns = [
        r"<p[^>]*>(.*?)</p>",
        r"<span[^>]*class=\"[^\"]*(?:body|summary|description)[^\"]*\"[^>]*>(.*?)</span>",
        r"<div[^>]*class=\"[^\"]*(?:body|summary|description)[^\"]*\"[^>]*>(.*?)</div>",
    ]
    published_patterns = [
        r"<time[^>]*datetime=\"([^\"]+)\"[^>]*>",
        r"<time[^>]*>(.*?)</time>",
    ]

    entries: list[dict[str, Any]] = []
    seen_links: set[str] = set()
    href_pattern = source["href_pattern"]
    for match in re.finditer(
        rf"<a[^>]+href=\"(?P<href>{href_pattern})\"[^>]*>(?P<body>[\s\S]*?)</a>",
        html,
        flags=re.IGNORECASE,
    ):
        href = urljoin(source["url"], unescape(match.group("href")))
        if href in seen_links:
            continue
        seen_links.add(href)

        body = match.group("body")
        title = _first_clean_match(body, title_patterns)
        summary = _first_clean_match(body, summary_patterns)
        published = _first_clean_match(body, published_patterns)
        entry = {
            "source": source["name"],
            "title": title,
            "summary": summary,
            "link": href,
            "published": published,
        }
        entry["published_at"] = _parse_feed_datetime(published)
        if title and _entry_matches_ai_model_news(entry):
            entries.append(entry)
    return entries


def _collect_ai_news_entries(
    sources: list[dict[str, Any]],
    fetcher,
    error_message: str,
) -> list[dict[str, Any]]:
    if not sources:
        return []

    entries: list[dict[str, Any]] = []
    max_workers = min(4, len(sources))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ai-news-fetch") as executor:
        future_to_source = {executor.submit(fetcher, source): source for source in sources}
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                entries.extend(future.result())
            except Exception:
                logger.exception(error_message, extra={"source": source["url"]})
    return entries


def _build_ai_model_news_fallback(query: str) -> str | None:
    if not _looks_like_ai_model_news_query(query):
        return None

    requested = _extract_requested_result_count(query)
    collected: list[dict[str, Any]] = []
    seen_links: set[str] = set()

    for entry in _collect_ai_news_entries(
        _AI_MODEL_NEWS_RSS_SOURCES,
        _fetch_ai_news_rss_source,
        "AI model news RSS source fetch failed",
    ):
        link = entry["link"]
        if link in seen_links:
            continue
        seen_links.add(link)
        collected.append(entry)

    for entry in _collect_ai_news_entries(
        _AI_MODEL_NEWS_PAGE_SOURCES,
        _fetch_ai_news_page_source,
        "AI model news page source fetch failed",
    ):
        link = entry["link"]
        if link in seen_links:
            continue
        seen_links.add(link)
        collected.append(entry)

    if not collected:
        return None

    collected.sort(
        key=lambda entry: (
            _AI_NEWS_SOURCE_PRIORITIES.get(str(entry.get("source", "")), 0),
            entry.get("published_at") or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )
    lines = [
        "Server-side AI model news fallback aggregated recent public updates from trusted feeds because direct public search results were unreliable in this runtime.",
        "",
    ]
    for index, entry in enumerate(collected[:requested], start=1):
        lines.append(f"{index}. {entry['title']}")
        meta_parts = [entry["source"]]
        if entry.get("published"):
            meta_parts.append(str(entry["published"]))
        lines.append(" | ".join(meta_parts))
        lines.append(entry["link"])
        if entry.get("summary"):
            lines.append(str(entry["summary"])[:360])
        lines.append("")
    return "\n".join(lines).strip()


def _extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for raw_url in _URL_RE.findall(text or ""):
        url = raw_url.rstrip(".,;:)]}>'\"，。；：、）】")
        if url and url not in urls:
            urls.append(url)
    return urls


def _format_open_meteo_fallback(url: str, payload: dict[str, Any]) -> str | None:
    current = payload.get("current")
    if not isinstance(current, dict):
        return None
    lines = ["根据 Open-Meteo API 的实时数据，当前天气如下：", ""]
    field_specs = [
        ("temperature_2m", "当前温度", "°C"),
        ("apparent_temperature", "体感温度", "°C"),
        ("relative_humidity_2m", "相对湿度", "%"),
        ("wind_speed_10m", "10 米风速", " km/h"),
    ]
    for field, label, suffix in field_specs:
        value = current.get(field)
        if value is None:
            continue
        lines.append(f"- **{label}**：{value}{suffix}")
    weather_code = current.get("weather_code")
    if weather_code is not None:
        meaning = _OPEN_METEO_WEATHER_CODES.get(int(weather_code), "未知天气")
        lines.append(f"- **天气状况代码**：{weather_code}（{meaning}）")
    if current.get("time"):
        lines.append(f"- **数据时间**：{current['time']}")
    lines.extend(["", f"数据来源：{url}"])
    return "\n".join(lines)


def _build_direct_url_fetch_fallback(prompt: str) -> str | None:
    for url in _extract_urls(prompt)[:3]:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (OctoAgent/1.0)"})
            with urllib.request.urlopen(request, timeout=20) as response:
                content_type = response.headers.get("Content-Type", "")
                body = response.read().decode("utf-8", errors="ignore")
        except Exception:
            continue

        body_text = body.strip()
        if not body_text:
            continue
        if "open-meteo.com" in url:
            try:
                payload = json.loads(body_text)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                formatted = _format_open_meteo_fallback(url, payload)
                if formatted:
                    return formatted
        if "json" in content_type or body_text.startswith(("{", "[")):
            try:
                payload = json.loads(body_text)
            except Exception:
                payload = None
            if payload is not None:
                pretty = json.dumps(payload, ensure_ascii=False, indent=2)
                return f"Direct URL fetch fallback succeeded.\n\nSource: {url}\n\n{pretty}"
        return f"Direct URL fetch fallback succeeded.\n\nSource: {url}\n\n{body_text[:4000]}"
    return None


# ─────────────────────────────────────────────────────────────────
# Fallback-routing helpers (moved from execution.py for decoupling)
# ─────────────────────────────────────────────────────────────────

_X_DOMAIN_MARKERS = ("x.com", "twitter", "site:x.com")
_SINA_DOMAIN_MARKERS = ("新浪", "sina", "news.sina.com.cn")
_NEWS_QUERY_MARKERS = ("news", "headline", "headlines", "新闻", "资讯", "头条")
_TOP_NEWS_QUERY_MARKERS = ("top 10", "top10", "top ten", "前十", "前10", "十大", "热点", "热榜")

_INTEGRATED_WORKFLOW_ALIASES: dict[str, str] = {
    "ian handdrawn": "ian-handdrawn-ppt",
    "handdrawn ppt": "ian-handdrawn-ppt",
    "hand drawn ppt": "ian-handdrawn-ppt",
    "helloianneo": "ian-handdrawn-ppt",
    "lumibot": "lumibot-research-strategy",
    "lumiwealth": "lumibot-research-strategy",
}


def _prefers_server_side_ai_news_fallback(query: str | None) -> bool:
    normalized = (query or "").strip().lower()
    return _looks_like_ai_model_news_query(normalized) and any(
        marker in normalized for marker in _X_DOMAIN_MARKERS
    )


def _prefers_server_side_news_fallback(query: str | None) -> bool:
    normalized = (query or "").strip().lower()
    if _prefers_server_side_ai_news_fallback(normalized):
        return True
    mentions_sina = any(marker in (query or "").lower() for marker in _SINA_DOMAIN_MARKERS)
    mentions_news = any(marker in normalized for marker in _NEWS_QUERY_MARKERS)
    mentions_top_news = any(marker in normalized for marker in _TOP_NEWS_QUERY_MARKERS)
    return mentions_sina and mentions_news and mentions_top_news


def server_side_fallback_target(query: str | None) -> str:
    """Return the preferred fallback target key for *query*."""
    if _prefers_server_side_ai_news_fallback(query):
        return "server_side_ai_news_fallback"
    if _prefers_server_side_news_fallback(query):
        return "server_side_news_fallback"
    return "server_side_research_fallback"


def resolve_integrated_workflow_id(query: str | None) -> str | None:
    """Detect whether *query* maps to a known integrated ecosystem workflow."""
    import logging as _log

    _logger = _log.getLogger(__name__)
    normalized = (query or "").strip().lower()
    raw = str(query or "").lower()
    if not normalized and not raw:
        return None
    try:
        from src.tools.builtins.ecosystem_workflow_tools import WORKFLOW_ALIASES
    except Exception:
        _logger.exception("Failed to load integrated ecosystem workflow aliases")
        return None
    haystacks = (normalized, raw)
    for workflow_id in sorted(WORKFLOW_ALIASES, key=len, reverse=True):
        candidate = workflow_id.lower()
        if any(candidate in haystack for haystack in haystacks):
            return workflow_id
    for marker, workflow_id in _INTEGRATED_WORKFLOW_ALIASES.items():
        if any(marker in haystack for haystack in haystacks):
            return workflow_id
    return None


def _json_tool_payload_rf(raw: str) -> dict:
    import json as _json

    try:
        payload = _json.loads(raw)
    except _json.JSONDecodeError:
        return {"raw": raw}
    return payload if isinstance(payload, dict) else {"raw": payload}


def build_integrated_workflow_tool_response(workflow_id: str, prompt: str) -> tuple[str, int]:
    """Execute integrated workflow tool calls and return (content, tool_call_count)."""
    import json as _json

    from src.tools.builtins.ecosystem_workflow_tools import (
        integrated_project_catalog_tool,
        integrated_workflow_run_tool,
    )
    from src.tools.capability_tools import get_plugin_command_tool, load_skill_tool

    catalog_raw = integrated_project_catalog_tool.invoke({"max_items": 100})
    workflow_raw = integrated_workflow_run_tool.invoke({"workflow_id": workflow_id, "prompt": prompt, "dry_run": True})
    catalog_payload = _json_tool_payload_rf(catalog_raw)
    workflow_payload = _json_tool_payload_rf(workflow_raw)
    project = workflow_payload.get("project") if isinstance(workflow_payload.get("project"), dict) else {}
    sequence = workflow_payload.get("tool_call_sequence") if isinstance(workflow_payload.get("tool_call_sequence"), list) else []
    command_id = None
    for step in sequence:
        if not isinstance(step, dict) or step.get("tool") != "get_plugin_command":
            continue
        args = step.get("args") if isinstance(step.get("args"), dict) else {}
        command_id = str(args.get("command_id") or "").strip() or None
        if command_id:
            break
    plugin_raw = get_plugin_command_tool.invoke({"command_id": command_id}) if command_id else ""
    skill_name = str(project.get("skill_name") or "").strip()
    skill_raw = load_skill_tool.invoke({"skill_name": skill_name}) if skill_name else ""

    tool_calls = [
        "integrated_project_catalog",
        "get_plugin_command" if command_id else "get_plugin_command(skipped)",
        "load_skill" if skill_name else "load_skill(skipped)",
        "integrated_workflow_run",
    ]
    catalog_count = catalog_payload.get("returned", 0)
    status = workflow_payload.get("status", "unknown")
    plugin_excerpt = plugin_raw[:500] if plugin_raw else "skipped"
    skill_excerpt = skill_raw[:500] if skill_raw else "skipped"
    workflow_excerpt = _json.dumps(workflow_payload, ensure_ascii=False, indent=2)[:2500]
    content = (
        "## Integrated Workflow Tool Execution\n\n"
        f"Status: `{status}`\n"
        f"workflow_id: `{workflow_id}`\n\n"
        f"1. `integrated_project_catalog` returned `{catalog_count}` installed ecosystem projects.\n"
        f"2. `get_plugin_command` ({command_id or 'skipped'}) excerpt:\n```\n{plugin_excerpt}\n```\n"
        f"3. `load_skill` ({skill_name or 'skipped'}) excerpt:\n```\n{skill_excerpt}\n```\n"
        f"4. `integrated_workflow_run` result:\n```json\n{workflow_excerpt}\n```\n"
    )
    return content, len([n for n in tool_calls if "skipped" not in n])
