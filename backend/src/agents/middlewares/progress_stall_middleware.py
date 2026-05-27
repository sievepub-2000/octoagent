"""Progress-stall self-reflection middleware (Reflexion pattern).

Activates when the agent loop shows symptoms of being "stuck":
  - Repeating identical tool calls (same name+args) ≥ N times in the
    current human turn.
  - The last K tool outputs are highly redundant (e.g. all empty, or all
    identical short strings) → information gain per call ≈ 0.

When stalled, injects a single ``<self_reflection>`` SystemMessage telling
the model to:
  1. Summarise the concrete evidence it has already collected.
  2. List the still-unknown facts.
  3. Decide explicitly: either (a) finalise an answer with what it has, or
     (b) switch strategy with a *different* concrete next step.
  4. Stop repeating any already-tried tool call verbatim.

The middleware is throttled: once a self-reflection has been injected for a
given stall signature it is not injected again for that signature within the
same human turn. The full pattern mirrors Reflexion / Self-Refine: a cheap
heuristic detector + an LLM-time self-critique prompt rather than a hard
abort.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import Counter
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime

from src.utils.messages import latest_human_index as _latest_human_index
from src.utils.messages import message_text as _message_text

logger = logging.getLogger(__name__)


_DUP_THRESHOLD = int(os.getenv("OCTO_PROGRESS_STALL_DUP", "3"))
_REDUNDANT_OUTPUT_WINDOW = int(os.getenv("OCTO_PROGRESS_STALL_WINDOW", "5"))
_REDUNDANT_OUTPUT_MIN = int(os.getenv("OCTO_PROGRESS_STALL_REDUNDANT", "4"))
_MAX_REFLECTIONS_PER_TURN = int(os.getenv("OCTO_PROGRESS_STALL_MAX_REFLECTIONS", "3"))
# Soft escalation ceiling: if any single tool-call signature is repeated this
# many times in a single human turn, force a strategy-change prompt instead of
# injecting another generic self-reflection. The legacy HARD_STOP env name is
# still accepted for compatibility, but this path never jumps to graph end.
_SOFT_ESCALATION_DUP = int(os.getenv("OCTO_PROGRESS_STALL_SOFT_ESCALATION_DUP", os.getenv("OCTO_PROGRESS_STALL_HARD_STOP_DUP", "3")))
# Deep soft ceiling: once the same call repeats this many times, inject stronger
# strategy-change guidance instead of allowing the same call loop to continue.
_SAFETY_NET_DUP = max(_SOFT_ESCALATION_DUP + 2, int(os.getenv("OCTO_PROGRESS_STALL_SAFETY_NET_DUP", "5")))
# Maximum number of soft-recovery system messages to inject for any single stall
# signature inside one human turn before escalating to user-communication advice.
_MAX_SOFT_ESCALATIONS_PER_SIGNATURE = int(os.getenv("OCTO_PROGRESS_STALL_MAX_SOFT_PER_SIG", "2"))
_USER_HANDOFF_MARKER = '<progress_stall_user_handoff origin="progress_stall_middleware"'
_SOFT_ESCALATION_MARKER = '<progress_stall_recovery origin="progress_stall_middleware"'

# Marker we put in the SystemMessage content so we can find prior injections
# and avoid spamming the model with duplicate reflections.
_REFLECTION_MARKER = '<self_reflection origin="progress_stall_middleware"'






def _tool_call_signature(name: str, args: object) -> str:
    try:
        payload = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        payload = str(args)
    return f"{name}::{payload}"


def _short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:10]


def _normalise_output(text: str, head: int = 240) -> str:
    """Produce a stable signature for a tool output.

    Keeps the head of the text after collapsing whitespace so that semantically
    identical outputs (e.g. ``(no output)``) collide deterministically.
    """
    flat = " ".join(text.split())
    return flat[:head]


def _gather_turn_tool_history(messages: list[Any]) -> tuple[list[str], list[str], list[str]]:
    """Return (tool_call_signatures, output_signatures, ai_tool_call_signatures).

    Only considers messages produced after the latest human turn.
    """
    start = _latest_human_index(messages) + 1
    scoped = messages[start:]

    tool_call_sigs_in_ai: list[str] = []
    output_sigs: list[str] = []
    id_to_call: dict[str, tuple[str, object]] = {}

    for msg in scoped:
        if isinstance(msg, AIMessage):
            for call in getattr(msg, "tool_calls", None) or []:
                name = str(call.get("name") or "unknown")
                args = call.get("args")
                sig = _tool_call_signature(name, args)
                tool_call_sigs_in_ai.append(sig)
                call_id = call.get("id")
                if call_id:
                    id_to_call[call_id] = (name, args)
        elif isinstance(msg, ToolMessage):
            output_sigs.append(_normalise_output(_message_text(msg)))

    # The "per-call" signature view (one entry per executed tool message)
    per_call_sigs: list[str] = []
    for msg in scoped:
        if isinstance(msg, ToolMessage):
            tool_call_id = getattr(msg, "tool_call_id", None)
            if tool_call_id and tool_call_id in id_to_call:
                name, args = id_to_call[tool_call_id]
                per_call_sigs.append(_tool_call_signature(name, args))
            else:
                per_call_sigs.append(_tool_call_signature(str(getattr(msg, "name", None) or "unknown"), None))

    return per_call_sigs, output_sigs, tool_call_sigs_in_ai


def _count_prior_reflections(messages: list[Any]) -> int:
    start = _latest_human_index(messages) + 1
    count = 0
    for msg in messages[start:]:
        if isinstance(msg, SystemMessage) and _REFLECTION_MARKER in _message_text(msg):
            count += 1
    return count


def _stall_signature(per_call_sigs: list[str], output_sigs: list[str]) -> str | None:
    """Return a stable stall fingerprint, or None if no stall.

    A stall is defined by EITHER of:
      * any single (name+args) signature repeated >= _DUP_THRESHOLD times;
      * within the last _REDUNDANT_OUTPUT_WINDOW tool outputs, the most
        common normalised output appears >= _REDUNDANT_OUTPUT_MIN times.
    """
    # Duplicate-call detector.
    dup_counter = Counter(per_call_sigs)
    most_common_call, most_common_call_count = (dup_counter.most_common(1) or [(None, 0)])[0]
    if most_common_call and most_common_call_count >= _DUP_THRESHOLD:
        return f"dup-call:{_short_hash(most_common_call)}:{most_common_call_count}"

    # Output redundancy detector.
    if len(output_sigs) >= _REDUNDANT_OUTPUT_WINDOW:
        window = output_sigs[-_REDUNDANT_OUTPUT_WINDOW:]
        ranked = Counter(window).most_common(1)
        if ranked and ranked[0][1] >= _REDUNDANT_OUTPUT_MIN:
            return f"redundant-output:{_short_hash(ranked[0][0])}:{ranked[0][1]}"

    return None


def _build_reflection_message(
    *,
    stall_signature: str,
    per_call_sigs: list[str],
    output_sigs: list[str],
) -> SystemMessage:
    """Compose the Reflexion-style prompt."""
    top_calls = Counter(per_call_sigs).most_common(3)
    top_outputs = Counter(output_sigs[-_REDUNDANT_OUTPUT_WINDOW:]).most_common(2)

    call_lines = []
    for sig, count in top_calls:
        # sig is "name::json"; render compactly
        try:
            name, payload = sig.split("::", 1)
        except ValueError:
            name, payload = sig, ""
        payload = payload[:160] + ("…" if len(payload) > 160 else "")
        call_lines.append(f"  - {count}× {name} {payload}")

    output_lines = []
    for sig, count in top_outputs:
        snippet = sig[:120] + ("…" if len(sig) > 120 else "")
        output_lines.append(f'  - {count}× "{snippet}"')

    body = "\n".join(
        [
            f'{_REFLECTION_MARKER} signature="{stall_signature}">',
            "你陷入了重复执行同一个工具调用、且新产出信息为 0 的循环。",
            "",
            "最近被重复发起的工具调用：",
            *(call_lines or ["  - (无)"]),
            "",
            "最近的工具输出分布：",
            *(output_lines or ["  - (无)"]),
            "",
            "请按下面 4 步在下一条助理消息里完成 自检（self-reflection）：",
            "1. 用 ≤5 行总结当前已经收集到的具体证据（事实，不是推测）。",
            "2. 用 ≤5 行列出仍未知、但用户原始任务真正需要的事实。",
            "3. 做一个明确决定，并写在最前面：",
            "   - 决定 A：现有证据已经足够，立即向用户输出最终报告/答案（不要再调用更多工具）。",
            "   - 决定 B：必须换策略——给出一个与上面重复列表里**完全不同**的下一步工具调用（不同工具，或显著不同的参数）。",
            "4. 严禁再以相同参数调用上述重复工具；空结果本身就是确定性答案——它意味着该路径无目标存在，应当被采纳为最终结论而不是反复重试。",
            "</self_reflection>",
        ]
    )
    return SystemMessage(content=body)


def _max_dup_count(per_call_sigs: list[Any]) -> int:
    if not per_call_sigs:
        return 0
    return Counter(per_call_sigs).most_common(1)[0][1]


def _build_user_handoff_message(per_call_sigs: list[str], dup_count: int) -> SystemMessage:
    top = Counter(per_call_sigs).most_common(1)
    top_sig = top[0][0] if top else "(unknown)"
    try:
        name, payload = top_sig.split("::", 1)
    except ValueError:
        name, payload = top_sig, ""
    payload = payload[:240] + ("..." if len(payload) > 240 else "")
    body = (
        f'{_USER_HANDOFF_MARKER} signature="dup={dup_count}">\n'
        f"Progress stall recovery: the same tool call repeated {dup_count} times after self-reflection.\n"
        "This is a deep soft-recovery instruction, not a hard stop, not task completion, and not a default handoff to the user.\n"
        f"Repeated tool: {name}\n"
        f"Repeated arguments (first 240 chars): {payload}\n"
        "\nNext assistant message must do one of these safe actions:\n"
        "1) Continue with a different tool, source, or materially different arguments.\n"
        "2) If existing evidence is sufficient, provide the substantive answer from that evidence.\n"
        "3) Ask exactly one clear question only when missing user credentials, paths, accounts, or business choices are truly required.\n"
        "Do not repeat the same tool arguments and do not claim that runtime policy stopped the task.\n"
        "</progress_stall_user_handoff>"
    )
    return SystemMessage(content=body)

def _user_handoff_visible(messages: list[Any]) -> bool:
    start = _latest_human_index(messages) + 1
    return any(isinstance(message, SystemMessage) and _USER_HANDOFF_MARKER in _message_text(message) for message in messages[start:])


def _build_ignored_handoff_answer(per_call_sigs: list[str], dup_count: int) -> str:
    top = Counter(per_call_sigs).most_common(1)
    top_sig = top[0][0] if top else "(unknown)"
    try:
        name, payload = top_sig.split("::", 1)
    except ValueError:
        name, payload = top_sig, ""
    payload = payload[:360] + ("..." if len(payload) > 360 else "")
    return "\n".join(
        [
            "Progress-stall recovery checkpoint: repeated tool calls need a strategy change.",
            "",
            "Observed loop:",
            f"- The same tool path repeated {dup_count} times without adding new evidence.",
            f"- Repeated tool: {name}",
            f"- Repeated arguments summary: {payload}",
            "",
            "This is recoverable and not task completion. Continue by changing tool, source, or arguments, or answer from the evidence already collected if it is sufficient.",
        ]
    )

def _build_soft_escalation_message(per_call_sigs: list[str], dup_count: int, stall_signature: str = "") -> SystemMessage:
    top = Counter(per_call_sigs).most_common(1)
    top_sig = top[0][0] if top else "(unknown)"
    try:
        name, payload = top_sig.split("::", 1)
    except ValueError:
        name, payload = top_sig, ""
    payload = payload[:240] + ("…" if len(payload) > 240 else "")
    body = (
        f'{_SOFT_ESCALATION_MARKER} signature="{stall_signature or f"dup={dup_count}"}" dup="{dup_count}">\n'
        f"同一工具调用已重复 {dup_count} 次（阈值 {_SOFT_ESCALATION_DUP}），且常规 self-reflection 未打破循环。\n"
        "这不是系统级错误，不要直接停止任务或把控制权交回用户。请立即切换策略继续执行。\n"
        f"重复中的工具： {name}\n"
        f"重复参数 (截取前 240): {payload}\n"
        "\n下一条助理消息必须完成：\n"
        "1) 用事实清单总结已经确认的信息。\n"
        "2) 明确写出这条路径为何没有新增信息。\n"
        "3) 选择一个不同工具、不同参数或不同证据来源的下一步。\n"
        "4) 除非出现系统级错误，继续推进用户任务；不要再次调用上述重复工具参数。\n"
        "</progress_stall_recovery>"
    )
    return SystemMessage(content=body)


class ProgressStallMiddleware(AgentMiddleware[AgentState]):
    """Detect progress stalls and inject a Reflexion-style self-critique."""

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_reflect(state)

    @override
    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_reflect(state)

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_finalize_ignored_handoff(state)

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_finalize_ignored_handoff(state)

    def _maybe_finalize_ignored_handoff(self, state: AgentState) -> dict | None:
        messages = list(state.get("messages", []))
        if not messages:
            return None
        last_message = messages[-1]
        if getattr(last_message, "type", None) != "ai" or not getattr(last_message, "tool_calls", None):
            return None
        if not _user_handoff_visible(messages):
            return None
        per_call_sigs, output_sigs, _ai_sigs = _gather_turn_tool_history(messages[:-1])
        dup_count = _max_dup_count(per_call_sigs)
        if dup_count < _DUP_THRESHOLD:
            return None
        runtime_state = dict(state.get("runtime") or {})
        runtime_state["progress_stall"] = {
            "signature": "ignored_user_handoff",
            "per_call_count": len(per_call_sigs),
            "output_count": len(output_sigs),
            "escalation": "ignored_handoff_observed",
            "hard_stop": False,
            "next_action": "allow tool middleware to block duplicate calls and continue with a changed strategy",
        }
        return {"runtime": runtime_state}

    def _maybe_reflect(self, state: AgentState) -> dict | None:
        messages = list(state.get("messages", []))
        if not messages:
            return None
        # Only consider reflecting right after a ToolMessage block.
        if not isinstance(messages[-1], ToolMessage):
            return None

        per_call_sigs, output_sigs, _ai_sigs = _gather_turn_tool_history(messages)
        signature = _stall_signature(per_call_sigs, output_sigs)
        if signature is None:
            return None

        dup_count = _max_dup_count(per_call_sigs)
        prior_reflections = _count_prior_reflections(messages)
        turn_start = _latest_human_index(messages) + 1
        scoped = messages[turn_start:]
        already_terminal = _user_handoff_visible(messages)
        # Count how many soft-recovery messages we have already injected for
        # this exact stall signature inside the current human turn. Without
        # this throttle the soft branch would re-inject the same system
        # message on every `before_model` call, flooding the prompt and
        # never breaking the loop (observed in production: same write_todos
        # repeated 90+ times because soft escalation had no throttle and the
        # hard-stop env flag was disabled by default).
        soft_for_signature = 0
        stable_signature_prefix = ":".join(signature.split(":")[:2])
        for m in scoped:
            if isinstance(m, SystemMessage):
                text = _message_text(m)
                if _SOFT_ESCALATION_MARKER in text and stable_signature_prefix in text:
                    soft_for_signature += 1

        # Deep soft escalation: if repeated self-reflection did not help, ask
        # the model to change strategy. No graph jump is returned here; OOM guard
        # remains the only automatic hard stop.
        safety_net_triggered = (
            dup_count >= _SAFETY_NET_DUP
            or soft_for_signature >= _MAX_SOFT_ESCALATIONS_PER_SIGNATURE
        )

        # Escalation: same tool call repeated past ceiling, or reflections
        # exhausted but still stalled. Default to a soft recovery instruction;
        # hard END is the safety net and also an explicit operator opt-in.
        if not already_terminal and (dup_count >= _SOFT_ESCALATION_DUP or (prior_reflections >= _MAX_REFLECTIONS_PER_TURN and dup_count >= _DUP_THRESHOLD)):
            logger.warning(
                "ProgressStall: escalating signature=%s dup=%d prior_reflections=%d soft_for_sig=%d safety_net=%s",
                signature,
                dup_count,
                prior_reflections,
                soft_for_signature,
                safety_net_triggered,
            )
            return {
                "messages": [_build_soft_escalation_message(per_call_sigs, dup_count, signature)],
                "runtime": {
                    **dict(state.get("runtime") or {}),
                    "progress_stall": {
                        "signature": signature,
                        "per_call_count": len(per_call_sigs),
                        "output_count": len(output_sigs),
                        "escalation": "deep_soft_recovery" if safety_net_triggered else "soft_recovery",
                        "soft_for_signature": soft_for_signature + 1,
                        "hard_stop": False,
                    },
                },
            }

        # Throttle: at most _MAX_REFLECTIONS_PER_TURN reflections per human turn.
        if prior_reflections >= _MAX_REFLECTIONS_PER_TURN:
            return None

        # Throttle: don't re-inject the same stall family (kind + content hash) again.
        # The trailing ":<count>" varies as duplicates grow, so we compare only the
        # stable prefix ``kind:hash``.
        stable_prefix = ":".join(signature.split(":")[:2])
        start = _latest_human_index(messages) + 1
        for prior in reversed(messages[start:]):
            if isinstance(prior, SystemMessage):
                text = _message_text(prior)
                if _REFLECTION_MARKER in text and stable_prefix in text:
                    return None
                if _REFLECTION_MARKER in text:
                    # Older different reflection — keep going, allow new injection.
                    break
            else:
                continue

        message = _build_reflection_message(
            stall_signature=signature,
            per_call_sigs=per_call_sigs,
            output_sigs=output_sigs,
        )
        runtime_state = dict(state.get("runtime") or {})
        runtime_state["progress_stall"] = {
            "signature": signature,
            "per_call_count": len(per_call_sigs),
            "output_count": len(output_sigs),
        }
        logger.info("ProgressStall: injecting self_reflection signature=%s", signature)
        return {"messages": [message], "runtime": runtime_state}
