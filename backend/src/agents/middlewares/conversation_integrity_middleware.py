"""Conversation integrity middleware.

Defensive, deterministic after-model guard that collapses degenerate repeated
output before it reaches the user. It exists to neutralize a class of failure
where a small/fast model emits the same sentence or preamble many times in a
single final answer (for example "let me re-fetch ..." repeated five times).

Design constraints:
  * Never fabricate or add new content - only remove exact repetition.
  * Only touch the latest text-only AIMessage that has no tool calls
    (i.e. a final answer). Tool-calling turns are left untouched.
  * Replace in place by reusing the original message id so the LangGraph
    ``add_messages`` reducer overwrites rather than appends.
"""

from __future__ import annotations

import logging
import re
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

_MIN_REPEATS = 3
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?\.])\s*")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _collapse_lines(text: str) -> str:
    out: list[str] = []
    prev_norm: str | None = None
    for line in text.split("\n"):
        norm = _normalize(line)
        if norm and norm == prev_norm:
            # Drop consecutive duplicate lines beyond the first occurrence.
            continue
        prev_norm = norm
        out.append(line)
    return "\n".join(out)


def _collapse_sentences(text: str) -> str:
    out: list[str] = []
    prev: str | None = None
    for part in _SENTENCE_SPLIT.split(text):
        if part == "":
            continue
        norm = _normalize(part)
        if norm and norm == prev:
            continue
        prev = norm
        out.append(part)
    return "".join(out)


def _max_repeat_count(text: str) -> int:
    line_counts: dict[str, int] = {}
    for line in text.split("\n"):
        norm = _normalize(line)
        if norm:
            line_counts[norm] = line_counts.get(norm, 0) + 1
    line_max = max(line_counts.values(), default=1)

    sent_counts: dict[str, int] = {}
    for part in _SENTENCE_SPLIT.split(text):
        norm = _normalize(part)
        if norm:
            sent_counts[norm] = sent_counts.get(norm, 0) + 1
    sent_max = max(sent_counts.values(), default=1)
    return max(line_max, sent_max)


def _sanitize(text: str) -> str | None:
    if _max_repeat_count(text) < _MIN_REPEATS:
        return None
    cleaned = _collapse_sentences(_collapse_lines(text)).strip()
    if not cleaned or cleaned == text.strip():
        return None
    return cleaned


class ConversationIntegrityMiddleware(AgentMiddleware[AgentState]):
    """Collapse degenerate repeated text in the final assistant answer."""

    def _maybe_fix(self, state: AgentState) -> dict | None:
        messages = list(state.get("messages", []) or [])
        if not messages:
            return None
        last = messages[-1]
        if not isinstance(last, AIMessage):
            return None
        if getattr(last, "tool_calls", None):
            return None
        if not getattr(last, "id", None):
            # Without a stable id the reducer would append a duplicate instead
            # of replacing; skip rather than risk doubling the output.
            return None
        content = getattr(last, "content", "")
        if not isinstance(content, str) or not content.strip():
            return None
        cleaned = _sanitize(content)
        if cleaned is None:
            return None
        logger.info(
            "ConversationIntegrityMiddleware: collapsed repeated output (%d -> %d chars)",
            len(content),
            len(cleaned),
        )
        fixed = last.model_copy(update={"content": cleaned})
        return {"messages": [fixed]}

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_fix(state)

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_fix(state)
