from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agents.core.run_records import build_execution_run_record


def test_run_record_rejects_think_only_final_message() -> None:
    record = build_execution_run_record(
        {
            "messages": [HumanMessage(content="请继续完成任务"), AIMessage(content="<think>\n\n</think>\n\n")],
            "runtime": {},
            "task_state": {"goal": "请继续完成任务", "status": "active"},
        }
    )

    assert record["final_evaluation"]["status"] == "incomplete"
    assert record["final_evaluation"]["reason"] == "assistant produced no user-visible final answer"
    assert record["final_evaluation"]["final_message_preview"] == ""


def test_run_record_marks_visible_completed_answer_completed() -> None:
    record = build_execution_run_record(
        {
            "messages": [HumanMessage(content="请分析"), AIMessage(content="结论：推荐先做轻量 API 网关。")],
            "runtime": {},
            "task_state": {"goal": "请分析", "status": "completed"},
        }
    )

    assert record["final_evaluation"]["status"] == "completed"
    assert "轻量 API 网关" in record["final_evaluation"]["final_message_preview"]


def test_run_record_aligns_active_task_state_when_explicitly_completed() -> None:
    record = build_execution_run_record(
        {
            "messages": [HumanMessage(content="请给建议"), AIMessage(content="建议：优先做AI网关。具体部署步骤是先装Docker，再接Cloudflare。")],
            "runtime": {},
            "task_state": {"goal": "请给建议", "status": "active", "pending_steps": ["请给建议"]},
        },
        final_status="completed",
    )

    assert record["final_evaluation"]["status"] == "completed"
    assert record["task_state"]["status"] == "completed"
    assert record["task_state"]["pending_steps"] == []


def test_run_record_marks_completed_tool_batch_without_final_answer_incomplete() -> None:
    record = build_execution_run_record(
        {
            "messages": [
                HumanMessage(content="生成 Word 文件"),
                AIMessage(content="", tool_calls=[{"name": "present_files", "args": {}, "id": "call-1"}]),
                ToolMessage(content="Successfully presented files", name="present_files", tool_call_id="call-1"),
                SystemMessage(content="<step_review>下一条助理消息必须复盘并给最终回复</step_review>"),
            ],
            "runtime": {},
            "task_state": {"goal": "生成 Word 文件", "status": "active"},
        }
    )

    assert record["final_evaluation"]["status"] == "incomplete"
    assert record["final_evaluation"]["reason"] == "assistant ended after tool results without final answer"
    assert record["final_evaluation"]["final_message_preview"] == ""
