from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import src.agents.middlewares.skill_evolution_middleware as skill_middleware
from src.agents.middlewares.skill_evolution_middleware import SkillEvolutionMiddleware, _extract_execution_trace


def test_log_text_with_error_words_does_not_mark_tool_failed() -> None:
    trace = _extract_execution_trace(
        [
            HumanMessage(content="检查日志"),
            AIMessage(content="我会查看日志", tool_calls=[{"name": "bash", "args": {}, "id": "call-1"}]),
            ToolMessage(
                content="/var/log/auth.log\n/var/log/dgx-dashboard-service.err.log\nno critical failure found",
                name="bash",
                tool_call_id="call-1",
                status="success",
            ),
            AIMessage(content="日志检查完成，没有发现需要处理的问题。"),
        ]
    )

    assert trace.success is True
    assert trace.tools_failed == []
    assert trace.error_message == ""


def test_tool_message_error_status_marks_trace_failed() -> None:
    trace = _extract_execution_trace(
        [
            HumanMessage(content="运行命令"),
            AIMessage(content="", tool_calls=[{"name": "bash", "args": {}, "id": "call-1"}]),
            ToolMessage(content="permission denied", name="bash", tool_call_id="call-1", status="error"),
        ]
    )

    assert trace.success is False
    assert trace.tools_failed == ["bash"]
    assert trace.error_message == "permission denied"


def test_unfinished_action_announcement_marks_trace_failed() -> None:
    trace = _extract_execution_trace(
        [
            HumanMessage(content="检查系统日志"),
            AIMessage(content="现在让我检查系统日志中的错误信息："),
        ]
    )

    assert trace.success is False
    assert trace.error_message == "Assistant ended with an unfinished action announcement."


def test_sentence_ended_action_announcement_marks_trace_failed() -> None:
    trace = _extract_execution_trace(
        [
            HumanMessage(content="详细评估系统"),
            AIMessage(content="我来对OctoAgent系统进行全面的深度评估分析。首先，让我探索系统结构和各个模块的实现。"),
        ]
    )

    assert trace.success is False
    assert trace.error_message == "Assistant ended with an unfinished action announcement."


def test_raw_tool_call_text_marks_trace_failed() -> None:
    trace = _extract_execution_trace(
        [
            HumanMessage(content="查找系统核心文档和配置"),
            AIMessage(
                content=('<tool_call> <function=bash> <parameter=description> 查找系统核心文档和配置 </parameter> <parameter=command> find /mnt -name "SOUL.md" </parameter> </function> </tool_call>'),
            ),
        ]
    )

    assert trace.success is False
    assert trace.error_message == "Assistant ended with an unfinished action announcement."


def test_runtime_model_error_marks_trace_failed() -> None:
    trace = _extract_execution_trace(
        [
            HumanMessage(content="继续完成所有工作"),
            AIMessage(
                content=("我在执行这轮任务时遇到了运行时错误，当前结果不完整。\n\n错误类型：NormalizedModelError\n原始错误：Error code: 400 - {'error': {'message': 'Cannot have 2 or more assistant messages at the end of the list.'}}"),
            ),
        ]
    )

    assert trace.success is False
    assert trace.error_message == "Assistant ended with a runtime model error."


def test_tool_failure_recovered_by_final_answer_marks_trace_completed() -> None:
    trace = _extract_execution_trace(
        [
            HumanMessage(content="检查系统"),
            AIMessage(content="", tool_calls=[{"name": "bash", "args": {}, "id": "call-1"}]),
            ToolMessage(content="Error: command timed out", name="bash", tool_call_id="call-1", status="error"),
            AIMessage(content="已根据已有日志完成系统检查，结论是服务已恢复，后续无需继续调用失败命令。"),
        ]
    )

    assert trace.success is True
    assert trace.tools_failed == ["bash"]
    assert trace.error_message == ""


