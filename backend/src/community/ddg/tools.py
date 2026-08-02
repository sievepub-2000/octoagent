"""Keyless DuckDuckGo web search fallback."""

from __future__ import annotations

import json
import logging

from langchain.tools import tool

from src.runtime.config import get_app_config
from src.utils.proxy_env import without_unavailable_local_proxy

logger = logging.getLogger(__name__)


@tool("web_search", parse_docstring=True)
def web_search_tool(query: str) -> str:
    """Search the web through DuckDuckGo and return title, URL, and snippet.

    Args:
        query: Search query.
    """
    config = get_app_config().get_tool_config("web_search")
    try:
        max_results = int(config.model_extra.get("max_results", 8)) if config and config.model_extra else 8
    except (TypeError, ValueError):
        max_results = 8

    try:
        from ddgs import DDGS

        with without_unavailable_local_proxy(), DDGS(timeout=25) as ddg:
            results = list(ddg.text(query, region="us-en", max_results=max_results))
    except Exception as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)
        return json.dumps([{"error": f"web_search failed: {type(exc).__name__}: {exc}"}], ensure_ascii=False)

    return json.dumps(
        [
            {
                "title": str(result.get("title") or "").strip(),
                "url": result.get("href") or result.get("url") or "",
                "snippet": str(result.get("body") or "").strip(),
            }
            for result in results
        ],
        ensure_ascii=False,
        indent=2,
    )


__all__ = ["web_search_tool"]
