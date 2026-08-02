"""Single lightweight URL reader; dynamic interaction belongs to Browser."""

from __future__ import annotations

import json
import logging
import re
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urlparse

import httpx
from langchain.tools import tool
from markdownify import markdownify

from src.runtime.config import get_app_config
from src.utils.proxy_env import should_trust_proxy_env
from src.utils.readability import ReadabilityExtractor
from src.utils.url_safety import is_url_safe, safe_join_url

logger = logging.getLogger(__name__)

_MAX_BODY_CHARS = 1_000_000
_MAX_OUTPUT_CHARS = 24_000
_BLOCKED_STATUS_CODES = {401, 403, 407, 408, 409, 418, 423, 425, 429, 451, 503}
_ANTI_BOT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"access denied",
        r"attention required.*cloudflare",
        r"captcha",
        r"checking your browser",
        r"enable javascript and cookies",
        r"human verification",
        r"just a moment",
        r"verify you are human",
    )
)
_RSS_REWRITES = {
    "bloomberg.com": "https://feeds.bloomberg.com/markets/news.rss",
    "www.bloomberg.com": "https://feeds.bloomberg.com/markets/news.rss",
    "reuters.com": "https://www.reutersagency.com/feed/",
    "www.reuters.com": "https://www.reutersagency.com/feed/",
}
_GITHUB_NOISE = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"Sponsor open source projects you depend on",
        r"Contributors are working behind the scenes",
        r"Explore sponsorable projects",
        r"ProTip!\s*Press the / key",
        r"resolvedServerColorMode",
        r"You can.?t perform that action at this time",
        r"Sign in to GitHub",
        r"Skip to content",
        r"Navigation Menu",
        r"Search or jump to",
    )
)


def _timeout() -> float:
    config = get_app_config().get_tool_config("web_read")
    try:
        return float(config.model_extra.get("timeout", 30)) if config and config.model_extra else 30.0
    except (TypeError, ValueError):
        return 30.0


def _fetch(url: str, *, timeout: float) -> tuple[int, str, str, str]:
    """Return status, content type, body, and final URL after safe redirects."""
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    current_url = url
    with httpx.Client(
        timeout=httpx.Timeout(timeout, connect=min(timeout, 15.0)),
        follow_redirects=False,
        trust_env=should_trust_proxy_env(),
        headers=headers,
    ) as client:
        for _ in range(8):
            response = client.get(current_url)
            if response.is_redirect:
                next_url = safe_join_url(current_url, response.headers.get("Location", ""))
                if next_url is None:
                    raise ValueError("redirect target is private, internal, or invalid")
                current_url = next_url
                continue
            body = response.text[:_MAX_BODY_CHARS]
            return response.status_code, response.headers.get("Content-Type", ""), body, current_url
    raise ValueError("too many redirects")


def _browser_required(url: str, reason: str) -> str:
    return json.dumps(
        {"status": "browser_required", "url": url, "reason": reason, "next_tool": "browser"},
        ensure_ascii=False,
    )


def _is_github_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host == "github.com" or host.endswith(".github.com")


def _clean_extracted_text(url: str, text: str) -> str:
    if not text:
        return text
    if _is_github_url(url):
        text = "\n".join(line for line in text.splitlines() if not any(pattern.search(line) for pattern in _GITHUB_NOISE))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _cap_extracted_content(text: str) -> str:
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    return text[:_MAX_OUTPUT_CHARS].rstrip() + "\n\n... (content shortened; use a narrower URL or query)"


def _quality_failure_reason(url: str, text: str, *, original_html: str = "") -> str | None:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) < 160:
        return "extracted content is too short"
    combined = f"{text}\n{original_html[:20_000]}"
    if sum(1 for pattern in _ANTI_BOT_PATTERNS if pattern.search(combined)) >= 1:
        return "page contains a login, anti-bot, or JavaScript challenge"
    if _is_github_url(url) and sum(1 for pattern in _GITHUB_NOISE if pattern.search(combined)) >= 2:
        return "GitHub page is dominated by navigation or login chrome"
    return None


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = ""

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self.links.append({"text": self._text.strip(), "href": self._href})
            self._href = None
            self._text = ""


@tool("web_read", parse_docstring=True)
def web_read_tool(url: str, extract_mode: Literal["article", "markdown", "raw", "links"] = "article") -> str:
    """Read a public URL without a browser and return compact model-ready content.

    Use this for articles, documentation, feeds, and static pages. When the
    result status is ``browser_required``, call the separate Browser capability.

    Args:
        url: Public HTTP or HTTPS URL to read.
        extract_mode: Output mode: article, markdown, raw, or links.
    """
    if not is_url_safe(url):
        return json.dumps({"status": "error", "url": url, "reason": "private, internal, unresolved, or invalid URL"})

    try:
        status, content_type, body, final_url = _fetch(url, timeout=_timeout())
    except Exception as exc:
        return json.dumps({"status": "error", "url": url, "reason": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)

    rss_url = _RSS_REWRITES.get((urlparse(final_url).hostname or "").lower())
    if (status in _BLOCKED_STATUS_CODES or not body) and rss_url:
        try:
            rss_status, rss_type, rss_body, rss_final_url = _fetch(rss_url, timeout=_timeout())
            if rss_status == 200 and rss_body:
                status, content_type, body, final_url = rss_status, rss_type, rss_body, rss_final_url
        except Exception as exc:
            logger.info("RSS fallback failed for %s: %s", final_url, exc)

    if status in _BLOCKED_STATUS_CODES:
        return _browser_required(final_url, f"HTTP {status} indicates a blocked or interactive page")
    if status >= 400:
        return json.dumps({"status": "error", "url": final_url, "reason": f"HTTP {status}"})
    if any(pattern.search(body[:80_000]) for pattern in _ANTI_BOT_PATTERNS):
        return _browser_required(final_url, "page contains an anti-bot, login, captcha, or JavaScript challenge")

    if extract_mode == "raw":
        return body[:50_000]
    if extract_mode == "links":
        parser = _LinkParser()
        parser.feed(body)
        return json.dumps(parser.links[:500], ensure_ascii=False, indent=2)
    if "xml" in content_type.lower() or final_url.endswith((".rss", ".xml", ".atom")):
        return _cap_extracted_content(f"# Feed\n\nSource: {final_url}\n\n{body}")

    if extract_mode == "markdown":
        result = markdownify(body, heading_style="ATX", strip=["script", "style"])
    else:
        result = ReadabilityExtractor().extract_article(body).to_markdown()
    result = _cap_extracted_content(_clean_extracted_text(final_url, f"Source: {final_url}\n\n{result}"))
    failure = _quality_failure_reason(final_url, result, original_html=body)
    return _browser_required(final_url, failure) if failure else result


__all__ = ["web_read_tool"]
