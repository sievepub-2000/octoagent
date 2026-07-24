"""Single source of truth for run termination.

Inspired by Claude Code and Codex: the model's structural intent
(tool_calls vs no tool_calls) determines whether a run is finished,
not text keyword heuristics on the final message.

Three terminal states:
  - "completed":  model produced visible text without calling tools.
  - "active":     model still wants control (it issued tool_calls).
  - "incomplete": model was cut off, errored out, or only announced future work.

The classifier is deliberately small and deterministic. It is the only
place in the codebase that decides "did the long-running task finish?".
All other code (run_records, task_state_middleware, frontend
auto-continue) consumes its output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from typing import Any, Literal

from langchain_core.messages import AIMessage

RunStatus = Literal["completed", "active", "incomplete"]

_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")

# Sentinel reasons for the incomplete state, used by callers to drive UX.
REASON_EMPTY_OUTPUT = "assistant produced no user-visible final answer"
REASON_PENDING_TOOLS = "assistant ended with pending tool calls"
REASON_CONTINUATION_ANNOUNCEMENT = "assistant ended after announcing an action"
REASON_RUNTIME_ERROR = "runtime/tool error interrupted the task"
REASON_TOOL_FAILURES = "tool failures interrupted the task"
REASON_TOOL_RESULTS_WITHOUT_FINAL = "assistant ended after tool results without final answer"


@dataclass(frozen=True)
class TerminationOutcome:
    """Result of classifying a run."""

    status: RunStatus
    reason: str | None
    current_step: str
    next_action: str


def _visible_text(message: Any) -> str:
    """Return user-visible text from a message, stripping <think> and tags."""
    content = getattr(message, "content", "") if message is not None else ""
    if isinstance(content, list):
        content = " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    text = str(content or "")
    text = _THINK_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _has_tool_calls(message: Any) -> bool:
    return bool(getattr(message, "tool_calls", None))


def _tool_call_ids(message: Any) -> set[str]:
    ids: set[str] = set()
    for call in getattr(message, "tool_calls", None) or []:
        value = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
        if value:
            ids.add(str(value))
    return ids


def _tool_result_ids(messages: list[Any]) -> set[str]:
    ids: set[str] = set()
    for message in messages:
        value = getattr(message, "tool_call_id", None)
        if value:
            ids.add(str(value))
            continue
        if isinstance(message, dict) and message.get("tool_call_id"):
            ids.add(str(message["tool_call_id"]))
    return ids


# Continuation announcement: model said "let me do X" but did not call a tool.
# This is a weak-model failure mode (Qwen flash etc.) where the model narrates
# instead of acting. The detection is narrow on purpose:
#   - short message (<=360 chars), AND
#   - contains an announcement lead like "now let me" / "\u73b0\u5728\u8ba9\u6211", AND
#   - contains an action verb the model intended to perform, AND
#   - does NOT contain a completion negator like "summary" / "\u5df2\u5b8c\u6210".
_CONTINUATION_LEADS = (
    "\u73b0\u5728\u8ba9\u6211",  # \u73b0\u5728\u8ba9\u6211
    "\u6211\u6765",  # \u6211\u6765
    "\u6211\u5c06",  # \u6211\u5c06
    "\u63a5\u4e0b\u6765\u6211\u4f1a",  # \u63a5\u4e0b\u6765\u6211\u4f1a
    "\u63a5\u4e0b\u6765",  # \u63a5\u4e0b\u6765
    "\u9996\u5148\uff0c\u8ba9\u6211",  # \u9996\u5148\uff0c\u8ba9\u6211
    "\u9996\u5148\u8ba9\u6211",  # \u9996\u5148\u8ba9\u6211
    "\u8ba9\u6211",  # \u8ba9\u6211
    "\u6211\u8981",  # \u6211\u8981
    "\u6211\u4f1a",  # \u6211\u4f1a
    "let me",
    "i will",
    "i am going",
    "now let me",
)
_CONTINUATION_VERBS = (
    "\u68c0\u67e5",  # \u68c0\u67e5
    "\u67e5\u770b",  # \u67e5\u770b
    "\u8bfb\u53d6",  # \u8bfb\u53d6
    "\u641c\u7d22",  # \u641c\u7d22
    "\u67e5\u8be2",  # \u67e5\u8be2
    "\u67e5\u627e",  # \u67e5\u627e
    "\u8c03\u7814",  # \u8c03\u7814
    "\u8c03\u67e5",  # \u8c03\u67e5
    "\u6df1\u5165",  # \u6df1\u5165
    "\u8fd0\u884c",  # \u8fd0\u884c
    "\u5206\u6790",  # \u5206\u6790
    "\u6392\u67e5",  # \u6392\u67e5
    "\u5b9e\u73b0",  # \u5b9e\u73b0
    "\u9a8c\u8bc1",  # \u9a8c\u8bc1
    "\u7ee7\u7eed",  # \u7ee7\u7eed
    "inspect",
    "check",
    "read",
    "search",
    "look up",
    "research",
    "investigate",
    "run",
    "analy",
    "implement",
    "verify",
    "continue",
)
_COMPLETION_NEGATORS = (
    "\u5df2\u5b8c\u6210",  # \u5df2\u5b8c\u6210
    "\u5b8c\u6210\u4e86",  # \u5b8c\u6210\u4e86
    "\u4fee\u590d\u5b8c\u6210",  # \u4fee\u590d\u5b8c\u6210
    "\u9a8c\u8bc1\u901a\u8fc7",  # \u9a8c\u8bc1\u901a\u8fc7
    "\u603b\u7ed3",  # \u603b\u7ed3
    "\u7ed3\u8bba",  # \u7ed3\u8bba
    "\u7ed3\u679c",  # \u7ed3\u679c
    "done",
    "completed",
    "summary",
    "result",
    "in summary",
)
_RUNTIME_FAIL_MARKERS = (
    "\u6211\u5728\u6267\u884c\u8fd9\u8f6e\u4efb\u52a1\u65f6\u9047\u5230\u4e86\u8fd0\u884c\u65f6\u9519\u8bef",
    "\u9519\u8bef\u7c7b\u578b\uff1anormalizedmodelerror",
    "cannot have 2 or more assistant messages at the end of the list",
)
_TOOL_FAIL_MARKERS = (
    "\u5de5\u5177\u8c03\u7528\u8fde\u7eed\u5931\u8d25",
    "tool failures",
    "recovery policy",
)

# Explicit "I am continuing" phrases. When any of these appears the message is
# a mid-task progress report, not a final answer -- even if it also contains
# completion words like "completed" or "done" that refer to a sub-step.
_STRONG_CONTINUATION_PHRASES = (
    "will continue",
    "going to continue",
    "i'll continue",
    "and will continue",
    "next i will",
    "next, i",
    "still need to",
    "\u63a5\u4e0b\u6765",  # \u63a5\u4e0b\u6765
    "\u8ba9\u6211\u7ee7\u7eed",  # \u8ba9\u6211\u7ee7\u7eed
    "\u6211\u4f1a\u7ee7\u7eed",  # \u6211\u4f1a\u7ee7\u7eed
    "\u4e0b\u4e00\u6b65",  # \u4e0b\u4e00\u6b65
)


def _is_continuation_announcement(text: str) -> bool:
    """Detect short transitional messages where the model narrates instead of acting."""
    stripped = text.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    # Embedded raw tool-call markup -> the model thought it was calling a tool.
    if "<tool_call" in lowered or "<function=" in lowered:
        return True
    # Strong continuation phrases are decisive regardless of message length or
    # the presence of "completed/done" wording for sub-steps.
    if any(phrase in lowered for phrase in _STRONG_CONTINUATION_PHRASES):
        return True
    if len(stripped) > 360:
        return False
    if not any(lead in lowered for lead in _CONTINUATION_LEADS):
        return False
    if not any(verb in lowered for verb in _CONTINUATION_VERBS):
        return False
    if stripped.endswith((":", "\uff1a")):
        return True
    if any(neg in lowered for neg in _COMPLETION_NEGATORS):
        return False
    return True


def _is_runtime_failure(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _RUNTIME_FAIL_MARKERS)


def _is_tool_failure_final(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _TOOL_FAIL_MARKERS)


def classify_run_outcome(
    messages: list[Any],
    *,
    tool_errors: list[str] | None = None,
) -> TerminationOutcome:
    """Classify the outcome of an agent run from the message history alone.

    Trust order (strongest signal first):

    1. No AI message at all -> active (run has not produced a turn yet).
    2. Last AI has pending tool_calls -> active (ToolNode runs next).
    3. Last AI has no visible text -> incomplete (empty output).
    4. Last AI text is a continuation announcement -> incomplete.
    5. Last AI text matches a runtime failure marker -> incomplete.
    6. Last AI text matches a tool failure marker, or tool errors are pending
       with empty AI text -> incomplete.
    7. Otherwise (clean visible text + no pending tool calls) -> completed.

    The classifier never uses character-length or keyword "substantive-enough"
    heuristics to decide completion. If the model stopped its turn without
    calling a tool, it considers the response final. Trust that signal.
    """
    last_ai_index: int | None = None
    last_ai = None
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, AIMessage) or getattr(message, "type", "") == "ai":
            last_ai_index = index
            last_ai = message
            break
    if last_ai is None:
        return TerminationOutcome(
            status="active",
            reason=None,
            current_step="agent has not produced a turn yet",
            next_action="wait for the model to respond",
        )

    if _has_tool_calls(last_ai):
        expected_tool_ids = _tool_call_ids(last_ai)
        resolved_tool_ids = _tool_result_ids(messages[(last_ai_index or 0) + 1 :])
        if expected_tool_ids and expected_tool_ids.issubset(resolved_tool_ids):
            return TerminationOutcome(
                status="incomplete",
                reason=REASON_TOOL_RESULTS_WITHOUT_FINAL,
                current_step=REASON_TOOL_RESULTS_WITHOUT_FINAL,
                next_action="resume after the completed tool results and produce the missing final answer",
            )
        return TerminationOutcome(
            status="active",
            reason=REASON_PENDING_TOOLS,
            current_step="assistant invoked tools",
            next_action="execute pending tool calls",
        )

    text = _visible_text(last_ai)
    if not text:
        return TerminationOutcome(
            status="incomplete",
            reason=REASON_EMPTY_OUTPUT,
            current_step=REASON_EMPTY_OUTPUT,
            next_action="resume with the latest user goal and produce a concise final answer",
        )

    if _is_continuation_announcement(text):
        snippet = text[:500]
        return TerminationOutcome(
            status="incomplete",
            reason=REASON_CONTINUATION_ANNOUNCEMENT,
            current_step=REASON_CONTINUATION_ANNOUNCEMENT,
            next_action=f"Continue the announced action: {snippet}",
        )

    if _is_runtime_failure(text):
        return TerminationOutcome(
            status="incomplete",
            reason=REASON_RUNTIME_ERROR,
            current_step=REASON_RUNTIME_ERROR,
            next_action="retry from the persistent task state with compact context and a different tool path",
        )

    errors_present = bool(tool_errors)
    if _is_tool_failure_final(text) or (errors_present and not text):
        return TerminationOutcome(
            status="incomplete",
            reason=REASON_TOOL_FAILURES,
            current_step=REASON_TOOL_FAILURES,
            next_action="switch source/tool path and continue from the last successful evidence",
        )

    return TerminationOutcome(
        status="completed",
        reason=None,
        current_step="assistant delivered a final answer",
        next_action="none",
    )


def is_continuation_announcement(text: str) -> bool:
    """Public alias for the continuation-announcement detector.

    Other middleware may tag mid-task narration
    messages for downstream evolution analysis. They share the exact same
    vocabulary as ``classify_run_outcome``; routing them through this single
    entry point keeps the detector definition in one place.
    """
    return _is_continuation_announcement(text)


__all__ = [
    "REASON_CONTINUATION_ANNOUNCEMENT",
    "REASON_EMPTY_OUTPUT",
    "REASON_PENDING_TOOLS",
    "REASON_RUNTIME_ERROR",
    "REASON_TOOL_FAILURES",
    "REASON_TOOL_RESULTS_WITHOUT_FINAL",
    "RunStatus",
    "TerminationOutcome",
    "classify_run_outcome",
    "is_continuation_announcement",
    "_visible_text",
]
