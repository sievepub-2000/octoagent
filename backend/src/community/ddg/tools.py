"""DuckDuckGo + httpx based web tools — zero API key required.

Provides:
  - ``web_search_tool``: queries DuckDuckGo via the ``ddgs`` package.
  - ``web_fetch_tool``: safe layered fetch via env-configured proxy, with
    readability extraction, same-URL Scrapling retry for anti-bot pages, and RSS
    variants for sites known to expose public feeds.

Why this exists: Tavily/Jina API keys are not provisioned, and Jina reader is
not reachable from this host. DDG + httpx work today without credentials.
"""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
from functools import lru_cache
from urllib.parse import urlparse

import httpx
from langchain.tools import tool

from src.runtime.config import get_app_config
from src.utils.proxy_env import should_trust_proxy_env, without_unavailable_local_proxy
from src.utils.readability import ReadabilityExtractor
from src.utils.url_safety import is_url_safe

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0
_DEFAULT_CONNECT = 15.0
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
_readability = ReadabilityExtractor()

_SCRAPLING_MIN_CONTENT_CHARS = 160
_BLOCKED_STATUS_CODES = {401, 403, 407, 408, 409, 418, 423, 425, 429, 451, 503}
_ANTI_BOT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\baccess denied\b",
        r"\baccess to this page has been denied\b",
        r"\bakamai\b",
        r"\battention required\b.*\bcloudflare\b",
        r"\bbot detection\b",
        r"\bcaptcha\b",
        r"\bchecking your browser\b",
        r"\bcloudflare\b",
        r"\bddos-guard\b",
        r"\benable javascript and cookies\b",
        r"\bforbidden\b",
        r"\bhuman verification\b",
        r"\bincapsula\b",
        r"\bjust a moment\b",
        r"\bperimeterx\b",
        r"\bplease verify you are a human\b",
        r"\brobot check\b",
        r"\btemporarily blocked\b",
        r"\bverify you are human\b",
        r"javascript.*(?:disabled|enable|無効)",
        r"(?:cookies|cookie).*enable",
    )
)


# Sites that reliably 403 HTML scrapers but expose RSS / public APIs.
_RSS_REWRITES = {
    "www.bloomberg.com": "https://feeds.bloomberg.com/markets/news.rss",
    "bloomberg.com": "https://feeds.bloomberg.com/markets/news.rss",
    "www.reuters.com": "https://www.reutersagency.com/feed/",
    "reuters.com": "https://www.reutersagency.com/feed/",
}


@lru_cache(maxsize=1)
def _ssl_verify_context() -> ssl.SSLContext | bool:
    if os.environ.get("OCTO_WEB_FETCH_SSL_VERIFY", "1").strip().lower() in {"0", "false", "no", "off"}:
        return False
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        try:
            import certifi

            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            return True


def _allow_insecure_ssl_retry() -> bool:
    return os.environ.get("OCTO_WEB_FETCH_ALLOW_INSECURE_SSL_RETRY", "0").strip().lower() in {"1", "true", "yes", "on"}


def _is_certificate_verify_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "certificate_verify_failed" in text or "certificate verify failed" in text or "unable to get local issuer certificate" in text


def _client(timeout: float = _DEFAULT_TIMEOUT, *, verify: ssl.SSLContext | bool | None = None) -> httpx.Client:
    """httpx client that honours usable HTTP_PROXY/HTTPS_PROXY env vars."""
    return httpx.Client(
        trust_env=should_trust_proxy_env(),
        timeout=httpx.Timeout(timeout, connect=_DEFAULT_CONNECT),
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        follow_redirects=True,
        verify=_ssl_verify_context() if verify is None else verify,
    )


# ──────────────────────────── web_search ────────────────────────────


