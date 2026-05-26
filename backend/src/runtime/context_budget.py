"""Shared context-budget primitives for model calls and session compaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import BaseMessage, SystemMessage

SYSTEM_SESSION_CONTINUE_PROMPT = "[system：session is compressing and continuing to act]"
DEFAULT_CHARS_PER_TOKEN = 4
DEFAULT_TOKEN_OVERHEAD = 8


@dataclass(frozen=True)
class MessageTokenLimits:
    tool: int = 1_200
    human: int = 5_000
    ai: int = 4_000
    default: int = 4_000


@dataclass(frozen=True)
class MessageBudgetResult:
    messages: list[Any]
    original_tokens: int
    final_tokens: int
    dropped_count: int = 0
    changed: bool = False


def estimate_text_tokens(text: str, *, minimum: int = 0) -> int:
    """Estimate tokens without loading a tokenizer.

    ASCII text is roughly 4 chars/token; CJK and symbols are costlier, so they
    use a 1.5 chars/token heuristic. This keeps all context guards aligned.
    """
    if not text:
        return minimum
    ascii_count = sum(1 for char in text if ord(char) < 128)
    non_ascii = len(text) - ascii_count
    return max(minimum, int(ascii_count / 4 + non_ascii / 1.5))


def message_content_text(message: Any) -> str:
    content = getattr(message, "content", message.get("content") if isinstance(message, dict) else "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                parts.append(text if isinstance(text, str) else str(item))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def message_type(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("type") or message.get("role") or "")
    return str(getattr(message, "type", "") or getattr(message, "role", ""))


def estimate_message_tokens(messages: list[Any], *, overhead: int = DEFAULT_TOKEN_OVERHEAD) -> int:
    total = 0
    for message in messages:
        total += estimate_text_tokens(message_content_text(message), minimum=1) + overhead
    return total


def copy_message_with_content(message: Any, content: str) -> Any:
    if isinstance(message, BaseMessage):
        return message.model_copy(update={"content": content})
    if isinstance(message, dict):
        return {**message, "content": content}
    return message


def trim_text_to_token_budget(
    text: str,
    max_tokens: int,
    *,
    marker: str = SYSTEM_SESSION_CONTINUE_PROMPT,
) -> str:
    if estimate_text_tokens(text, minimum=0) <= max_tokens:
        return text
    max_chars = max(1, max_tokens * DEFAULT_CHARS_PER_TOKEN)
    head_chars = max(int(max_chars * 0.7), 1)
    tail_chars = max(max_chars - head_chars, 0)
    tail = text[-tail_chars:] if tail_chars > 0 else ""
    return text[:head_chars].rstrip() + f"\n\n{marker}\n\n" + tail.lstrip()


def trim_message_to_token_budget(message: Any, max_tokens: int) -> Any:
    text = message_content_text(message)
    next_text = trim_text_to_token_budget(text, max_tokens)
    if next_text == text:
        return message
    return copy_message_with_content(message, next_text)


def max_tokens_for_message(message: Any, limits: MessageTokenLimits | None = None) -> int:
    limits = limits or MessageTokenLimits()
    msg_type = message_type(message)
    if msg_type == "tool":
        return limits.tool
    if msg_type == "human":
        return limits.human
    if msg_type == "ai":
        return limits.ai
    return limits.default


def truncate_oversized_messages(
    messages: list[Any],
    *,
    limits: MessageTokenLimits | None = None,
) -> tuple[list[Any], bool]:
    changed = False
    out: list[Any] = []
    for message in messages:
        text = message_content_text(message)
        next_text = trim_text_to_token_budget(text, max_tokens_for_message(message, limits))
        if next_text != text:
            changed = True
            out.append(copy_message_with_content(message, next_text))
        else:
            out.append(message)
    return out, changed


def _append_message_within_budget(
    selected: list[tuple[int, Any]],
    *,
    index: int,
    message: Any,
    budget_tokens: int,
    current_tokens: int,
) -> int:
    message_tokens = estimate_message_tokens([message])
    if message_tokens <= max(0, budget_tokens - current_tokens):
        selected.append((index, message))
        return current_tokens + message_tokens
    if not selected and budget_tokens > 0:
        selected.append((index, trim_message_to_token_budget(message, budget_tokens)))
        return estimate_message_tokens([selected[-1][1]])
    return current_tokens


def select_system_messages_to_budget(system_messages: list[Any], budget_tokens: int) -> list[Any]:
    if not system_messages or budget_tokens <= 0:
        return []

    first_budget = max(1, budget_tokens // 3)
    selected: list[tuple[int, Any]] = []
    used_tokens = _append_message_within_budget(
        selected,
        index=0,
        message=system_messages[0],
        budget_tokens=first_budget,
        current_tokens=0,
    )
    remaining_budget = max(1, budget_tokens - used_tokens)
    recent: list[tuple[int, Any]] = []
    recent_tokens = 0
    seen_content: set[str] = set()
    for offset, message in reversed(list(enumerate(system_messages[1:], start=1))):
        content_key = message_content_text(message)[:500]
        if content_key in seen_content:
            continue
        seen_content.add(content_key)
        before = recent_tokens
        recent_tokens = _append_message_within_budget(
            recent,
            index=offset,
            message=message,
            budget_tokens=remaining_budget,
            current_tokens=recent_tokens,
        )
        if recent_tokens == before and recent:
            continue
        if recent_tokens >= remaining_budget:
            break

    return [message for _, message in sorted([*selected, *recent], key=lambda item: item[0])]


def trim_messages_to_budget(
    messages: list[Any],
    max_tokens: int,
    *,
    keep_recent_messages: int | None = 20,
    system_budget_ratio: float = 0.35,
    force: bool = False,
) -> MessageBudgetResult:
    original_tokens = estimate_message_tokens(messages)
    target_tokens = max(1, int(max_tokens))
    if original_tokens <= target_tokens and not force:
        return MessageBudgetResult(
            messages=messages,
            original_tokens=original_tokens,
            final_tokens=original_tokens,
        )

    system_messages = [message for message in messages if message_type(message) == "system"]
    non_system_messages = [message for message in messages if message_type(message) != "system"]
    notice = SystemMessage(content=SYSTEM_SESSION_CONTINUE_PROMPT)
    notice_tokens = estimate_message_tokens([notice])
    system_budget = max(
        1,
        min(
            int(target_tokens * system_budget_ratio),
            max(1, target_tokens - notice_tokens - 1),
        ),
    )
    kept_system_messages = select_system_messages_to_budget(system_messages, system_budget)
    reserved_tokens = estimate_message_tokens([*kept_system_messages, notice])
    recent_budget = max(1, target_tokens - reserved_tokens)
    recent: list[Any] = []
    recent_tokens = 0

    for message in reversed(non_system_messages):
        if keep_recent_messages is not None and len(recent) >= keep_recent_messages:
            break
        message_tokens = estimate_message_tokens([message])
        if recent and recent_tokens + message_tokens > recent_budget:
            continue
        if not recent and message_tokens > recent_budget:
            recent.append(trim_message_to_token_budget(message, recent_budget))
            break
        recent.append(message)
        recent_tokens += message_tokens

    recent.reverse()
    trimmed = [*kept_system_messages, notice, *recent]
    final_tokens = estimate_message_tokens(trimmed)
    dropped_count = max(0, len(messages) - len(kept_system_messages) - len(recent))
    return MessageBudgetResult(
        messages=trimmed,
        original_tokens=original_tokens,
        final_tokens=final_tokens,
        dropped_count=dropped_count,
        changed=True,
    )
