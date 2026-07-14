from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agents.middlewares.runtime_state_middleware import RuntimeStateMiddleware
from src.agents.middlewares.session_compaction_middleware import (
    SYSTEM_SESSION_CONTINUE_PROMPT,
    SessionCompactionMiddleware,
    _completed_item_hash,
    _message_estimated_tokens,
)


def _large_tool_message(content: str) -> ToolMessage:
    return ToolMessage(content=content, name="bash", tool_call_id="call-1")


class _Runtime:
    def __init__(self, context: dict[str, object]) -> None:
        self.context = context


def test_oversized_tool_output_is_truncated_before_model_call() -> None:
    middleware = SessionCompactionMiddleware(max_context_tokens=32_000, allow_hard_truncation=True)
    oversized_output = "x" * 6_000
    messages = [HumanMessage(content="run a command"), _large_tool_message(oversized_output)]

    update = middleware.before_model({"messages": messages, "runtime": {}}, None)

    assert update is not None
    next_messages = update["messages"]
    assert SYSTEM_SESSION_CONTINUE_PROMPT in next_messages[1].content
    assert "OctoAgent context guard" not in next_messages[1].content
    assert "truncated" not in next_messages[1].content
    assert update["runtime"]["context_guard_state"] == "truncated"
    assert "memory_guard_state" not in update["runtime"]
    assert update["runtime"]["recommended_memory_action"] == "compact"


def test_compaction_result_is_trimmed_to_model_budget() -> None:
    middleware = SessionCompactionMiddleware(max_context_tokens=1_000, keep_recent_turns=12)
    messages = [SystemMessage(content="System prompt")]
    for index in range(80):
        messages.append(HumanMessage(content=f"Older user turn {index} " + ("x" * 900)))
        messages.append(AIMessage(content=f"Older assistant turn {index} " + ("y" * 900)))

    update = middleware.before_model({"messages": messages, "runtime": {}}, None)

    assert update is not None
    assert update["runtime"]["recommended_memory_action"] == "compact"
    assert update["runtime"]["compaction_dropped_messages"] > 0
    assert any(SYSTEM_SESSION_CONTINUE_PROMPT == message.content for message in update["messages"] if message.type == "system")
    assert not any("<system:" in message.content for message in update["messages"] if message.type == "system")
    assert not any("OctoAgent context guard" in message.content for message in update["messages"] if message.type == "system")
    assert len(update["messages"]) < len(messages)
    assert sum(_message_estimated_tokens(message) for message in update["messages"]) <= 850


def test_compaction_persists_runtime_checkpoint_summary() -> None:
    middleware = SessionCompactionMiddleware(max_context_tokens=200, keep_recent_turns=1)
    messages = [SystemMessage(content="System prompt")]
    for index in range(8):
        messages.append(HumanMessage(content=f"Older user turn {index} " + ("x" * 220)))
        messages.append(AIMessage(content=f"Older assistant turn {index} " + ("y" * 220)))

    update = middleware.before_model({"messages": messages, "runtime": {}}, None)

    assert update is not None
    assert update["runtime"]["recommended_memory_action"] == "compact"
    assert update["runtime"]["compaction_summary"].startswith("[Session compaction review")
    assert update["runtime"]["compaction_saved_tokens"] > 0
    assert update["runtime"]["context_cycle_id"].startswith("context-cycle-")
    assert update["runtime"]["context_cycle_base_tokens"] > 0
    assert update["runtime"]["context_cycle_started_at"]
    assert update["runtime"]["task_review_required"] is True
    assert update["runtime"]["memory_followup_action"] == "promote_compaction_review_to_memory"


def test_compaction_merges_completed_todos_before_generating_summary() -> None:
    middleware = SessionCompactionMiddleware(max_context_tokens=220, keep_recent_turns=1)
    messages = [SystemMessage(content="System prompt")]
    for index in range(10):
        messages.append(HumanMessage(content=f"Older user turn {index} " + ("x" * 220)))
        messages.append(AIMessage(content=f"Older assistant turn {index} " + ("y" * 220)))
    state = {
        "messages": messages,
        "runtime": {},
        "task_state": {"goal": "repair long task continuation"},
        "todos": [
            {"content": "Fix skipped tests", "status": "completed"},
            {"content": "Fix skipped tests", "status": "completed"},
            {"content": "Validate continuation summary", "status": "in_progress"},
        ],
    }

    update = middleware.before_model(state, None)

    assert update is not None
    assert update["task_state"]["completed_steps"] == ["Fix skipped tests"]
    assert update["task_state"]["pending_steps"] == ["Validate continuation summary"]
    assert update["runtime"]["completed_item_hashes"] == [_completed_item_hash("Fix skipped tests")]
    assert update["runtime"]["task_phase_id"].startswith("task-phase-")
    assert update["runtime"]["source_event_id"].startswith("compaction-event-")
    assert "Persistent task state" not in update["runtime"]["compaction_summary"]
    assert update["task_state"]["completed_steps"] == ["Fix skipped tests"]