@tool("web_search", parse_docstring=True)
def web_search_tool(query: str) -> str:
    """Search the web via DuckDuckGo. Returns a JSON list of {title,url,snippet}.

    No API key required. Honours HTTPS_PROXY in the environment.

    Args:
        query: The query to search for.
    """
    cfg = get_app_config().get_tool_config("web_search")
    max_results = 8
    if cfg is not None and "max_results" in cfg.model_extra:
        max_results = int(cfg.model_extra.get("max_results") or max_results)

    try:
        from ddgs import DDGS
    except ImportError:
        return json.dumps([{"error": "ddgs package not installed"}])

    def _ddg_search():
        with without_unavailable_local_proxy():
            with DDGS(timeout=25) as ddg:
                return list(ddg.text(query, region="us-en", max_results=max_results))

    try:
        raw = _ddg_search()
    except Exception as exc:
        logger.warning("ddgs search failed: %s", exc)
        return json.dumps([{"error": f"web_search failed: {type(exc).__name__}: {exc}"}])

    normalised = [
        {
            "title": (r.get("title") or "").strip(),
            "url": r.get("href") or r.get("url") or "",
            "snippet": (r.get("body") or "").strip(),
        }
        for r in raw
    ]
    return json.dumps(normalised, ensure_ascii=False, indent=2)


# ──────────────────────────── web_fetch ─────────────────────────────


