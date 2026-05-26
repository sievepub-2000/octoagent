from __future__ import annotations

from datetime import UTC, datetime, timedelta

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from src.agents.middlewares.execution_review_middleware import ExecutionReviewMiddleware


def _old_timestamp() -> str:
    return (datetime.now(UTC) - timedelta(minutes=6)).isoformat()


def test_compaction_flag_triggers_execution_review() -> None:
    middleware = ExecutionReviewMiddleware()
    messages = [HumanMessage(content="继续完成系统修复")]

    update = middleware.before_model(
        {
            "messages": messages,
            "runtime": {
                "task_review_required": True,
                "context_guard_state": "compacted",
            },
            "task_state": {
                "status": "active",
                "current_step": "verify compaction",
                "next_action": "continue implementation",
            },
        },
        None,
    )

    assert update is not None
    assert update["runtime"]["task_review_required"] is False
    assert update["runtime"]["execution_review_last_reasons"] == ["context_compaction"]
    assert any("execution_review_middleware" in message.content for message in update["messages"] if isinstance(message, SystemMessage))


def test_tool_error_triggers_soft_review_without_end_jump() -> None:
    middleware = ExecutionReviewMiddleware()
    messages = [
        HumanMessage(content="检查执行结果"),
        ToolMessage(content="Error: command timed out", name="shell", tool_call_id="call-1", status="error"),
    ]

    update = middleware.before_model({"messages": messages, "runtime": {}, "task_state": {"status": "active"}}, None)

    assert update is not None
    assert update["runtime"]["execution_review_last_reasons"] == ["tool_error"]
    assert "jump_to" not in update
    assert "不要把任务直接交回用户" in update["messages"][0].content


def test_five_minute_active_task_timeout_triggers_review() -> None:
    middleware = ExecutionReviewMiddleware()
    messages = [HumanMessage(content="长期任务"), ToolMessage(content="ok", name="shell", tool_call_id="call-1")]

    update = middleware.before_model(
        {
            "messages": messages,
            "runtime": {"execution_review_last_at": _old_timestamp()},
            "task_state": {"status": "active", "current_step": "running validation"},
        },
        None,
    )

    assert update is not None
    assert update["runtime"]["execution_review_last_reasons"] == ["timeout_5m"]


def test_research_closure_suppresses_execution_review_message() -> None:
    middleware = ExecutionReviewMiddleware()
    messages = [HumanMessage(content="研究内容订阅"), ToolMessage(content="evidence", name="web_fetch", tool_call_id="call-1")]

    update = middleware.before_model(
        {
            "messages": messages,
            "runtime": {
                "execution_review_last_at": _old_timestamp(),
                "research_closure": {"status": "must_finalize"},
            },
            "task_state": {"status": "active", "current_step": "finalize report"},
        },
        None,
    )

    assert update is not None
    assert "messages" not in update
    assert update["runtime"]["execution_review_status"] == "suppressed_for_research_closure"
    assert update["runtime"]["self_feedback_action"] == "produce_final_answer_from_existing_evidence"


def test_first_pass_initializes_review_timer_without_injecting_message() -> None:
    middleware = ExecutionReviewMiddleware()
    messages = [HumanMessage(content="short task")]

    update = middleware.before_model({"messages": messages, "runtime": {}, "task_state": {"status": "active"}}, None)

    assert update is not None
    assert update["runtime"]["execution_review_started_at"]
    assert "messages" not in update
