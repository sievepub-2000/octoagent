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

from src.utils.proxy_env import without_unavailable_local_proxy

logger = logging.getLogger(__name__)

_FETCHER = None
_STEALTHY = None
_INIT_TRIED = False


def _lazy_init() -> None:
    global _FETCHER, _STEALTHY, _INIT_TRIED
    if _INIT_TRIED:
        return
    _INIT_TRIED = True
    try:
        from scrapling.fetchers import Fetcher  # type: ignore

        _FETCHER = Fetcher
    except Exception as e:  # pragma: no cover - import-time gate
        logger.warning("scrapling Fetcher not available: %s", e)
    try:
        from scrapling.fetchers import StealthyFetcher  # type: ignore

        _STEALTHY = StealthyFetcher
    except Exception as e:  # pragma: no cover
        logger.info("scrapling StealthyFetcher not available (browser deps missing): %s", e)


def _allow_insecure_ssl_retry() -> bool:
    return os.environ.get("OCTO_SCRAPLING_ALLOW_INSECURE_SSL_RETRY", "1").strip().lower() in {"1", "true", "yes", "on"}


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

    Use for JS-light pages or when DDG/Tavily failed. Returns JSON
    {url, title, content, engine, mode}.
    """
    _lazy_init()
    if _FETCHER is None:
        return json.dumps({"error": "scrapling not installed", "url": url})
    try:
        page = _FETCHER.get(url, stealthy_headers=True, timeout=30)
        return _fmt_result(url, page, mode="http")
    except Exception as e:
        if _allow_insecure_ssl_retry() and _is_certificate_verify_error(e):
            logger.warning("scrapling_fetch TLS verification failed for %s; retrying without verification: %s", url, e)
            try:
                page = _FETCHER.get(url, stealthy_headers=True, timeout=30, verify=False)
                return _fmt_result(url, page, mode="http", tls_verification="disabled_after_certificate_error")
            except Exception as retry_e:
                logger.warning("scrapling_fetch insecure TLS retry failed for %s: %s", url, retry_e)
                return json.dumps({"error": str(retry_e), "url": url, "engine": "scrapling", "tls_verification": "retry_failed"})
        logger.warning("scrapling_fetch failed for %s: %s", url, e)
        return json.dumps({"error": str(e), "url": url, "engine": "scrapling"})


@tool
def scrapling_fetch_stealth(url: str) -> str:
    """Fetch a URL using Scrapling StealthyFetcher (Cloudflare/Turnstile bypass).

    Requires browser deps; gracefully degrades to HTTP fetcher if unavailable.
    """
    _lazy_init()
    if _STEALTHY is None:
        logger.info("StealthyFetcher unavailable, falling back to HTTP fetcher")
        return scrapling_fetch.invoke({"url": url})
    try:
        page = _STEALTHY.fetch(url, headless=True, network_idle=True, timeout=60)
        return _fmt_result(url, page, mode="stealth")
    except Exception as e:
        logger.warning("scrapling stealth failed for %s: %s; falling back", url, e)
        return scrapling_fetch.invoke({"url": url})


__all__ = ["scrapling_fetch", "scrapling_fetch_stealth"]
