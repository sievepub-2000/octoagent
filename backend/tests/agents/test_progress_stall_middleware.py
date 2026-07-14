"""Regression tests for ProgressStallMiddleware.

Covers the production stall pathology where the same ``write_todos`` tool call
was repeated 90+ times in a single human turn because the soft-escalation
branch had no per-signature throttle and the hard-stop branch was gated behind
an env flag that defaulted to off. See ``backend/src/agents/middlewares/
progress_stall_middleware.py``.
"""

from __future__ import annotations

import importlib

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


@pytest.fixture()
def mw_module(monkeypatch):
    """Fresh import with explicit env so module-level constants are stable."""
    monkeypatch.setenv("OCTO_PROGRESS_STALL_DUP", "3")
    monkeypatch.setenv("OCTO_PROGRESS_STALL_SOFT_ESCALATION_DUP", "6")
    monkeypatch.setenv("OCTO_PROGRESS_STALL_SAFETY_NET_DUP", "12")
    monkeypatch.setenv("OCTO_PROGRESS_STALL_MAX_SOFT_PER_SIG", "2")
    monkeypatch.setenv("OCTO_PROGRESS_STALL_MAX_REFLECTIONS", "3")
    import src.agents.middlewares.progress_stall_middleware as mod

    importlib.reload(mod)
    return mod


def _make_messages(tool_name: str, args: dict, dup: int) -> list:
    """Build a synthetic message history with `dup` repeats of the same call."""
    msgs: list = [HumanMessage(content="please do the thing")]
    for i in range(dup):
        call_id = f"call_{i}"
        msgs.append(
            AIMessage(
                content="",
                tool_calls=[{"id": call_id, "name": tool_name, "args": args}],
            )
        )
        msgs.append(ToolMessage(content="ok", tool_call_id=call_id, name=tool_name))
    return msgs


class _State(dict):
    pass


def _run(mw_module, messages):
    mw = mw_module.ProgressStallMiddleware()
    state = _State(messages=messages, runtime={})
    return mw._maybe_reflect(state)


def test_reflection_injected_at_threshold(mw_module):
    msgs = _make_messages("write_todos", {"todos": ["a"]}, dup=3)
    out = _run(mw_module, msgs)
    assert out is not None
    rendered = out["messages"][0].content
    assert mw_module._REFLECTION_MARKER in rendered


def test_soft_escalation_injected_once_then_throttled(mw_module):
    msgs = _make_messages("write_todos", {"todos": ["a"]}, dup=6)
    out1 = _run(mw_module, msgs)
    assert out1 is not None
    msg1 = out1["messages"][0]
    assert mw_module._SOFT_ESCALATION_MARKER in msg1.content
    # Replay: add the soft escalation back into the history (simulates the
    # next before_model tick) and bump the dup count by one more call.
    msgs2 = msgs + [msg1]
    msgs2 += _make_messages("write_todos", {"todos": ["a"]}, dup=1)[1:]
    # dup is now 7; soft_for_signature=1 (< MAX=2) so we still get a 2nd soft.
    out2 = _run(mw_module, msgs2)
    assert out2 is not None
    assert mw_module._SOFT_ESCALATION_MARKER in out2["messages"][0].content


def test_safety_net_requests_user_handoff_when_soft_max_reached(mw_module):
    msgs = _make_messages("write_todos", {"todos": ["a"]}, dup=6)
    first = _run(mw_module, msgs)
    assert first is not None
    msgs.append(first["messages"][0])
    # Append another soft escalation (simulating second tick).
    msgs += _make_messages("write_todos", {"todos": ["a"]}, dup=1)[1:]
    second = _run(mw_module, msgs)
    assert second is not None
    msgs.append(second["messages"][0])
    # Now we have 2 soft-recovery messages for this signature; the next stall
    # observation must remain a deep soft recovery, not a user-visible stop.
    msgs += _make_messages("write_todos", {"todos": ["a"]}, dup=1)[1:]
    third = _run(mw_module, msgs)
    assert third is not None
    assert third.get("jump_to") is None
    assert mw_module._SOFT_ESCALATION_MARKER in third["messages"][0].content
    assert mw_module._USER_HANDOFF_MARKER not in third["messages"][0].content
    assert third["runtime"]["progress_stall"]["escalation"] == "deep_soft_recovery"
    assert third["runtime"]["progress_stall"]["hard_stop"] is False


def test_safety_net_requests_user_handoff_when_dup_exceeds_ceiling(mw_module):
    msgs = _make_messages("write_todos", {"todos": ["a"]}, dup=12)
    out = _run(mw_module, msgs)
    assert out is not None
    # 12 dup hits _SAFETY_NET_DUP but remains a soft strategy-change prompt.
    assert out.get("jump_to") is None
    assert mw_module._SOFT_ESCALATION_MARKER in out["messages"][0].content
    assert mw_module._USER_HANDOFF_MARKER not in out["messages"][0].content
    assert out["runtime"]["progress_stall"]["escalation"] == "deep_soft_recovery"
    assert out["runtime"]["progress_stall"]["hard_stop"] is False


def test_ignored_user_handoff_does_not_replace_more_tool_calls_by_default(mw_module):
    mw = mw_module.ProgressStallMiddleware()
    msgs = _make_messages("write_todos", {"todos": ["a"]}, dup=12)
    handoff = mw_module._build_user_handoff_message([r'write_todos::{"todos":["a"]}'], 12)
    msgs.append(handoff)
    final_tool_call = AIMessage(content="", tool_calls=[{"id": "call-final", "name": "write_todos", "args": {"todos": ["a"]}}])
    msgs.append(final_tool_call)

    update = mw.after_model(_State(messages=msgs, runtime={}), None)

    assert update is not None
    assert "messages" not in update
    assert final_tool_call.tool_calls
    assert update["runtime"]["progress_stall"]["escalation"] == "ignored_handoff_observed"
    assert update["runtime"]["progress_stall"]["hard_stop"] is False


def test_no_action_when_below_threshold(mw_module):
    msgs = _make_messages("write_todos", {"todos": ["a"]}, dup=2)
    assert _run(mw_module, msgs) is None


def test_goal_autopilot_stall_prompt_requires_different_strategy(mw_module):
    mw = mw_module.ProgressStallMiddleware()
    msgs = _make_messages("web_fetch", {"url": "https://example.com"}, dup=3)

    out = mw._maybe_reflect(_State(messages=msgs, runtime={"execution_mode": "goal_autopilot"}))

    assert out is not None
    content = out["messages"][0].content
    assert 'execution_mode="goal_autopilot"' in content
    assert "至少尝试两种不同策略" in content
    assert out["runtime"]["progress_stall"]["execution_mode"] == "goal_autopilot"


def test_assisted_soft_escalation_can_ask_user_after_failed_strategies(mw_module):
    mw = mw_module.ProgressStallMiddleware()
    msgs = _make_messages("web_fetch", {"url": "https://example.com"}, dup=6)

    out = mw._maybe_reflect(_State(messages=msgs, runtime={"execution_mode": "assisted"}))

    assert out is not None
    content = out["messages"][0].content
    assert 'execution_mode="assisted"' in content
    assert "问一个清晰问题" in content