def _maybe_rewrite_to_rss(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    if host in _RSS_REWRITES:
        return _RSS_REWRITES[host]
    return None


def _fetch_raw(url: str, timeout: float) -> tuple[int, str, str]:
    """Return (status_code, content_type, body). Body truncated to 1MB."""
    with _client(timeout=timeout) as c:
        r = c.get(url)
        body = r.text
        if len(body) > 1_000_000:
            body = body[:1_000_000]
        return r.status_code, (r.headers.get("Content-Type") or ""), body


def _fetch_raw_without_verification(url: str, timeout: float) -> tuple[int, str, str]:
    """Retry for public pages with broken certificate chains; caller adds warning."""
    with _client(timeout=timeout, verify=False) as c:
        r = c.get(url)
        body = r.text
        if len(body) > 1_000_000:
            body = body[:1_000_000]
        return r.status_code, (r.headers.get("Content-Type") or ""), body


def _scrapling_fallback_markdown(url: str, *, reason: str, stealth: bool = False) -> str | None:
    """Return cleaner Scrapling text for pages where httpx/readability is noisy."""
    try:
        from src.community.scrapling.tools import scrapling_fetch, scrapling_fetch_stealth

        fetcher = scrapling_fetch_stealth if stealth else scrapling_fetch
        raw = fetcher.invoke({"url": url})
        payload = json.loads(raw)
    except Exception as exc:
        logger.info("web_fetch scrapling fallback unavailable for %s: %s", url, exc)
        return None
    if not isinstance(payload, dict) or payload.get("error"):
        logger.info("web_fetch scrapling fallback returned error for %s: %s", url, payload.get("error"))
        return None
    content = str(payload.get("content") or "").strip()
    if len(content) < _SCRAPLING_MIN_CONTENT_CHARS:
        return None
    title = str(payload.get("title") or url).strip()
    mode = str(payload.get("mode") or "http")
    tls = str(payload.get("tls_verification") or "verified")
    return f"# {title}\n\nSource: {url}\nEngine: scrapling ({mode}, tls={tls})\nFallback reason: {reason}\n\n{content[:6000]}"


def _anti_bot_reason(status: int, content: str) -> str | None:
    if status in _BLOCKED_STATUS_CODES:
        return f"HTTP status {status} is commonly returned by blocked or anti-bot pages"
    normalized = re.sub(r"\s+", " ", content or "")[:80_000]
    if not normalized:
        return None
    hits = [pattern.pattern for pattern in _ANTI_BOT_PATTERNS if pattern.search(normalized)]
    if len(hits) >= 1:
        return "page content looks like an anti-bot, login, captcha, or JavaScript challenge"
    return None


def _should_prefer_scrapling(url: str, content: str, *, status: int = 200) -> str | None:
    anti_bot = _anti_bot_reason(status, content)
    if anti_bot:
        return anti_bot
    host = urlparse(url).netloc.lower()
    lowered = content.lower()
    if host.endswith("yahoo.co.jp") and ("javascript" in lowered or "topics" in lowered or "トピックス" in content):
        return "Yahoo pages expose cleaner topic text through Scrapling than through readability/httpx"
    if "javascript" in lowered and ("enable" in lowered or "無効" in content):
        return "extracted page is dominated by JavaScript-disabled boilerplate"
    return None


def _scrapling_stealth_enabled_for_blocked_pages() -> bool:
    return os.environ.get("OCTO_WEB_FETCH_SCRAPLING_STEALTH_ON_BLOCK", "0").strip().lower() in {"1", "true", "yes", "on"}


@tool("web_fetch", parse_docstring=True)
def web_fetch_tool(url: str) -> str:
    """Fetch a web page and return readable markdown.

    Uses a safe layered reader: httpx/readability first, Scrapling on the same
    URL when anti-bot/login/JavaScript challenge text or blocked HTTP statuses
    are detected, and RSS feeds for known public feed fallbacks.

    Args:
        url: The URL to fetch the contents of.
    """
    if not is_url_safe(url):
        return "Error: Access to private/internal network addresses is not allowed."

    cfg = get_app_config().get_tool_config("web_fetch")
    timeout = _DEFAULT_TIMEOUT
    if cfg is not None and "timeout" in cfg.model_extra:
        try:
            timeout = float(cfg.model_extra.get("timeout") or timeout)
        except (TypeError, ValueError):
            pass

    tls_warning = ""
    fetch_error = ""
    try:
        status, ctype, body = _fetch_raw(url, timeout=timeout)
    except Exception as exc:
        if _allow_insecure_ssl_retry() and _is_certificate_verify_error(exc):
            logger.warning("web_fetch TLS verification failed for %s; retrying without verification: %s", url, exc)
            try:
                status, ctype, body = _fetch_raw_without_verification(url, timeout=timeout)
                tls_warning = "[Warning: TLS certificate verification failed for this public URL; retried with certificate verification disabled. Verify the source URL before relying on the content.]\n\n"
            except Exception as retry_exc:
                logger.warning("web_fetch insecure TLS retry failed for %s: %s", url, retry_exc)
                fetch_error = f"{type(retry_exc).__name__}: {retry_exc}"
                status, ctype, body = 0, "", ""
        else:
            logger.warning("web_fetch initial GET failed for %s: %s", url, exc)
            fetch_error = f"{type(exc).__name__}: {exc}"
            status, ctype, body = 0, "", ""

    blocked_reason = _anti_bot_reason(status, body)
    if blocked_reason:
        logger.info("web_fetch: %s status=%s, retrying same URL with scrapling: %s", url, status, blocked_reason)
        scrapling_md = _scrapling_fallback_markdown(
            url,
            reason=blocked_reason,
            stealth=_scrapling_stealth_enabled_for_blocked_pages(),
        )
        if scrapling_md:
            return f"{tls_warning}{scrapling_md[:6000]}"

    # If blocked or empty, try RSS fallback for known-bad hosts.
    if status in (0, 403, 401, 451, 503) or not body:
        rss = _maybe_rewrite_to_rss(url)
        if rss:
            logger.info("web_fetch: %s status=%s, retrying RSS %s", url, status, rss)
            try:
                status2, ctype2, body2 = _fetch_raw(rss, timeout=timeout)
                if status2 == 200 and body2:
                    return f"# RSS feed for {urlparse(url).netloc}\n\nSource: {rss}\n\n{body2[:6000]}"
            except Exception as exc:
                logger.warning("web_fetch RSS fallback failed: %s", exc)

    if not body:
        detail = f", error={fetch_error}" if fetch_error else ""
        return f"Web fetch failed for {url}: status={status}{detail}. Consider trying a different source URL or web_search for alternatives."

    # XML/RSS content: return raw (truncated) — readability does not help.
    if "xml" in ctype or url.endswith((".rss", ".xml", ".atom")):
        return f"{tls_warning}# Feed: {url}\n\n{body[:6000]}"

    try:
        article = _readability.extract_article(body)
        md = article.to_markdown()
        if md and md.strip():
            reason = _should_prefer_scrapling(url, md, status=status)
            if reason:
                scrapling_md = _scrapling_fallback_markdown(url, reason=reason)
                if scrapling_md:
                    return f"{tls_warning}{scrapling_md[:6000]}"
            return f"{tls_warning}{md[:4096]}"
    except Exception as exc:
        logger.warning("readability failed for %s: %s", url, exc)

    # Last resort: truncated raw HTML.
    scrapling_md = _scrapling_fallback_markdown(url, reason="readability failed or returned no markdown")
    if scrapling_md:
        return f"{tls_warning}{scrapling_md[:6000]}"
    return f"{tls_warning}# Raw HTML for {url}\n\n{body[:4096]}"
