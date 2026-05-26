"""Unit tests for StepReflectionMiddleware."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agents.middlewares.step_reflection_middleware import (
    StepReflectionMiddleware,
    _count_completed_tool_batches,
    _ends_on_tool_batch_boundary,
    _window_fingerprint,
)


def _ai_tool_call(call_id: str, name: str = "bash", args: dict | None = None) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"id": call_id, "name": name, "args": args or {"cmd": "ls"}}],
    )


def _tool_msg(call_id: str, content: str = "ok", name: str = "bash") -> ToolMessage:
    return ToolMessage(content=content, tool_call_id=call_id, name=name)


def test_batch_boundary_detects_resolved_batch() -> None:
    messages = [
        HumanMessage(content="go"),
        _ai_tool_call("c1"),
        _tool_msg("c1", "alpha"),
    ]
    assert _ends_on_tool_batch_boundary(messages) is True
    assert _count_completed_tool_batches(messages) == 1


def test_batch_boundary_false_when_pending() -> None:
    messages = [
        HumanMessage(content="go"),
        AIMessage(
            content="",
            tool_calls=[
                {"id": "c1", "name": "bash", "args": {"cmd": "a"}},
                {"id": "c2", "name": "bash", "args": {"cmd": "b"}},
            ],
        ),
        _tool_msg("c1", "alpha"),
    ]
    assert _ends_on_tool_batch_boundary(messages) is False


def test_no_inject_before_threshold() -> None:
    mw = StepReflectionMiddleware(every_n=3)
    messages = [HumanMessage(content="go"), _ai_tool_call("c1"), _tool_msg("c1", "alpha")]
    result = mw._maybe_inject({"messages": messages})
    assert result is None


def test_inject_on_every_n_th_batch() -> None:
    mw = StepReflectionMiddleware(every_n=2)
    messages: list = [HumanMessage(content="go")]
    # batch 1
    messages += [_ai_tool_call("c1", args={"cmd": "a"}), _tool_msg("c1", "alpha")]
    assert mw._maybe_inject({"messages": list(messages)}) is None
    # batch 2 → should inject
    messages += [_ai_tool_call("c2", args={"cmd": "b"}), _tool_msg("c2", "beta")]
    result = mw._maybe_inject({"messages": list(messages)})
    assert result is not None and "messages" in result
    sysmsg = result["messages"][0]
    assert isinstance(sysmsg, SystemMessage)
    text = sysmsg.content if isinstance(sysmsg.content, str) else str(sysmsg.content)
    assert "<step_review" in text
    assert "SUCCESS" in text and "PARTIAL" in text and "FAILED" in text


def test_throttle_same_fingerprint() -> None:
    mw = StepReflectionMiddleware(every_n=1)
    base = [HumanMessage(content="go"), _ai_tool_call("c1", args={"cmd": "a"}), _tool_msg("c1", "alpha")]
    first = mw._maybe_inject({"messages": list(base)})
    assert first is not None
    injected = first["messages"][0]
    # Same fingerprint window → don't re-inject
    again = mw._maybe_inject({"messages": list(base) + [injected]})
    assert again is None


def test_resets_on_new_human_turn() -> None:
    mw = StepReflectionMiddleware(every_n=2)
    msgs1: list = [HumanMessage(content="go")]
    msgs1 += [_ai_tool_call("a1", args={"cmd": "1"}), _tool_msg("a1", "x")]
    msgs1 += [_ai_tool_call("a2", args={"cmd": "2"}), _tool_msg("a2", "y")]
    r1 = mw._maybe_inject({"messages": list(msgs1)})
    assert r1 is not None
    # New human turn
    msgs2 = list(msgs1) + [r1["messages"][0], AIMessage(content="done"), HumanMessage(content="next")]
    msgs2 += [_ai_tool_call("b1", args={"cmd": "3"}), _tool_msg("b1", "z")]
    # Only 1 batch since latest human → no inject yet
    assert mw._maybe_inject({"messages": list(msgs2)}) is None
    msgs2 += [_ai_tool_call("b2", args={"cmd": "4"}), _tool_msg("b2", "w")]
    r2 = mw._maybe_inject({"messages": list(msgs2)})
    assert r2 is not None


def test_cap_per_turn(monkeypatch) -> None:
    # Tight cap, fire-every-batch.
    monkeypatch.setenv("OCTO_STEP_REVIEW_MAX_PER_TURN", "1")
    # Need to reload the module to pick up env override.
    import importlib

    from src.agents.middlewares import step_reflection_middleware as mod

    importlib.reload(mod)
    mw = mod.StepReflectionMiddleware(every_n=1)
    msgs: list = [HumanMessage(content="go")]
    msgs += [_ai_tool_call("a1", args={"cmd": "1"}), _tool_msg("a1", "x")]
    r1 = mw._maybe_inject({"messages": list(msgs)})
    assert r1 is not None
    msgs.append(r1["messages"][0])
    msgs += [_ai_tool_call("a2", args={"cmd": "2"}), _tool_msg("a2", "y")]
    r2 = mw._maybe_inject({"messages": list(msgs)})
    assert r2 is None  # capped


def test_fingerprint_changes_with_different_args() -> None:
    base = [HumanMessage(content="go"), _ai_tool_call("c1", args={"cmd": "a"}), _tool_msg("c1", "alpha")]
    fp1 = _window_fingerprint(base)
    alt = [HumanMessage(content="go"), _ai_tool_call("c1", args={"cmd": "b"}), _tool_msg("c1", "alpha")]
    fp2 = _window_fingerprint(alt)
    assert fp1 != fp2
