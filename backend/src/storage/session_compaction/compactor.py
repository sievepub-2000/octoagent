"""Session compactor — compresses long conversation context.

Keeps system messages, recent turns, and tool-call boundaries intact while
summarising older turns to fit within a token budget.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from src.runtime.context_budget import estimate_text_tokens

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    return estimate_text_tokens(text, minimum=0)


class CompactionConfig(BaseModel):
    """User-facing compaction settings."""

    enabled: bool = True
    max_context_tokens: int = Field(default=32_000, description="Target token budget after compaction")
    keep_recent_turns: int = Field(default=6, description="Number of recent turns to keep verbatim")
    keep_system_messages: bool = True
    keep_tool_boundaries: bool = True
    strategy: str = Field(
        default="summarize",
        description="Compaction strategy: 'summarize' (review/compress), 'hybrid', or emergency 'truncate'",
    )
    preflight_ratio: float = Field(default=0.5, ge=0.1, le=1.0, description="Hermes-style preflight compaction threshold")
    aggressive_ratio: float = Field(default=0.85, ge=0.1, le=1.0, description="Gateway-style aggressive compaction threshold")
    min_turns_before_compact: int = Field(default=10, description="Minimum turns before compaction triggers")
    preserve_anchors: bool = Field(default=True, description="Keep messages flagged as important anchors")


@dataclass
class Message:
    role: str
    content: str
    token_count: int = 0
    is_system: bool = False
    is_tool_boundary: bool = False
    is_anchor: bool = False


@dataclass
class CompactionResult:
    messages: list[Message] = field(default_factory=list)
    original_count: int = 0
    compacted_count: int = 0
    tokens_saved: int = 0
    summary_inserted: bool = False


class SessionCompactor:
    """Compress a conversation to fit within a token budget.

    Supports an optional LLM callback for the 'summarize' strategy.
    If no LLM callback is provided, falls back to extractive summary.
    """

    def __init__(
        self,
        config: CompactionConfig | None = None,
        *,
        llm_summarize_fn: Callable[[str], str] | None = None,
    ) -> None:
        self._config = config or CompactionConfig()
        self._llm_summarize = llm_summarize_fn

    @property
    def config(self) -> CompactionConfig:
        return self._config

    def compact(self, messages: list[Message]) -> CompactionResult:
        """Compact a list of messages according to the configuration.

        Strategy:
          1. Always keep system messages (first) and recent N turns.
          2. Middle turns are summarised into a single compaction message.
          3. Tool-boundary messages (tool_use / tool_result) are kept as stubs.
          4. Anchor messages are always preserved.
        """
        if not self._config.enabled or not messages:
            return CompactionResult(
                messages=messages,
                original_count=len(messages),
                compacted_count=len(messages),
            )

        # Guard: don't compact very short conversations
        non_system = [m for m in messages if not m.is_system]
        if len(non_system) < self._config.min_turns_before_compact:
            return CompactionResult(
                messages=messages,
                original_count=len(messages),
                compacted_count=len(messages),
            )

        total_tokens = sum(m.token_count for m in messages)
        if total_tokens <= self._config.max_context_tokens:
            return CompactionResult(
                messages=messages,
                original_count=len(messages),
                compacted_count=len(messages),
            )

        # Partition
        system_msgs: list[Message] = []
        middle_msgs: list[Message] = []
        recent_msgs: list[Message] = []
        protected_msgs: list[Message] = []

        keep_n = self._config.keep_recent_turns * 2  # user+assistant pairs

        for i, msg in enumerate(messages):
            if msg.is_system and self._config.keep_system_messages:
                system_msgs.append(msg)
            elif i >= len(messages) - keep_n:
                recent_msgs.append(msg)
            elif msg.is_anchor and self._config.preserve_anchors:
                protected_msgs.append(msg)
            elif msg.is_tool_boundary and self._config.keep_tool_boundaries:
                protected_msgs.append(msg)
            else:
                middle_msgs.append(msg)

        # Summarise middle based on strategy
        if middle_msgs:
            if self._config.strategy == "truncate":
                # Emergency fallback only. Normal long-running work should use
                # review-oriented summaries so task intent survives compaction.
                summary_msg = Message(
                    role="system",
                    content=f"[Session compaction — {len(middle_msgs)} older messages reviewed; emergency transcript elision applied]",
                    token_count=10,
                    is_system=True,
                )
            else:
                # 'summarize' and 'hybrid' — build a textual summary
                summary_text = self._build_summary(middle_msgs)
                summary_msg = Message(
                    role="system",
                    content=(
                        f"[Session compaction review — {len(middle_msgs)} messages compressed]\n"
                        "Preserve task goal, unresolved blockers, operator preferences, tool capability decisions, "
                        "resource state, and next action. Treat this as a stage review for self-feedback and memory follow-up.\n"
                        f"{summary_text}"
                    ),
                    token_count=len(summary_text) // 4,  # rough estimate
                    is_system=True,
                )
            result_messages = system_msgs + [summary_msg] + protected_msgs + recent_msgs
        else:
            result_messages = system_msgs + protected_msgs + recent_msgs

        tokens_after = sum(m.token_count for m in result_messages)
        return CompactionResult(
            messages=result_messages,
            original_count=len(messages),
            compacted_count=len(result_messages),
            tokens_saved=max(0, total_tokens - tokens_after),
            summary_inserted=bool(middle_msgs),
        )

    def _build_summary(self, messages: list[Message]) -> str:
        """Create a compact summary of the compacted messages.

        Uses the LLM callback when available; falls back to extractive
        snippets otherwise.
        """
        # Build raw transcript for LLM
        transcript_lines: list[str] = []
        for msg in messages[:40]:  # cap input to LLM
            role = msg.role.capitalize()
            snippet = msg.content[:300].replace("\n", " ")
            transcript_lines.append(f"{role}: {snippet}")
        transcript = "\n".join(transcript_lines)

        if self._llm_summarize is not None:
            try:
                prompt = f"Summarise the following conversation excerpt in 3-5 concise bullet points. Preserve key decisions, action items, and important context.\n\n{transcript}"
                return self._llm_summarize(prompt)
            except Exception:
                logger.warning("LLM summarization failed, falling back to extractive summary", exc_info=True)

        # Extractive fallback
        lines: list[str] = []
        for msg in messages[:20]:
            role = msg.role.capitalize()
            snippet = msg.content[:120].replace("\n", " ")
            lines.append(f"- {role}: {snippet}")
        if len(messages) > 20:
            lines.append(f"- ... and {len(messages) - 20} more messages")
        return "\n".join(lines)

    def ensure_token_counts(self, messages: list[Message]) -> list[Message]:
        """Fill in missing token counts using the heuristic estimator."""
        for msg in messages:
            if msg.token_count == 0 and msg.content:
                msg.token_count = _estimate_tokens(msg.content)
        return messages