def test_persisted_checkpoint_is_injected_before_agent() -> None:
    middleware = SessionCompactionMiddleware(max_context_tokens=200)
    update = middleware.before_agent(
        {
            "messages": [HumanMessage(content="continue")],
            "runtime": {"compaction_summary": "- Previous task state and decisions."},
        },
        None,
    )

    assert update is not None
    assert "OctoAgent long-running context checkpoint" in update["messages"][0].content
    assert update["runtime"]["continuation_mode"] == "resumed"
    assert update["runtime"]["recommended_memory_action"] == "continue"


def test_persisted_task_state_is_injected_as_checkpoint() -> None:
    middleware = SessionCompactionMiddleware(max_context_tokens=200)
    update = middleware.before_agent(
        {
            "messages": [HumanMessage(content="continue")],
            "runtime": {},
            "task_state": {
                "goal": "repair resumable execution",
                "status": "incomplete",
                "next_action": "continue from failed checkpoint",
            },
        },
        None,
    )

    assert update is not None
    assert "Persistent task state" in update["messages"][0].content
    assert "repair resumable execution" in update["messages"][0].content


def test_persisted_task_checkpoint_prevents_repeating_completed_steps() -> None:
    middleware = SessionCompactionMiddleware(max_context_tokens=200)
    update = middleware.before_agent(
        {
            "messages": [HumanMessage(content="continue")],
            "runtime": {},
            "task_state": {
                "goal": "ship long task runtime",
                "status": "active",
                "completed_steps": ["fix skipped tests"],
                "pending_steps": ["validate compaction resume"],
                "next_action": "validate compaction resume",
            },
        },
        None,
    )

    assert update is not None
    content = update["messages"][0].content
    assert "Completed items are historical evidence" in content
    assert "Resume only pending items" in content


def test_active_checkpoint_is_not_marked_as_completed_history() -> None:
    middleware = SessionCompactionMiddleware(max_context_tokens=200)
    update = middleware.before_agent(
        {
            "messages": [HumanMessage(content="continue")],
            "runtime": {"compaction_summary": "An older diagnostic step finished."},
            "task_state": {
                "goal": "repair continuation",
                "status": "active",
                "pending_steps": ["run validation"],
                "next_action": "run validation",
            },
        },
        None,
    )

    assert update is not None
    content = str(update["messages"][0].content)
    assert "【历史】 An older diagnostic step finished." in content
    assert "【历史】 - Goal: repair continuation" not in content
    assert "<active_continuation_contract>" in content
    assert "- Pending: run validation" in content


def test_compaction_preserves_tool_message_role_and_identity() -> None:
    middleware = SessionCompactionMiddleware(max_context_tokens=500, keep_recent_turns=1)
    messages = [SystemMessage(content="System prompt")]
    messages.extend(HumanMessage(content=f"old user {index} " + "x" * 300) for index in range(8))
    messages.append(ToolMessage(content="trusted tool output", name="bash", tool_call_id="call-preserve"))
    messages.extend([HumanMessage(content="latest user"), AIMessage(content="latest assistant")])

    update = middleware.before_model({"messages": messages, "runtime": {}}, None)

    assert update is not None
    tool_messages = [message for message in update["messages"] if isinstance(message, ToolMessage)]
    assert len(tool_messages) == 1
    assert tool_messages[0].name == "bash"
    assert tool_messages[0].tool_call_id == "call-preserve"


def test_continuation_cycle_context_is_persisted_to_runtime() -> None:
    middleware = SessionCompactionMiddleware(max_context_tokens=200)
    update = middleware.before_agent(
        {"messages": [HumanMessage(content="continue")], "runtime": {}},
        _Runtime(
            {
                "continue_trigger": "continue",
                "continue_cycle_id": "context-cycle-ui",
                "continue_cycle_started_at": "2026-05-12T20:10:00Z",
                "continue_cycle_base_tokens": 12345,
            }
        ),
    )

    assert update is not None
    assert update["runtime"]["context_cycle_id"] == "context-cycle-ui"
    assert update["runtime"]["context_cycle_started_at"] == "2026-05-12T20:10:00Z"
    assert update["runtime"]["context_cycle_base_tokens"] == 12345
    assert update["runtime"]["continuation_mode"] == "continued"


def test_runtime_state_preserves_continuation_cycle_markers() -> None:
    middleware = RuntimeStateMiddleware(model_name="test-model", fallback_models=[])

    update = middleware.after_model(
        {
            "messages": [HumanMessage(content="continue")],
            "runtime": {
                "context_cycle_id": "context-cycle-ui",
                "context_cycle_started_at": "2026-05-12T20:10:00Z",
                "context_cycle_base_tokens": 12345,
                "context_guard_state": "truncated",
                "recommended_memory_action": "truncate_oversized_messages",
            },
            "workflows": [],
            "workflow_events": [],
        },
        _Runtime({}),
    )

    assert update is not None
    assert update["runtime"]["context_cycle_id"] == "context-cycle-ui"
    assert update["runtime"]["context_cycle_started_at"] == "2026-05-12T20:10:00Z"
    assert update["runtime"]["context_cycle_base_tokens"] == 12345
    assert update["runtime"]["context_guard_state"] == "truncated"
    assert update["runtime"]["recommended_memory_action"] == "truncate_oversized_messages"
