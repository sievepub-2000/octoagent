"""Context compression system with anti-hijack protection.

Inspired by hermes-agent's approach: keep recent messages verbatim, summarize
older ones into structured events using an aux model (or rule-based fallback),
and inject strong anti-resume directives to prevent the LLM from re-executing
tasks described in the compressed summary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.agents.core.compression_config import CompressionConfig, load_compression_config

# ---------------------------------------------------------------------------
# Token estimation helpers (re-exported from context_budget for convenience)
# ---------------------------------------------------------------------------


def _estimate_text_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars/token ASCII, ~2 chars/token CJK."""
    if not text:
        return 0
    ascii_count = sum(1 for ch in text if ord(ch) < 128)
    non_ascii = len(text) - ascii_count
    return int(ascii_count / 4 + non_ascii / 2)


def _message_text(message: Any) -> str:
    """Extract string content from a message (BaseMessage or dict)."""
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content", "")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                parts.append(str(text) if text is not None else str(item))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _message_role(message: Any) -> str:
    """Get the role of a message."""
    if isinstance(message, dict):
        return str(message.get("role", "unknown"))
    return str(getattr(message, "type", getattr(message, "role", "unknown")))


# ---------------------------------------------------------------------------
# TokenBudget
# ---------------------------------------------------------------------------


@dataclass
class TokenBudget:
    """Tracks token usage across conversation categories with hard limits.

    Budget allocation ratios (of max_context_size):
        system_prompt     ~15%
        tool_description  ~20%
        conversation      ~45%
        summary           ~20%
    """

    max_context_size: int = 128_000
    system_prompt_tokens: int = 0
    tool_description_tokens: int = 0
    conversation_tokens: int = 0
    summary_tokens: int = 0

    # Per-category ratios (of max_context_size)
    _system_ratio: float = 0.15
    _tool_ratio: float = 0.20
    _conversation_ratio: float = 0.45
    _summary_ratio: float = 0.20

    def __post_init__(self) -> None:
        pass

    @classmethod
    def from_config(cls, config: CompressionConfig) -> TokenBudget:
        return cls(
            max_context_size=config.max_context_size,
            _system_ratio=config.system_prompt_budget_ratio,
            _tool_ratio=config.tool_description_budget_ratio,
            _conversation_ratio=config.conversation_budget_ratio,
            _summary_ratio=config.summary_budget_ratio,
        )

    @property
    def total_used(self) -> int:
        return self.system_prompt_tokens + self.tool_description_tokens + self.conversation_tokens + self.summary_tokens

    @property
    def remaining(self) -> int:
        return max(0, self.max_context_size - self.total_used)

    @property
    def utilization_ratio(self) -> float:
        if self.max_context_size == 0:
            return 1.0
        return self.total_used / self.max_context_size

    @property
    def system_budget(self) -> int:
        return int(self.max_context_size * self._system_ratio)

    @property
    def tool_budget(self) -> int:
        return int(self.max_context_size * self._tool_ratio)

    @property
    def conversation_budget(self) -> int:
        return int(self.max_context_size * self._conversation_ratio)

    @property
    def summary_budget(self) -> int:
        return int(self.max_context_size * self._summary_ratio)

    def needs_aggressive_compress(self) -> bool:
        """True when total usage exceeds the hard max_context_size."""
        return self.total_used > self.max_context_size

    def needs_normal_compress(self, trigger_ratio: float = 0.80) -> bool:
        """True when utilization exceeds the configurable trigger ratio."""
        return self.utilization_ratio >= trigger_ratio


# ---------------------------------------------------------------------------
# Key event extraction (rule-based)
# ---------------------------------------------------------------------------

_EVENT_PATTERNS = [
    re.compile(r"(?:tool_call|tool\.call|调用工具)[:\s]*([^\n]+)", re.IGNORECASE),
    re.compile(r"(?:decision|决定|决策)[:\s]*([^\n]+)", re.IGNORECASE),
    re.compile(r"(?:result|结果|产出)[:\s]*([^\n]{1,200})", re.IGNORECASE),
    re.compile(r"(?:action|行动)[:\s]*([^\n]{1,200})", re.IGNORECASE),
    re.compile(r"(?:conclusion|结论)[:\s]*([^\n]{1,200})", re.IGNORECASE),
]


