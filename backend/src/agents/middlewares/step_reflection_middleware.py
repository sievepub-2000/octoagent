"""Step-cycle reflection middleware.

Implements the **Execute → Check → Decide** discipline that a senior engineer
applies between actions:

  1. After a batch of tool calls finishes (or at most every ``every_n`` such
     batches) we inject a hidden ``<step_review>`` system message that asks
     the model — in its **own next turn** — to:
       a. summarise what it just tried (one line);
       b. extract the observable outcome (≤ 3 factual bullets);
       c. classify the outcome as SUCCESS / PARTIAL / FAILED;
       d. branch:
          - SUCCESS  → state the next concrete step or finalise the task;
          - PARTIAL  → list what is known vs still missing, then the next step;
          - FAILED   → name the *specific* failure mode, give a one-line root
            cause hypothesis, and propose a different (not retry-as-is) fix.

  2. The middleware is fingerprint-throttled so it doesn't re-emit identical
     reviews for the same observed tool window (same set of tool signatures
     + same set of output signatures). It is purely heuristic — no LLM call —
     and costs sub-millisecond per turn.

Why this is distinct from ``CriticMiddleware`` and
``ProgressStallMiddleware``:

  * ``CriticMiddleware`` only acts when the model violates the active
    ``goal_contract`` (forbidden actions, missing success criteria).
  * ``ProgressStallMiddleware`` only acts when the agent is **stuck**
    (duplicate calls, zero-information-gain outputs).
  * ``StepReflectionMiddleware`` is the **steady-state cadence checkpoint**:
    it fires periodically even when things are going well, so the model
    explicitly verifies its incremental output before moving on. This builds
    a coherent Execute / Check / Continue-or-Correct workflow that mirrors
    Plan-Reflect-Act patterns proven in long-horizon agent research.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime
from src.utils.messages import latest_human_index as _latest_human_index

logger = logging.getLogger(__name__)

_DEFAULT_CADENCE = int(os.getenv("OCTO_STEP_REVIEW_EVERY_N", "3"))
_MAX_REVIEWS_PER_TURN = int(os.getenv("OCTO_STEP_REVIEW_MAX_PER_TURN", "8"))
_MARKER = '<step_review origin="step_reflection_middleware"'


def _content_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return " ".join(parts)
    return str(content or "")




def _research_closure_active(state: AgentState) -> bool:
    runtime_state = state.get("runtime") or {}
    closure = runtime_state.get("research_closure") if isinstance(runtime_state, dict) else None
    return isinstance(closure, dict) and closure.get("status") == "must_finalize"


def _ends_on_tool_batch_boundary(messages: list[Any]) -> bool:
    """True iff the last message is a ToolMessage AND it closes a complete
    batch (the preceding AI message's tool_calls all have matching results)."""
    if not messages or not isinstance(messages[-1], ToolMessage):
        return False
    # Find the closest prior AIMessage with tool_calls.
    ai_index: int | None = None
    for index in range(len(messages) - 1, -1, -1):
        msg = messages[index]
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            ai_index = index
            break
        if isinstance(msg, AIMessage):
            # An AIMessage with no tool_calls breaks the batch chain.
            return False
    if ai_index is None:
        return False
    expected = {call.get("id") for call in (messages[ai_index].tool_calls or []) if call.get("id")}
    if not expected:
        return False
    seen = {getattr(m, "tool_call_id", None) for m in messages[ai_index + 1 :] if isinstance(m, ToolMessage)}
    return expected.issubset(seen)


def _count_completed_tool_batches(messages: list[Any]) -> int:
    """How many AI tool-call batches have been fully resolved since the last
    human turn."""
    start = _latest_human_index(messages) + 1
    scoped = messages[start:]
    batches = 0
    for index, msg in enumerate(scoped):
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            expected_ids = {call.get("id") for call in msg.tool_calls or [] if call.get("id")}
            if not expected_ids:
                continue
            resolved_ids = {getattr(m, "tool_call_id", None) for m in scoped[index + 1 :] if isinstance(m, ToolMessage)}
            if expected_ids.issubset(resolved_ids):
                batches += 1
    return batches


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else (text[: limit - 1].rstrip() + "…")


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:10]


def _window_fingerprint(messages: list[Any]) -> str:
    """Fingerprint of (latest tool-call signatures, latest tool outputs) so we
    don't re-emit a review for an identical window."""
    start = _latest_human_index(messages) + 1
    scoped = messages[start:]
    tool_sigs: list[str] = []
    out_sigs: list[str] = []
    for msg in scoped[-12:]:
        if isinstance(msg, AIMessage):
            for call in msg.tool_calls or []:
                name = str(call.get("name") or "?")
                try:
                    args = json.dumps(call.get("args"), ensure_ascii=False, sort_keys=True, default=str)
                except TypeError:
                    args = str(call.get("args"))
                tool_sigs.append(f"{name}:{args[:120]}")
        elif isinstance(msg, ToolMessage):
            out_sigs.append(_short(_content_text(msg), 120))
    payload = json.dumps({"tools": tool_sigs, "outs": out_sigs}, ensure_ascii=False, sort_keys=True)
    return _hash(payload)


