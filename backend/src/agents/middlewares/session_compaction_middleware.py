"""Middleware for session compaction — compresses long context before LLM call.

Integrates the claw-code SessionCompactor into the agent middleware stack.
When context tokens exceed the configured budget, older messages are
summarised to free up the context window.
"""

from __future__ import annotations

import logging
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from src.session_compaction.compactor import (
    CompactionConfig,
    Message,
    SessionCompactor,
)

logger = logging.getLogger(__name__)

# Rough bytes-per-token ratio for English text
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Quick token estimate without loading a tokeniser."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _state_messages_to_compactor(messages: list[Any]) -> list[Message]:
    """Convert LangChain message objects to compactor Message format."""
    result: list[Message] = []
    for msg in messages:
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        content_str = str(content)
        msg_type = getattr(msg, "type", "")
        role = msg_type if msg_type in ("human", "ai", "system", "tool") else "human"
        token_count = _estimate_tokens(content_str)
        result.append(
            Message(
                role=role,
                content=content_str,
                token_count=token_count,
                is_system=(role == "system"),
                is_tool_boundary=(role == "tool" or bool(getattr(msg, "tool_calls", None))),
            )
        )
    return result


class SessionCompactionMiddleware(AgentMiddleware):
    """Compress conversation context when it exceeds token budget.

    Uses the ``before_model`` hook so compaction happens just before the LLM
    sees the messages.  The original messages list is replaced with the
    compacted version only when compaction actually occurs.
    """

    def __init__(
        self,
        max_context_tokens: int = 32_000,
        keep_recent_turns: int = 6,
    ) -> None:
        config = CompactionConfig(
            enabled=True,
            max_context_tokens=max_context_tokens,
            keep_recent_turns=keep_recent_turns,
        )
        self._compactor = SessionCompactor(config)

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        """Check context pressure and compact if over budget.

        Tiered strategy selection based on pressure ratio:
          - ratio < 1.0  → no compaction needed
          - 1.0–2.0     → truncate (drop oldest, fast and safe)
          - 2.0–4.0     → hybrid   (truncate recent + summarise middle)
          - > 4.0       → summarize (full LLM summary, most aggressive)
        """
        messages = state.get("messages")
        if not messages:
            return None

        compactor_msgs = _state_messages_to_compactor(messages)
        total_tokens = sum(m.token_count for m in compactor_msgs)
        budget = self._compactor.config.max_context_tokens

        if total_tokens <= budget:
            return None  # Context fits — no compaction needed

        # ── Tiered strategy selection ─────────────────────────────────────
        pressure_ratio = total_tokens / max(budget, 1)
        original_strategy = self._compactor.config.strategy
        if pressure_ratio < 2.0:
            effective_strategy = "truncate"
        elif pressure_ratio < 4.0:
            effective_strategy = "hybrid"
        else:
            effective_strategy = "summarize"

        if effective_strategy != original_strategy:
            logger.info(
                "Session compaction: pressure ratio=%.2fx → upgrading strategy %s → %s",
                pressure_ratio,
                original_strategy,
                effective_strategy,
            )
            self._compactor.config.strategy = effective_strategy

        result = self._compactor.compact(compactor_msgs)

        # Restore original strategy for next call
        self._compactor.config.strategy = original_strategy

        if not result.summary_inserted:
            return None  # Nothing was compacted

        logger.info(
            "Session compaction: %d → %d messages, saved ~%d tokens (strategy=%s, ratio=%.2fx)",
            result.original_count,
            result.compacted_count,
            result.tokens_saved,
            effective_strategy,
            pressure_ratio,
        )

        # Rebuild LangChain-compatible message dicts for the compacted result
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        rebuilt: list[Any] = []
        for cm in result.messages:
            if cm.is_system or cm.role == "system":
                rebuilt.append(SystemMessage(content=cm.content))
            elif cm.role == "ai":
                rebuilt.append(AIMessage(content=cm.content))
            else:
                rebuilt.append(HumanMessage(content=cm.content))

        runtime_state = dict(state.get("runtime") or {})
        runtime_state["context_pressure"] = "high" if pressure_ratio >= 2.0 else "medium"
        runtime_state["compaction_strategy"] = effective_strategy
        runtime_state["pressure_ratio"] = round(pressure_ratio, 2)
        runtime_state["recommended_memory_action"] = "compact"
        runtime_state["updated_at"] = runtime_state.get("updated_at")
        return {"messages": rebuilt, "runtime": runtime_state}