def _extract_events_from_text(text: str) -> list[str]:
    """Extract key event phrases from a message's content."""
    events: list[str] = []
    for pattern in _EVENT_PATTERNS:
        matches = pattern.findall(text)
        for m in matches[:2]:  # at most 2 per pattern
            cleaned = m.strip().rstrip("。,.!；;")
            if len(cleaned) > 5 and cleaned not in events:
                events.append(cleaned)
    return events


# ---------------------------------------------------------------------------
# ContextCompressor
# ---------------------------------------------------------------------------


class ContextCompressor:
    """Compresses conversation history while preventing task resumption."""

    def __init__(self, config: CompressionConfig | None = None) -> None:
        self.config = config or load_compression_config()
        self._aux_model = None  # set externally if an aux model is available

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compress(
        self,
        messages: list[Any],
        *,
        system_prompt_tokens: int = 0,
        tool_description_tokens: int = 0,
    ) -> tuple[list[Any], bool]:
        """Main compression entry point.

        Returns (compressed_messages, was_compressed).
        If no compression is needed, returns the original list unchanged.
        """
        budget = TokenBudget.from_config(self.config)
        budget.system_prompt_tokens = system_prompt_tokens
        budget.tool_description_tokens = tool_description_tokens

        # Estimate current conversation tokens
        conv_tokens = 0
        for msg in messages:
            conv_tokens += _estimate_text_tokens(_message_text(msg)) + 8  # overhead per message
        budget.conversation_tokens = conv_tokens

        if not budget.needs_normal_compress(self.config.compression_trigger_ratio):
            return messages, False

        # Determine cutoff: keep last N messages verbatim
        keep_recent = self.config.keep_recent_messages
        cutoff_index = max(0, len(messages) - keep_recent)

        if cutoff_index <= 0:
            # Nothing to compress; just truncate individual oversized messages
            return self._truncate_oversized(messages, budget), True

        older_messages = messages[:cutoff_index]
        recent_messages = messages[cutoff_index:]

        # Extract key events and build summary
        events = self._extract_key_events(older_messages)
        summary_text = self._build_summary_template(events)

        # Build compressed message list
        compressed = self._assemble_compressed(messages, older_messages, recent_messages, summary_text, budget)
        return compressed, True

    def compress_if_needed(
        self,
        messages: list[Any],
        *,
        system_prompt_tokens: int = 0,
        tool_description_tokens: int = 0,
    ) -> tuple[list[Any], bool]:
        """Convenience wrapper matching session.py integration signature."""
        return self.compress(messages, system_prompt_tokens=system_prompt_tokens, tool_description_tokens=tool_description_tokens)

    # ------------------------------------------------------------------
    # Internal compression logic
    # ------------------------------------------------------------------

    def _summarize_older_messages(self, messages: list[Any], cutoff_index: int) -> str:
        """Summarize messages before the cutoff index."""
        events = self._extract_key_events(messages[:cutoff_index])
        return self._build_summary_template(events)

    def _extract_key_events(self, messages: list[Any]) -> list[dict[str, Any]]:
        """Extract key decisions/actions from conversation messages.

        Returns a list of event dicts with timestamp, role, action, and result.
        """
        events: list[dict[str, Any]] = []
        for msg in messages:
            text = _message_text(msg)
            if not text.strip():
                continue
            role = _message_role(msg)

            # Extract event phrases from content
            phrases = _extract_events_from_text(text)

            # If no structured events found, create a generic summary line
            if not phrases:
                # Take first meaningful sentence (up to 150 chars)
                cleaned = text.strip()[:150]
                if len(cleaned) >= 10:
                    phrases = [cleaned]

            for phrase in phrases:
                event_ts = self._guess_timestamp_from_index(len(events))
                events.append(
                    {
                        "timestamp": event_ts,
                        "role": role,
                        "action": phrase,
                        "result": "",  # filled below if we can infer it
                    }
                )

        return events

    def _build_summary_template(self, events: list[dict[str, Any]]) -> str:
        """Build a structured summary from extracted events.

        Each event is prefixed with the anti-hijack marker and wrapped in
        strong directives preventing task resumption.
        """
        if not events:
            return ""

        lines = [self.config.anti_hijack_system_instruction]
        lines.append(self.config.anti_hijack_chinese_directive)
        lines.append("")
        lines.append("## Compressed Conversation Summary")
        lines.append("")

        for event in events:
            prefix = self.config.anti_hijack_prefix
            role_label = "agent" if event["role"] == "assistant" else ("user" if event["role"] == "human" else event["role"])
            action = event.get("action", "").strip()
            result = event.get("result", "").strip()

            line = f"{prefix} [{event['timestamp']}] {role_label}:{action}"
            if result:
                line += f" \u2192 {result}"  # arrow character
            lines.append(line)

        return "\n".join(lines)

    def _assemble_compressed(
        self,
        all_messages: list[Any],
        older_messages: list[Any],
        recent_messages: list[Any],
        summary_text: str,
        budget: TokenBudget,
    ) -> list[Any]:
        """Assemble the final compressed message list.

        Structure:
          [system_prompt] + [anti-hijack summary] + [recent verbatim messages]
        """
        # Estimate summary tokens
        summary_tokens = _estimate_text_tokens(summary_text) + 8
        budget.summary_tokens = summary_tokens

        # Check if we need to truncate the summary to fit budget
        available_for_summary = max(0, budget.summary_budget - summary_tokens)
        if available_for_summary < 0:
            # Summary exceeds its own budget; truncate aggressively
            summary_text = self._truncate_to_token_limit(summary_text, budget.summary_budget)

        # Build the compressed messages
        compressed: list[Any] = []

        # Keep system message(s) from original
        for msg in all_messages:
            if _message_role(msg) == "system":
                compressed.append(msg)

        # Insert anti-hijack summary as a system-level instruction
        if summary_text.strip():
            summary_msg = {"role": "system", "content": summary_text}
            compressed.append(summary_msg)

        # Append recent messages verbatim
        compressed.extend(recent_messages)

        return compressed

    def _truncate_oversized(self, messages: list[Any], budget: TokenBudget) -> list[Any]:
        """Truncate individual oversized messages to fit within budget."""
        result = []
        for msg in messages:
            text = _message_text(msg)
            role = _message_role(msg)

            if role == "system":
                max_tok = budget.system_budget
            elif role == "tool":
                max_tok = budget.tool_budget
            else:
                max_tok = budget.conversation_budget

            truncated = self._truncate_to_token_limit(text, max_tok)
            if isinstance(msg, dict):
                result.append({**msg, "content": truncated})
            else:
                # Copy message with updated content (handle BaseMessage)
                try:
                    result.append(msg.model_copy(update={"content": truncated}))
                except Exception:
                    result.append(msg)
        return result

    def _truncate_to_token_limit(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within a token limit using char-based estimation."""
        if _estimate_text_tokens(text) <= max_tokens:
            return text
        # Keep 70% head + marker + 30% tail for context preservation
        head_chars = max(int(max_tokens * self.config.chars_per_token_ascii * 0.7), 1)
        tail_chars = max(int(max_tokens * self.config.chars_per_token_ascii * 0.3), 1)
        marker = "\n\n[system: session is compressing and continuing to act]\n\n"
        return text[:head_chars].rstrip() + marker + text[-tail_chars:].lstrip()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _guess_timestamp_from_index(event_count: int) -> str:
        """Generate a pseudo-timestamp for events (relative ordering)."""
        return f"step-{event_count + 1}"


__all__ = ["ContextCompressor", "TokenBudget"]
