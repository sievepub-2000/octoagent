"""Canonical message-content extraction helper.

Replaces 7 duplicated ``_message_text`` definitions across middlewares and
run-record code. The implementation matches the *robust* variant previously
duplicated in ``tool_budget_middleware`` / ``progress_stall_middleware``:
short-circuits on plain ``str`` content and preserves non-dict list items
that the simpler variants silently dropped.
"""

from __future__ import annotations

from typing import Any

__all__ = ["latest_human_index", "message_text"]


def message_text(message: Any) -> str:
    """Return text content from a LangChain message-like object."""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return " ".join(parts)
    return str(content or "")

def latest_human_index(messages: list) -> int:
    """Return the index of the most-recent ``HumanMessage`` in ``messages``.

    Returns ``-1`` if no human message is found. Imported lazily to avoid a
    hard dependency on ``langchain_core`` at module import time for callers
    that may not need it.
    """
    from langchain_core.messages import HumanMessage

    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return index
    return -1
