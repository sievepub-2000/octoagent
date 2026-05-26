"""Web content reader tool — fetch and extract clean content from URLs.

Uses readabilipy (Mozilla Readability port) for article extraction and
httpx for fetching.  Both are already in the project dependencies.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated
from urllib.parse import urlparse

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from src.agents.thread_state import ThreadState
from src.utils.url_safety import is_url_safe, safe_join_url

logger = logging.getLogger(__name__)

_MAX_EXTRACTED_CONTENT_CHARS = 24_000
_GITHUB_BOILERPLATE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"Sponsor open source projects you depend on",
        r"Contributors are working behind the scenes to make open source better for everyone",
        r"Explore sponsorable projects",
        r"ProTip!\s*Press the / key to activate the search input again and adjust your query",
        r"resolvedServerColorMode",
        r"You can[’']t perform that action at this time",
        r"Sign in to GitHub",
        r"Skip to content",
        r"Navigation Menu",
        r"Search or jump to",
    )
)
_LOW_QUALITY_PAGE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"Sponsor open source projects you depend on",
        r"resolvedServerColorMode",
        r"You can[’']t perform that action at this time",
        r"Sign in to GitHub",
        r"This page requires JavaScript",
        r"Please sign in to continue",
        r"Access denied",
        r"verify you are human",
        r"enable JavaScript and cookies",
    )
)


def _is_github_url(url: str) -> bool:
    """Return True when the URL points at GitHub's web UI."""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return host == "github.com" or host.endswith(".github.com")


def _clean_extracted_text(url: str, text: str) -> str:
    """Remove high-volume page chrome from extracted web text."""
    if not text:
        return text
    cleaned = text
    if _is_github_url(url):
        lines = []
        for line in cleaned.splitlines():
            stripped = line.strip()
            if not stripped:
                lines.append("")
                continue
            if any(pattern.search(stripped) for pattern in _GITHUB_BOILERPLATE_PATTERNS):
                continue
            lines.append(line)
        cleaned = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _cap_extracted_content(text: str) -> str:
    """Keep tool output inside a compact model-friendly envelope."""
    if len(text) <= _MAX_EXTRACTED_CONTENT_CHARS:
        return text
    return text[:_MAX_EXTRACTED_CONTENT_CHARS].rstrip() + "\n\n... (content shortened by OctoAgent web reader; use a narrower URL or query for more detail)"


def _quality_failure_reason(url: str, text: str, *, original_html: str = "") -> str | None:
    """Return a semantic extraction failure reason, or None for usable content."""
    normalized = re.sub(r"\s+", " ", text or "").strip()
    body_without_headers = re.sub(r"^# .*? Source: .*?", "", normalized, flags=re.IGNORECASE).strip()
    if len(body_without_headers) < 160:
        return "extracted content is too short to be useful"

    combined = f"{text}\n{original_html[:20_000]}"
    boilerplate_hits = sum(1 for pattern in _LOW_QUALITY_PAGE_PATTERNS if pattern.search(combined))
    if boilerplate_hits >= 2:
        return "page extraction is dominated by boilerplate, login, or blocked-page text"

    words = re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]{2,}", body_without_headers)
    if len(set(words)) < 20 and len(body_without_headers) < 1_000:
        return "extracted content has too little semantic variety"

    if _is_github_url(url) and "github" in body_without_headers.lower() and boilerplate_hits >= 1:
        return "GitHub page extraction still contains page chrome instead of repository content"

    return None


def _low_quality_tool_message(url: str, reason: str, tool_call_id: str) -> ToolMessage:
    """Build a recoverable tool error for unusable extracted content."""
    return ToolMessage(
        (f"Error: low-quality webpage extraction for {url}: {reason}. Use a more specific raw file/document URL, an API endpoint, or a different public source instead of reusing this noisy page."),
        tool_call_id=tool_call_id,
        status="error",
    )


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
    import httpx

    if not is_url_safe(url):
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

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; OctoAgent/1.0; +https://github.com/OctoAgent)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        current_url = url
        with httpx.Client(timeout=30.0, follow_redirects=False) as client:
            for _ in range(8):
                resp = client.get(current_url, headers=headers)
                if resp.is_redirect:
                    next_url = safe_join_url(current_url, resp.headers.get("Location", ""))
                    if next_url is None:
                        return Command(
                            update={
                                "messages": [
                                    ToolMessage(
                                        "Error: Redirect target points to a private/internal network address.",
                                        tool_call_id=tool_call_id,
                                    )
                                ]
                            }
                        )
                    current_url = next_url
                    continue
                break
            else:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "Error: Too many redirects while fetching URL",
                                tool_call_id=tool_call_id,
                            )
                        ]
                    }
                )
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
        return Command(update={"messages": [ToolMessage(content, tool_call_id=tool_call_id)]})

    # ---- markdown ----
    if mode == "markdown":
        try:
            from markdownify import markdownify as md

            content = _cap_extracted_content(
                _clean_extracted_text(
                    current_url,
                    md(html, heading_style="ATX", strip=["script", "style"]),
                )
            )
            failure_reason = _quality_failure_reason(current_url, content, original_html=html)
            if failure_reason is not None:
                return Command(
                    update={
                        "messages": [
                            _low_quality_tool_message(
                                current_url,
                                failure_reason,
                                tool_call_id,
                            )
                        ]
                    }
                )
            return Command(update={"messages": [ToolMessage(content, tool_call_id=tool_call_id)]})
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
                        links.append({"text": self._text.strip(), "href": self._href})
                        self._href = None
                        self._text = ""

            parser = LinkParser()
            parser.feed(html)
            content = json.dumps(links[:500], indent=2, ensure_ascii=False)
            return Command(update={"messages": [ToolMessage(content, tool_call_id=tool_call_id)]})
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
            content = "\n\n".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)

        result = _cap_extracted_content(
            _clean_extracted_text(
                current_url,
                f"# {title}\n\nSource: {current_url}\n\n{content}",
            )
        )
        failure_reason = _quality_failure_reason(current_url, result, original_html=html)
        if failure_reason is not None:
            return Command(
                update={
                    "messages": [
                        _low_quality_tool_message(
                            current_url,
                            failure_reason,
                            tool_call_id,
                        )
                    ]
                }
            )
        return Command(update={"messages": [ToolMessage(result, tool_call_id=tool_call_id)]})
    except ImportError:
        # Fallback to markdownify
        try:
            from markdownify import markdownify as md

            content = _cap_extracted_content(
                _clean_extracted_text(
                    current_url,
                    md(html, heading_style="ATX", strip=["script", "style"]),
                )
            )
            failure_reason = _quality_failure_reason(current_url, content, original_html=html)
            if failure_reason is not None:
                return Command(
                    update={
                        "messages": [
                            _low_quality_tool_message(
                                current_url,
                                failure_reason,
                                tool_call_id,
                            )
                        ]
                    }
                )
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
