"""Web content reader tool — fetch and extract clean content from URLs.

Uses readabilipy (Mozilla Readability port) for article extraction and
httpx for fetching.  Both are already in the project dependencies.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)


@tool("read_webpage", parse_docstring=True)
def read_webpage_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    url: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    extract_mode: str = "article",
) -> Command:
    """Fetch a web page and extract its main content as clean text or markdown.

    Modes:
      - "article"  — extract main article content using Readability algorithm.
      - "markdown"  — convert full HTML to markdown.
      - "raw"       — return raw HTML (first 50 KB).
      - "links"     — extract all hyperlinks with text and href.

    Args:
        url: The URL to fetch.
        extract_mode: One of "article", "markdown", "raw", "links" (default: article).
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    import httpx

    if not url.startswith(("http://", "https://")):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "Error: URL must start with http:// or https://",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    # SSRF protection: block private/internal IP ranges
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if hostname:
            resolved_ip = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(resolved_ip)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_link_local:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "Error: Access to private/internal network addresses is not allowed.",
                                tool_call_id=tool_call_id,
                            )
                        ]
                    }
                )
    except (socket.gaierror, ValueError):
        pass  # Let httpx handle DNS resolution errors

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; OctoAgent/1.0; +https://github.com/OctoAgent)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError as exc:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"HTTP error {exc.response.status_code} fetching {url}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
    except Exception as exc:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Error fetching URL: {exc}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    mode = extract_mode.lower().strip()

    # ---- raw ----
    if mode == "raw":
        content = html[:50_000]
        return Command(
            update={
                "messages": [
                    ToolMessage(content, tool_call_id=tool_call_id)
                ]
            }
        )

    # ---- markdown ----
    if mode == "markdown":
        try:
            from markdownify import markdownify as md

            content = md(html, heading_style="ATX", strip=["script", "style"])
            if len(content) > 60_000:
                content = content[:60_000] + "\n\n... (truncated)"
            return Command(
                update={
                    "messages": [
                        ToolMessage(content, tool_call_id=tool_call_id)
                    ]
                }
            )
        except ImportError:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "Error: markdownify not installed.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

    # ---- links ----
    if mode == "links":
        try:
            from html.parser import HTMLParser

            links: list[dict[str, str]] = []

            class LinkParser(HTMLParser):
                _href: str | None = None
                _text: str = ""

                def handle_starttag(self, tag, attrs):
                    if tag == "a":
                        self._href = dict(attrs).get("href")
                        self._text = ""

                def handle_data(self, data):
                    if self._href is not None:
                        self._text += data

                def handle_endtag(self, tag):
                    if tag == "a" and self._href:
                        links.append(
                            {"text": self._text.strip(), "href": self._href}
                        )
                        self._href = None
                        self._text = ""

            parser = LinkParser()
            parser.feed(html)
            content = json.dumps(links[:500], indent=2, ensure_ascii=False)
            return Command(
                update={
                    "messages": [
                        ToolMessage(content, tool_call_id=tool_call_id)
                    ]
                }
            )
        except Exception as exc:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"Error extracting links: {exc}",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

    # ---- article (default) ----
    try:
        from readabilipy import simple_json_from_html_string

        article = simple_json_from_html_string(html, use_readability=True)
        title = article.get("title", "")
        content = article.get("plain_text", [])
        if isinstance(content, list):
            content = "\n\n".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in content
            )

        result = f"# {title}\n\nSource: {url}\n\n{content}"
        if len(result) > 60_000:
            result = result[:60_000] + "\n\n... (truncated)"
        return Command(
            update={
                "messages": [
                    ToolMessage(result, tool_call_id=tool_call_id)
                ]
            }
        )
    except ImportError:
        # Fallback to markdownify
        try:
            from markdownify import markdownify as md

            content = md(html, heading_style="ATX", strip=["script", "style"])
            if len(content) > 60_000:
                content = content[:60_000] + "\n\n... (truncated)"
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"Source: {url}\n\n{content}",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        except ImportError:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "Error: readabilipy and markdownify not installed.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
