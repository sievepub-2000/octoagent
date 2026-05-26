"""Lesson-injection middleware.

Sprint-1 P0: inject top-K most recent + most-cited lessons from the
``LessonsStore`` into the system prompt at the start of each turn so the
agent benefits from past mistakes without depending on the model recalling
them from chat history.

Lessons are short, structured rows of (pattern, root_cause, fix). Injecting
the top 5 by default adds < 400 tokens to the prompt — cheap compared to the
correction loop saved when the model dodges a known pitfall.

Disable via env ``OCTOAGENT_LESSON_INJECTION_DISABLED=1``.
"""

from __future__ import annotations

import logging
import os
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

DEFAULT_LESSON_TOP_K = 5
MAX_LESSON_CHARS = 200  # per lesson summary line


def _disabled() -> bool:
    return os.environ.get("OCTOAGENT_LESSON_INJECTION_DISABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class LessonInjectionMiddleware(AgentMiddleware[AgentState]):
    """Prepend a compact lessons-learned block to the system prompt.

    The middleware uses ``modify_model_request`` (not ``before_model``) so the
    injection only affects the LLM call payload and is not persisted to thread
    state — keeping the checkpoint small.
    """

    def __init__(self, top_k: int = DEFAULT_LESSON_TOP_K):
        super().__init__()
        self.top_k = max(0, top_k)

    def _format_lessons(self) -> str | None:
        if self.top_k <= 0 or _disabled():
            return None
        try:
            # Sprint-2: go through the unified RAG facade so observability +
            # caching + future hybrid backends are consistent across callers.
            from src.storage.rag import unified_search
            from src.storage.self_evolution.lessons import LessonsStore

            query = self._latest_user_query_hint or "recent operational mistakes"
            entries = unified_search(table="lessons", query=query, top_k=self.top_k, mode="bm25")
            # Fallback to recency if BM25 returned nothing (cold store / no
            # overlap with current turn).
            if not entries:
                rows = LessonsStore.default().recent(limit=self.top_k)
            else:
                rows = [
                    {
                        "pattern": e.content,
                        "fix": (e.metadata or {}).get("fix", ""),
                    }
                    for e in entries
                ]
        except Exception as exc:  # pragma: no cover — degrades silently
            logger.debug("Lesson injection skipped: %s", exc)
            return None

        if not rows:
            return None

        lines: list[str] = ["<lessons_learned>"]
        for row in rows:
            getter = row.get if isinstance(row, dict) else (lambda k: getattr(row, k, ""))
            pattern = (getter("pattern") or "").strip().replace("\n", " ")
            fix = (getter("fix") or "").strip().replace("\n", " ")
            if not pattern and not fix:
                continue
            summary = f"- {pattern[:MAX_LESSON_CHARS]} → {fix[:MAX_LESSON_CHARS]}"
            lines.append(summary)
        lines.append("</lessons_learned>")
        if len(lines) <= 2:
            return None
        return "\n".join(lines)

    def _inject(self, request: ModelRequest) -> ModelRequest:
        block = self._format_lessons()
        if not block:
            return request
        sys_msg = SystemMessage(content=block)
        messages = list(request.messages)
        # Place lesson block right after any leading system message so the agent
        # treats it as part of the persistent instructions.
        insert_at = 0
        for idx, msg in enumerate(messages):
            if getattr(msg, "type", None) == "system":
                insert_at = idx + 1
            else:
                break
        messages.insert(insert_at, sys_msg)
        request.messages = messages
        return request

    @override
    def modify_model_request(self, request: ModelRequest, state: AgentState, runtime: Runtime) -> ModelRequest:
        return self._inject(request)

    @override
    async def amodify_model_request(self, request: ModelRequest, state: AgentState, runtime: Runtime) -> ModelRequest:
        return self._inject(request)


__all__ = ["LessonInjectionMiddleware"]
