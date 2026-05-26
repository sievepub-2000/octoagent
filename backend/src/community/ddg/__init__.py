"""DuckDuckGo + httpx web tools (zero API key, system proxy aware)."""

from src.community.ddg.tools import web_fetch_tool, web_search_tool

__all__ = ["web_search_tool", "web_fetch_tool"]
