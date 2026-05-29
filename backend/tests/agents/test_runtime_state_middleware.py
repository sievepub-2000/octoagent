from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from src.agents.middlewares.runtime_state_middleware import (
    _merge_run_events,
    _normalize_run_event,
    _synthesize_run_events_from_messages,
)


def test_synthesizes_tool_call_and_result_run_events() -> None:
    events = _synthesize_run_events_from_messages(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-1",
                        "name": "bash",
                        "args": {"command": "printf hello"},
                    }
                ],
            ),
            ToolMessage(content="hello", tool_call_id="call-1", name="bash"),
        ],
        run_id="thread-1",
    )

    assert [event["kind"] for event in events] == ["tool_call", "tool_result"]
    assert events[0]["taskId"] == "call-1"
    assert events[0]["runId"] == "thread-1"
    assert events[1]["level"] == "success"


def test_synthesizes_tool_error_run_event() -> None:
    events = _synthesize_run_events_from_messages(
        [ToolMessage(content="boom", tool_call_id="call-2", name="bash", status="error")],
        run_id="thread-1",
    )

    assert events[0]["kind"] == "error"
    assert events[0]["level"] == "error"
    assert events[0]["taskId"] == "call-2"


def test_merge_run_events_dedupes_and_keeps_newest_first() -> None:
    existing = [
        {
            "id": "run-event-tool-call-call-1",
            "kind": "tool_call",
            "title": "Calling bash",
            "created_at": "2026-05-29T00:00:00Z",
            "level": "info",
            "task_id": "call-1",
        }
    ]
    incoming = [
        {
            "id": "run-event-tool-call-call-1",
            "kind": "tool_call",
            "title": "Calling bash",
            "createdAt": "2026-05-29T00:00:00Z",
            "level": "info",
            "taskId": "call-1",
        },
        {
            "id": "run-event-tool-result-call-1",
            "kind": "tool_result",
            "title": "bash finished",
            "createdAt": "2026-05-29T00:00:01Z",
            "level": "success",
            "taskId": "call-1",
        },
    ]

    merged = _merge_run_events(existing, incoming)

    assert [event["id"] for event in merged] == [
        "run-event-tool-result-call-1",
        "run-event-tool-call-call-1",
    ]
    assert merged[1]["createdAt"] == "2026-05-29T00:00:00Z"


def test_normalize_rejects_unknown_run_event_kind() -> None:
    assert _normalize_run_event({"kind": "not-real", "title": "Nope"}) is None