def test_recovery_policy_stop_after_tool_failure_remains_recoverable() -> None:
    legacy_stop_text = "".join(
        chr(code)
        for code in (
            0x5DE5,
            0x5177,
            0x8C03,
            0x7528,
            0x8FDE,
            0x7EED,
            0x5931,
            0x8D25,
            0xFF0C,
            0x5DF2,
            0x6309,
            0x6062,
            0x590D,
            0x7B56,
            0x7565,
            0x505C,
            0x6B62,
            0x7EE7,
            0x7EED,
            0x6D88,
            0x8017,
            0x5DE5,
            0x5177,
            0x8C03,
            0x7528,
            0x3002,
        )
    )
    trace = _extract_execution_trace(
        [
            HumanMessage(content="检查系统"),
            AIMessage(content="", tool_calls=[{"name": "host_shell", "args": {}, "id": "call-1"}]),
            ToolMessage(content="Error: permission denied", name="host_shell", tool_call_id="call-1", status="error"),
            AIMessage(content=legacy_stop_text),
        ]
    )

    assert trace.success is False
    assert trace.tools_failed == ["host_shell"]
    assert trace.error_message == "Tool recovery policy stopped before completing the user task."


def test_generic_recovery_policy_wording_can_be_substantive_final_answer() -> None:
    trace = _extract_execution_trace(
        [
            HumanMessage(content="repair the service"),
            AIMessage(content="", tool_calls=[{"name": "bash", "args": {}, "id": "call-1"}]),
            ToolMessage(content="Error: command timed out", name="bash", tool_call_id="call-1", status="error"),
            AIMessage(
                content=(
                    "Recovery policy requires switching to a different implementation path. I switched to the service logs, found the blocked startup step, and the safe next action is to restart only the gateway after fixing configuration."
                )
            ),
        ]
    )

    assert trace.success is True
    assert trace.tools_failed == ["bash"]
    assert trace.error_message == ""


def test_after_agent_records_recoverable_tool_failures_as_incomplete(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_append_run_record(record, *, thread_id=None, agent_name=None, run_id=None):
        captured["record"] = record
        return "record-id"

    monkeypatch.setattr(skill_middleware, "append_run_record", fake_append_run_record)
    middleware = SkillEvolutionMiddleware(tmp_path / "data", tmp_path / "skills")
    messages = [
        HumanMessage(content="repair the service"),
        AIMessage(content="", tool_calls=[{"name": "bash", "args": {}, "id": "call-1"}]),
        ToolMessage(content="Error: command timed out", name="bash", tool_call_id="call-1", status="error"),
    ]

    update = middleware.after_agent({"messages": messages, "runtime": {}}, SimpleNamespace(context={}))

    assert update is not None
    record = captured["record"]
    assert isinstance(record, dict)
    assert record["recoverable_failure"]["status"] == "recoverable"
    assert record["final_evaluation"]["status"] == "incomplete"
    assert record["final_evaluation"]["reason"] == "Error: command timed out"


def test_after_agent_records_completed_tool_batch_without_final_answer_as_incomplete(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_append_run_record(record, *, thread_id=None, agent_name=None, run_id=None):
        captured["record"] = record
        return "record-id"

    monkeypatch.setattr(skill_middleware, "append_run_record", fake_append_run_record)
    middleware = SkillEvolutionMiddleware(tmp_path / "data", tmp_path / "skills")
    messages = [
        HumanMessage(content="生成 Word 文件"),
        AIMessage(content="", tool_calls=[{"name": "present_files", "args": {}, "id": "call-1"}]),
        ToolMessage(content="Successfully presented files", name="present_files", tool_call_id="call-1"),
    ]

    update = middleware.after_agent(
        {"messages": messages, "runtime": {}, "task_state": {"goal": "生成 Word 文件", "status": "active"}},
        SimpleNamespace(context={}),
    )

    assert update is not None
    record = captured["record"]
    assert isinstance(record, dict)
    assert record["recoverable_failure"]["status"] == "recoverable"
    assert record["final_evaluation"]["status"] == "incomplete"
    assert record["final_evaluation"]["reason"] == "assistant ended after tool results without final answer"
