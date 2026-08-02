"""Tavily web search with a keyless DuckDuckGo fallback."""

from __future__ import annotations

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
    config = get_app_config().get_tool_config("web_search")
    if config is not None and config.model_extra:
        return config.model_extra.get("api_key")
    return None


def _client() -> Any:
    key = _resolve_api_key()
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not configured")
    return lazy_tavily.TavilyClient(api_key=key)


def _max_results() -> int:
    config = get_app_config().get_tool_config("web_search")
    try:
        return int(config.model_extra.get("max_results", 5)) if config and config.model_extra else 5
    except (TypeError, ValueError):
        return 5


@tool("web_search", parse_docstring=True)
def web_search_tool(query: str) -> str:
    """Search the web with Tavily, falling back to DuckDuckGo.

    Args:
        query: Search query.
    """
    try:
        response = _client().search(query[:400], max_results=_max_results())
    except Exception as exc:
        logger.info("Tavily search unavailable; using DuckDuckGo: %s", exc)
        from src.community.ddg.tools import web_search_tool as ddg_search

        return ddg_search.invoke({"query": query})

    return json.dumps(
        [
            {"title": result.get("title", ""), "url": result.get("url", ""), "snippet": result.get("content", "")}
            for result in response.get("results", [])
        ],
        ensure_ascii=False,
        indent=2,
    )


__all__ = ["web_search_tool"]
