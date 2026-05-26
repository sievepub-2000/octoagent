"""Session compaction integration for the agent message pipeline.

Provides a helper that compacts conversation history before forwarding
to the agent runtime, transparently reducing context window usage.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def compact_message_history(
    messages: list[dict[str, Any]],
    *,
    max_context_tokens: int = 32_000,
    keep_recent_turns: int = 6,
    strategy: str = "hybrid",
    llm_summarize_fn=None,
) -> list[dict[str, Any]]:
    """Apply session compaction to a list of message dicts.

    Returns a (potentially shorter) list of message dicts suitable for
    forwarding to the LLM provider.
    """
    try:
        from src.storage.session_compaction.compactor import (
            CompactionConfig,
            Message,
            SessionCompactor,
        )
    except ImportError:
        logger.debug("session_compaction module not available, skipping compaction")
        return messages

    if len(messages) < keep_recent_turns * 2:
        return messages

    config = CompactionConfig(
        enabled=True,
        max_context_tokens=max_context_tokens,
        keep_recent_turns=keep_recent_turns,
        strategy=strategy,
    )
    compactor = SessionCompactor(config=config, llm_summarize_fn=llm_summarize_fn)

    wrapped = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        wrapped.append(
            Message(
                role=role,
                content=content if isinstance(content, str) else str(content),
                is_system=role == "system",
                is_tool_boundary=role in ("tool", "function"),
            )
        )

    result = compactor.compact(wrapped)

    compacted: list[dict[str, Any]] = []
    for m in result.messages:
        compacted.append({"role": m.role, "content": m.content})

    if result.tokens_saved > 0:
        logger.info(
            "Session compaction: %d→%d messages, saved ~%d tokens",
            len(messages),
            len(compacted),
            result.tokens_saved,
        )

    return compacted
