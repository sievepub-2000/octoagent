"""Scrapling-based fetch tools (BSD-3-Clause).

HTTP-only Fetcher is used by default (no Playwright dependency).
StealthyFetcher is invoked only when explicitly requested AND when browser
dependencies are available (graceful degradation).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from langchain.tools import tool

from src.utils.proxy_env import should_trust_proxy_env
from src.utils.url_safety import is_url_safe

logger = logging.getLogger(__name__)

_FETCHER = None
_STEALTHY = None
_INIT_TRIED = False


def _get_proxy_from_env() -> str | None:
    if os.environ.get("OCTOAGENT_WEB_SCRAPING_DISABLED"):
        raise RuntimeError("Web scraping tools are disabled (OCTOAGENT_WEB_SCRAPING_DISABLED=1). Set the env var to 0 or configure HTTPS_PROXY to re-enable.")
    if not should_trust_proxy_env():
        return None
    # curl_cffi HTTP Fetcher honours proxy env vars automatically, but the
    # Playwright-based StealthyFetcher does not -- so resolve the proxy here and
    # pass it explicitly to keep both fetchers routed through the proxy.
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return None


def _lazy_init() -> None:
    global _FETCHER, _STEALTHY, _INIT_TRIED
    if _INIT_TRIED:
        return
    _INIT_TRIED = True
    try:
        from scrapling.fetchers import Fetcher  # type: ignore

        _FETCHER = Fetcher
    except Exception as e:
        logger.warning("scrapling Fetcher not available: %s", e)
    try:
        from scrapling.fetchers import StealthyFetcher  # type: ignore

        _STEALTHY = StealthyFetcher
    except Exception as e:
        logger.info("scrapling StealthyFetcher not available (browser deps missing): %s", e)


def _allow_insecure_ssl_retry() -> bool:
    return os.environ.get("OCTO_SCRAPLING_ALLOW_INSECURE_SSL_RETRY", "0").strip().lower() in {"1", "true", "yes", "on"}


def _is_certificate_verify_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "certificateverifyerror" in type(exc).__name__.lower() or "curl: (60)" in text or "ssl certificate problem" in text or "unable to get local issuer certificate" in text


def _fmt_result(url: str, page: Any, *, mode: str, tls_verification: str = "verified") -> str:
    title = None
    try:
        sel = page.css("title::text") if hasattr(page, "css") else None
        if sel is not None:
            title = sel.get() if hasattr(sel, "get") else (sel[0] if sel else None)
    except Exception:
        title = None
    try:
        if hasattr(page, "get_all_text"):
            text = page.get_all_text(strip=True)
        elif hasattr(page, "text"):
            text = page.text  # type: ignore[attr-defined]
        else:
            text = str(page)[:8000]
    except Exception:
        text = str(page)[:8000]
    if isinstance(text, str) and len(text) > 8000:
        text = text[:8000] + "\n...[truncated]"
    return json.dumps(
        {
            "url": url,
            "title": title,
            "mode": mode,
            "engine": "scrapling",
            "tls_verification": tls_verification,
            "content": text,
        },
        ensure_ascii=False,
    )


@tool
def scrapling_fetch(url: str) -> str:
    """Fetch a single URL using Scrapling's HTTP Fetcher (TLS impersonation, no browser).

    Use for JS-light pages or when DDG/Tavily/web_fetch hit blocked-page
    patterns. Rejects private/internal URLs and returns JSON
    {url, title, content, engine, mode}.
    """
    if not is_url_safe(url):
        return json.dumps({"error": "Access to private/internal network addresses is not allowed.", "url": url, "engine": "scrapling"})
    _lazy_init()
    if _FETCHER is None:
        return json.dumps({"error": "scrapling not installed", "url": url})
    try:
        fetch_kwargs = dict(stealthy_headers=True, timeout=15)
        proxy = _get_proxy_from_env()
        if proxy:
            fetch_kwargs["proxy"] = proxy
        page = _FETCHER.get(url, **fetch_kwargs)
        return _fmt_result(url, page, mode="http")
    except Exception as e:
        if _allow_insecure_ssl_retry() and _is_certificate_verify_error(e):
            logger.warning("scrapling_fetch TLS verification failed for %s; retrying without verification: %s", url, e)
            try:
                retry_kwargs = dict(fetch_kwargs, timeout=30, verify=False)
                page = _FETCHER.get(url, **retry_kwargs)
                return _fmt_result(url, page, mode="http", tls_verification="disabled_after_certificate_error")
            except Exception as retry_e:
                logger.warning("scrapling_fetch insecure TLS retry failed for %s: %s", url, retry_e)
                return json.dumps({"error": str(retry_e), "url": url, "engine": "scrapling", "tls_verification": "retry_failed"})
        logger.warning("scrapling_fetch failed for %s: %s", url, e)
        return json.dumps({"error": str(e), "url": url, "engine": "scrapling"})


@tool
def scrapling_fetch_stealth(url: str) -> str:
    """Fetch a URL using Scrapling StealthyFetcher (Cloudflare/Turnstile bypass).

    Requires browser deps; rejects private/internal URLs and gracefully degrades
    to HTTP fetcher if unavailable. Uses direct connections (no proxy configured).
    """
    if not is_url_safe(url):
        return json.dumps({"error": "Access to private/internal network addresses is not allowed.", "url": url, "engine": "scrapling"})
    _lazy_init()
    if _STEALTHY is None:
        logger.info("StealthyFetcher unavailable, falling back to HTTP fetcher")
        return scrapling_fetch.invoke({"url": url})
    try:
        kwargs: dict[str, Any] = {
            "headless": True,
            "network_idle": True,
            "timeout": 60000,
        }
        proxy = _get_proxy_from_env()
        if proxy:
            kwargs["proxy"] = proxy
        page = _STEALTHY.fetch(url, **kwargs)
        return _fmt_result(url, page, mode="stealth")
    except Exception as e:
        logger.warning("scrapling stealth failed for %s: %s; falling back", url, e)
        return scrapling_fetch.invoke({"url": url})


__all__ = ["scrapling_fetch", "scrapling_fetch_stealth"]