def _summarise_recent_actions(messages: list[Any]) -> tuple[list[str], list[str]]:
    """Return (action_lines, observation_lines) for the latest batch."""
    start = _latest_human_index(messages) + 1
    scoped = messages[start:]
    # Walk back to the last AI tool-call boundary
    ai_index: int | None = None
    for index in range(len(scoped) - 1, -1, -1):
        if isinstance(scoped[index], AIMessage) and getattr(scoped[index], "tool_calls", None):
            ai_index = index
            break
    if ai_index is None:
        return [], []
    ai_msg = scoped[ai_index]
    actions: list[str] = []
    for call in ai_msg.tool_calls or []:
        name = str(call.get("name") or "?")
        try:
            args = json.dumps(call.get("args"), ensure_ascii=False)
        except TypeError:
            args = str(call.get("args"))
        actions.append(f"  - {name} {_short(args, 200)}")
    observations: list[str] = []
    for msg in scoped[ai_index + 1 :]:
        if isinstance(msg, ToolMessage):
            observations.append(f"  - {getattr(msg, 'name', None) or '?'}: {_short(_content_text(msg), 180)}")
    return actions, observations


def _build_review_message(messages: list[Any], fingerprint: str) -> SystemMessage:
    actions, observations = _summarise_recent_actions(messages)
    body = "\n".join(
        [
            f'{_MARKER} fingerprint="{fingerprint}">',
            "你刚刚完成了一组工具调用。下一条助理消息必须先做阶段性自检，再决定是否继续。",
            "",
            "刚刚执行的动作：",
            *(actions or ["  - (无)"]),
            "",
            "工具返回的可观察事实：",
            *(observations or ["  - (无)"]),
            "",
            "在下一条助理消息开头，严格按以下结构输出 阶段性复盘 段（≤180 字），随后再继续后续动作或最终回答：",
            "1) 我刚做了什么：1 行（包括用了哪些工具和URL）；",
            "2) 观察到的关键事实：≤3 条要点（只用上面的事实，不要编造）；",
            "3) 结果分类（必填一个）：SUCCESS / PARTIAL / FAILED；",
            "4) 分支：",
            "   - SUCCESS → 写出下一步具体动作；如果用户原始任务已经达成，直接给最终答案，不再调工具。",
            "   - PARTIAL → 列出已知 vs 还缺什么，并给出能闭合缺口的、明显不同的下一步。",
            "   - FAILED  → 严格执行以下步骤：",
            "     a) 记录具体错误现象和错误消息",
            "     b) 分析根本原因（不是简单的'操作失败'）",
            "     c) 制定与上次完全不同的修正方案（换工具/换参数/换路径/换思路）",
            "     d) 禁止以相同参数重试；禁止因单次失败就放弃任务",
            "     e) 如果已尝试2种方案仍失败，考虑是否需要换一个完全不同的方向",
            "5) 复盘段结束后再继续行动；如果决定 FAILED 但仍要重试，必须先在复盘里说明这次和上次的不同点。",
            "6) 去重检查：检查本轮是否有重复的URL抓取或工具调用。如果有，后续不再重复调用。",
            "7) 引用检查：如果任务要求提供source URLs，确认已收集的URL数量是否满足要求。",
            "</step_review>",
        ]
    )
    return SystemMessage(content=body)


class StepReflectionMiddleware(AgentMiddleware[AgentState]):
    """Inject a cadence-based Execute / Check / Continue-or-Correct prompt."""

    def __init__(self, *, every_n: int | None = None) -> None:
        super().__init__()
        self.every_n = max(1, every_n if every_n is not None else _DEFAULT_CADENCE)

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_inject(state)

    @override
    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_inject(state)

    def _maybe_inject(self, state: AgentState) -> dict | None:
        if _research_closure_active(state):
            return None
        messages = list(state.get("messages", []))
        if not messages:
            return None
        if not _ends_on_tool_batch_boundary(messages):
            return None
        batches = _count_completed_tool_batches(messages)
        # Fire on the every_n-th completed batch (1, every_n+1, 2*every_n+1, …).
        if batches <= 0 or batches % self.every_n != 0:
            return None
        # Per-turn cap.
        start = _latest_human_index(messages) + 1
        reviews_in_turn = sum(1 for m in messages[start:] if isinstance(m, SystemMessage) and _MARKER in _content_text(m))
        if reviews_in_turn >= _MAX_REVIEWS_PER_TURN:
            return None
        fingerprint = _window_fingerprint(messages)
        # Don't re-emit identical fingerprint.
        for m in reversed(messages[start:]):
            if isinstance(m, SystemMessage) and _MARKER in _content_text(m) and fingerprint in _content_text(m):
                return None
        message = _build_review_message(messages, fingerprint)
        runtime_state = dict(state.get("runtime") or {})
        runtime_state["step_review"] = {
            "fingerprint": fingerprint,
            "batches_completed": batches,
            "cadence_every_n": self.every_n,
        }
        logger.info(
            "StepReflection: injecting step_review fingerprint=%s batches=%d",
            fingerprint,
            batches,
        )
        return {"messages": [message], "runtime": runtime_state}


__all__ = ["StepReflectionMiddleware"]
