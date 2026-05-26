"""Goal-drift detection middleware (Sprint-2 P0, REAL implementation).

Every ``every_n`` turns we compute the cosine similarity between the
``goal_contract.goal_summary`` and the rolling window of the last K AI
message snippets. If similarity drops below ``drift_threshold`` we inject a
SystemMessage alert prompting the agent to re-anchor.

Async-blocking note: ``embedding_service.embed_one`` calls into
sentence-transformers (synchronous, GIL-holding). The middleware therefore
caches the goal-summary embedding for the lifetime of the contract and only
embeds the action-window once per check, keeping per-turn latency well under
50 ms on a 6-core host.
"""

from __future__ import annotations

import logging
import math
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from src.models.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


class GoalDriftMiddleware(AgentMiddleware[AgentState]):
    """Compare goal vs recent actions every N turns and inject a re-anchor."""

    def __init__(
        self,
        *,
        every_n: int = 5,
        drift_threshold: float = 0.45,
        window: int = 5,
    ):
        super().__init__()
        self.every_n = max(1, every_n)
        self.drift_threshold = drift_threshold
        self.window = max(1, window)
        self._turn_counter = 0
        # Caches; keyed by goal_summary hash so a brand-new contract resets.
        self._goal_emb_cache: tuple[str, list[float]] | None = None

    def _goal_embedding(self, goal_summary: str) -> list[float] | None:
        if self._goal_emb_cache and self._goal_emb_cache[0] == goal_summary:
            return self._goal_emb_cache[1]
        try:
            emb = get_embedding_service().embed_one(goal_summary)
        except Exception as exc:
            logger.debug("GoalDrift: goal-embedding failed: %s", exc)
            return None
        self._goal_emb_cache = (goal_summary, emb)
        return emb

    @staticmethod
    def _recent_ai_text(messages: list[Any], window: int) -> str:
        snippets: list[str] = []
        for msg in reversed(messages):
            if getattr(msg, "type", None) == "ai":
                content = getattr(msg, "content", "")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            snippets.append(str(part.get("text", "")))
                else:
                    snippets.append(str(content))
                if len(snippets) >= window:
                    break
        return "\n".join(reversed(snippets))[:2000]

    @staticmethod
    def _parse_goal_from_messages(messages: list[Any]) -> str | None:
        """Extract goal_summary from the latest <goal_contract> block."""
        for msg in reversed(messages):
            content = getattr(msg, "content", "")
            if not isinstance(content, str) or "<goal_contract>" not in content:
                continue
            # Find first 'summary: ...' line within the block.
            inside = content.split("<goal_contract>", 1)[1].split("</goal_contract>", 1)[0]
            for line in inside.splitlines():
                line = line.strip()
                if line.startswith("summary:"):
                    return line.split("summary:", 1)[1].strip() or None
            return None
        return None

    @staticmethod
    def _parse_task_state_goal_from_messages(messages: list[Any]) -> str | None:
        """Extract the active task goal from task-state checkpoint messages."""
        for msg in reversed(messages):
            content = getattr(msg, "content", "")
            if not isinstance(content, str):
                continue
            if "[OctoAgent persistent task state]" not in content and "Persistent task state:" not in content:
                continue
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("Goal:"):
                    return stripped.split("Goal:", 1)[1].strip() or None
                if stripped.startswith("- Goal:"):
                    return stripped.split("- Goal:", 1)[1].strip() or None
        return None

    def _active_goal_summary(self, state: AgentState) -> str | None:
        """Prefer the live task goal over stale historical goal contracts."""
        task_state = state.get("task_state")
        if isinstance(task_state, dict):
            status = str(task_state.get("status") or "active").strip().lower()
            goal = str(task_state.get("goal") or "").strip()
            if goal and status not in {"completed", "cancelled", "failed"}:
                return goal
        runtime_state = state.get("runtime") or {}
        if isinstance(runtime_state, dict):
            goal = str(runtime_state.get("task_goal") or runtime_state.get("current_goal") or "").strip()
            if goal:
                return goal
        messages = list(state.get("messages", []) or [])
        return self._parse_task_state_goal_from_messages(messages) or self._parse_goal_from_messages(messages)

    def _maybe_alert(self, state: AgentState) -> dict | None:
        runtime_state = state.get("runtime") or {}
        closure = runtime_state.get("research_closure") if isinstance(runtime_state, dict) else None
        if isinstance(closure, dict) and closure.get("status") == "must_finalize":
            return None
        self._turn_counter += 1
        if self._turn_counter % self.every_n != 0:
            return None
        goal_summary = self._active_goal_summary(state)
        if not goal_summary:
            return None
        messages = state.get("messages", []) or []
        window_text = self._recent_ai_text(list(messages), self.window)
        if not window_text:
            return None
        goal_emb = self._goal_embedding(goal_summary)
        if goal_emb is None:
            return None
        try:
            window_emb = get_embedding_service().embed_one(window_text)
        except Exception as exc:
            logger.debug("GoalDrift: window-embedding failed: %s", exc)
            return None
        score = _cosine(goal_emb, window_emb)
        logger.debug("GoalDrift turn=%d score=%.3f thr=%.3f", self._turn_counter, score, self.drift_threshold)
        if score >= self.drift_threshold:
            return None
        alert = SystemMessage(
            content=(f"<drift_alert>\n  Recent actions diverged from the user goal (cosine={score:.3f} < {self.drift_threshold:.2f}).\n  Re-anchor: '{goal_summary[:160]}'\n  Re-check success_criteria before continuing.\n</drift_alert>")
        )
        logger.warning(
            "GoalDrift: drift detected at turn=%d (score=%.3f, threshold=%.2f)",
            self._turn_counter,
            score,
            self.drift_threshold,
        )
        return {"messages": [alert]}

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_alert(state)

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        # Embedding calls are blocking; offload to thread to avoid stalling
        # the event loop in async LangGraph runs.
        import asyncio

        return await asyncio.to_thread(self._maybe_alert, state)


__all__ = ["GoalDriftMiddleware"]
