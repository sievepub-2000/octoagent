"""Tavily-backed web_search / web_fetch tools with layered fallback.

Search chain:   tavily → DDG
Fetch chain:    tavily → DDG → scrapling

``api_key`` is sourced from the environment first, with config.yaml
``tool_config.api_key`` as a fallback so the secret never has to live in
the repo.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from langchain.tools import tool

from src.runtime.config import get_app_config
from src.utils.lazy_import import lazy_tavily

logger = logging.getLogger(__name__)


def _resolve_api_key() -> str | None:
    env_key = os.getenv("TAVILY_API_KEY", "").strip()
    if env_key and not env_key.startswith("your-"):
        return env_key
    cfg = get_app_config().get_tool_config("web_search")
    if cfg is not None and cfg.model_extra and "api_key" in cfg.model_extra:
        return cfg.model_extra.get("api_key")
    return None


def _client() -> Any:
    key = _resolve_api_key()
    if not key:
        raise RuntimeError("TAVILY_API_KEY not set (env or tool_config.api_key)")
    return lazy_tavily.TavilyClient(api_key=key)


def _max_results(default: int = 5) -> int:
    cfg = get_app_config().get_tool_config("web_search")
    if cfg is not None and cfg.model_extra and "max_results" in cfg.model_extra:
        try:
            return int(cfg.model_extra["max_results"])
        except (TypeError, ValueError):
            pass
    return default


async def _fetch_chain(url: str, *, started_at: str = "tavily") -> str:
    """Execute the tavily → ddg → scrapling fetch fallback chain.

    Each tier is tried in order; transient exceptions or empty results
    promote to the next tier. The first non-empty result wins.
    """
    order = ["tavily", "ddg", "scrapling"]
    if started_at not in order:
        started_at = "tavily"
    last_err: Exception | None = None
    for tier in order[order.index(started_at) :]:
        try:
            if tier == "tavily":
                # Run synchronous TavilyClient.extract in a thread
                res = await asyncio.to_thread(_client().extract, [url])
                if res.get("failed_results"):
                    raise RuntimeError("tavily failed_results")
                results = res.get("results") or []
                if not results:
                    raise RuntimeError("tavily empty")
                r = results[0]
                return f"# {r.get('title', '')}\n\n{(r.get('raw_content', '') or '')[:4096]}"
            elif tier == "ddg":
                from src.community.ddg.tools import web_fetch_tool as ddg_fetch

                out = await asyncio.to_thread(ddg_fetch.invoke, {"url": url})
                if out and "Error" not in (out[:64] if isinstance(out, str) else ""):
                    return out
                raise RuntimeError("ddg empty/error")
            elif tier == "scrapling":
                from src.community.scrapling.tools import scrapling_fetch

                out = await asyncio.to_thread(scrapling_fetch.invoke, {"url": url})
                if out and '"error"' not in (out[:80] if isinstance(out, str) else ""):
                    return out
                raise RuntimeError("scrapling empty/error")

                if out and '"error"' not in (out[:120] if isinstance(out, str) else ""):
                    return out
        except Exception as exc:
            logger.info("fetch tier %s failed for %s: %s", tier, url, exc)
            last_err = exc
            continue
    return f"Error: all fetch tiers failed for {url}: {last_err}"


@tool("web_search", parse_docstring=True)
def web_search_tool(query: str) -> str:
    """Search the web with Tavily (falls back to DDG on failure).

    Args:
        query: The query to search for.
    """
    # Tavily rejects queries longer than 400 chars with a hard BadRequestError;
    # truncate for the API call while keeping the full query for the DDG fallback.
    tavily_query = query[:400] if isinstance(query, str) else query
    try:
        res = _client().search(tavily_query, max_results=_max_results())
    except Exception as exc:
        logger.warning("tavily.search failed: %s; falling back to DDG", exc)
        from src.community.ddg.tools import web_search_tool as ddg_search

        try:
            return ddg_search.invoke({"query": query})
        except Exception as ddg_exc:
            logger.warning("DDG web_search fallback also failed: %s", ddg_exc)
            return json.dumps(
                [{"error": f"web_search failed (tavily+ddg): {type(ddg_exc).__name__}: {ddg_exc}"}],
                ensure_ascii=False,
            )
    out: list[dict[str, Any]] = []
    for r in res.get("results", []):
        out.append({"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")})
    return json.dumps(out, indent=2, ensure_ascii=False)


@tool("web_fetch", parse_docstring=True)
async def web_fetch_tool(url: str) -> str:
    """Fetch the contents of a web page at a given URL.

    Uses a 3-tier fallback: tavily → DDG → scrapling. The first
    non-empty success wins. URLs must include the schema (https://...).

    Args:
        url: The URL to fetch the contents of.
    """
    return await _fetch_chain(url, started_at="tavily")


@tool("web_fetch_heavy", parse_docstring=True)
async def web_fetch_heavy_tool(url: str) -> str:
    """Heavy-task fetch: skip Tavily/DDG and use scrapling directly.

    Use for coding/scraping/anti-bot scenarios where lightweight tiers are
    unlikely to succeed (Cloudflare-protected, JS-heavy, large pages).

    Args:
        url: The URL to fetch.
    """
    return await _fetch_chain(url, started_at="scrapling")
