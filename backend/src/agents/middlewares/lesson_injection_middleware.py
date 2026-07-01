"""Lesson-injection middleware (Optimized v2).

Replaces expensive BM25/FAISS vector search with direct file-based lookup +
thread-local caching. Lessons change infrequently, so we cache the injected
block per thread and skip re-computation on subsequent turns.

Key optimizations:
  - No FAISS/vector DB load overhead (BM25 requires loading embedding model)
  - Thread-local cache: lesson block computed once per thread, reused for all turns
  - Fallback to direct file read from LessonsStore.recent() which is O(k)
  - Silent degradation on error (no exception path through vector search)
"""

from __future__ import annotations

import logging
import os
import threading
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


# Thread-local cache for lesson blocks (keyed by thread_id)
_lesson_cache: dict[str, str | None] = {}
_lesson_cache_lock = threading.Lock()


class LessonInjectionMiddleware(AgentMiddleware[AgentState]):
    """Prepend a compact lessons-learned block to the system prompt.

    Optimized v2: uses direct file-based lookup instead of BM25/FAISS search,
    with thread-local caching to avoid recomputation on every turn.
    """

    def __init__(self, top_k: int = DEFAULT_LESSON_TOP_K):
        super().__init__()
        self.top_k = max(0, top_k)

    def _get_thread_id(self, state: AgentState) -> str | None:
        """Extract thread_id from state for caching."""
        try:
            tid = state.get("thread_id")
            if tid:
                return str(tid)
            runtime_data = state.get("runtime") or {}
            tid = runtime_data.get("thread_id")
            if tid:
                return str(tid)
        except Exception:
            pass
        return None

    def _format_lessons(self, thread_id: str | None = None) -> str | None:
        """Format lessons using direct file read (no FAISS overhead).

        Optimized v2: skips BM25 vector search entirely. Uses LessonsStore.recent()
        which reads directly from the store files - much faster for small stores.
        """
        if self.top_k <= 0 or _disabled():
            return None

        # Check thread-local cache first
        if thread_id:
            with _lesson_cache_lock:
                cached = _lesson_cache.get(thread_id)
            if cached is not None:
                return cached

        try:
            from src.storage.self_evolution.lessons import LessonsStore

            rows = LessonsStore.default().recent(limit=self.top_k)
        except Exception as exc:  # pragma: no cover - degrades silently
            logger.debug("Lesson injection skipped: %s", exc)
            result = None
            if thread_id:
                with _lesson_cache_lock:
                    _lesson_cache[thread_id] = result
            return result

        if not rows:
            result = None
            if thread_id:
                with _lesson_cache_lock:
                    _lesson_cache[thread_id] = result
            return result

        lines: list[str] = ["<lessons_learned>"]
        for row in rows:
            getter = row.get if isinstance(row, dict) else (lambda k: getattr(row, k, ""))
            pattern = (getter("pattern") or "").strip().replace("\n", " ")
            fix = (getter("fix") or "").strip().replace("\n", " ")
            if not pattern and not fix:
                continue
            summary = f"- {pattern[:MAX_LESSON_CHARS]} -> {fix[:MAX_LESSON_CHARS]}"
            lines.append(summary)
        lines.append("</lessons_learned>")
        if len(lines) <= 2:
            result = None
        else:
            result = "\n".join(lines)

        if thread_id:
            with _lesson_cache_lock:
                _lesson_cache[thread_id] = result

        return result

    def _inject(self, request: ModelRequest, thread_id: str | None = None) -> ModelRequest:
        block = self._format_lessons(thread_id=thread_id)
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
        thread_id = self._get_thread_id(state)
        return self._inject(request, thread_id=thread_id)

    @override
    async def amodify_model_request(self, request: ModelRequest, state: AgentState, runtime: Runtime) -> ModelRequest:
        thread_id = self._get_thread_id(state)
        return self._inject(request, thread_id=thread_id)


__all__ = ["LessonInjectionMiddleware"]
