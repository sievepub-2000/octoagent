"""Tests for ProgressStallMiddleware."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agents.middlewares.progress_stall_middleware import (
    _REFLECTION_MARKER,
    ProgressStallMiddleware,
    _gather_turn_tool_history,
    _stall_signature,
)


def _make_dup_call_stream(n: int) -> list:
    msgs: list = [HumanMessage(content="check files")]
    for i in range(n):
        msgs.append(
            AIMessage(
                content="",
                tool_calls=[
                    {"id": f"c{i}a", "name": "bash", "args": {"command": "ls /a"}},
                    {"id": f"c{i}b", "name": "bash", "args": {"command": "ls /b"}},
                ],
            )
        )
        msgs.append(ToolMessage(content="(no output)", name="bash", tool_call_id=f"c{i}a"))
        msgs.append(ToolMessage(content="(no output)", name="bash", tool_call_id=f"c{i}b"))
    return msgs


def test_no_stall_when_short():
    msgs = _make_dup_call_stream(1)
    per_calls, outputs, _ = _gather_turn_tool_history(msgs)
    assert _stall_signature(per_calls, outputs) is None


def test_duplicate_call_triggers():
    msgs = _make_dup_call_stream(3)
    per_calls, outputs, _ = _gather_turn_tool_history(msgs)
    sig = _stall_signature(per_calls, outputs)
    assert sig is not None
    assert sig.startswith("dup-call:") or sig.startswith("redundant-output:")


def test_redundant_output_triggers_even_without_dup_args():
    """Different args, but identical empty output → still stall."""
    msgs: list = [HumanMessage(content="audit")]
    for i in range(5):
        msgs.append(
            AIMessage(
                content="",
                tool_calls=[{"id": f"c{i}", "name": "bash", "args": {"command": f"ls /p{i}"}}],
            )
        )
        msgs.append(ToolMessage(content="(no output)", name="bash", tool_call_id=f"c{i}"))
    per_calls, outputs, _ = _gather_turn_tool_history(msgs)
    sig = _stall_signature(per_calls, outputs)
    assert sig is not None, "5 identical empty outputs should trigger stall"


def test_middleware_injects_one_reflection():
    mw = ProgressStallMiddleware()
    msgs = _make_dup_call_stream(4)
    out = mw._maybe_reflect({"messages": msgs})
    assert out is not None
    new_msgs = out["messages"]
    assert len(new_msgs) == 1
    assert isinstance(new_msgs[0], SystemMessage)
    assert _REFLECTION_MARKER in new_msgs[0].content


def test_middleware_throttles_same_signature():
    mw = ProgressStallMiddleware()
    msgs = _make_dup_call_stream(4)
    first = mw._maybe_reflect({"messages": msgs})
    assert first is not None
    # Append the same reflection to the transcript and try again with the same stall;
    # should NOT inject again (same signature).
    msgs.append(first["messages"][0])
    msgs.append(
        AIMessage(
            content="",
            tool_calls=[{"id": "cN", "name": "bash", "args": {"command": "ls /a"}}],
        )
    )
    msgs.append(ToolMessage(content="(no output)", name="bash", tool_call_id="cN"))
    second = mw._maybe_reflect({"messages": msgs})
    assert second is None, "duplicate signature should be throttled"


def test_no_stall_when_outputs_differ():
    msgs: list = [HumanMessage(content="ok")]
    for i in range(5):
        msgs.append(
            AIMessage(
                content="",
                tool_calls=[{"id": f"c{i}", "name": "bash", "args": {"command": f"ls /p{i}"}}],
            )
        )
        msgs.append(ToolMessage(content=f"file{i}.txt", name="bash", tool_call_id=f"c{i}"))
    per_calls, outputs, _ = _gather_turn_tool_history(msgs)
    assert _stall_signature(per_calls, outputs) is None


def test_repeated_stall_escalates_softly_by_default():
    mw = ProgressStallMiddleware()
    msgs = _make_dup_call_stream(6)
    out = mw._maybe_reflect({"messages": msgs, "runtime": {}})
    assert out is not None
    assert "jump_to" not in out
    assert "progress_stall_recovery" in out["messages"][0].content
    assert out["runtime"]["progress_stall"]["escalation"] == "soft_recovery"
