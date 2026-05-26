from __future__ import annotations

from src.agents.core.execution_policies import evaluate_task_outcome
from src.storage.task_workspaces.contracts import TaskWorkspace, utc_now
from src.storage.task_workspaces.execution import _build_integrated_workflow_tool_response, _resolve_integrated_workflow_id


def test_resolve_integrated_workflow_id_from_prompt() -> None:
    prompt = "Call integrated_workflow_run for workflow_id ian-handdrawn-ppt."

    assert _resolve_integrated_workflow_id(prompt) == "ian-handdrawn-ppt"


def test_integrated_workflow_tool_response_uses_real_tools() -> None:
    content, tool_call_count = _build_integrated_workflow_tool_response(
        "ian-handdrawn-ppt",
        "Explain OctoAgent with a hand drawn deck.",
    )

    assert tool_call_count == 4
    assert "integrated_project_catalog" in content
    assert "load_skill" in content
    assert "integrated_workflow_run" in content


def test_status_audit_report_with_failed_items_is_completed() -> None:
    now = utc_now()
    workspace = TaskWorkspace(
        task_id="task-audit",
        name="检查并测试 skills mcp hooks 插件状态",
        mode="single",
        status="running",
        created_at=now,
        updated_at=now,
        goal="检查并测试所有 skills、mcp、hooks、插件的状态并汇总报告",
    )
    output = """
## 状态汇总报告

- skills: 通过，已验证 integrated workflow skill 能加载。
- mcp: 请求失败，当前 MCP 服务端口未监听，已记录需要修复。
- hooks: 正常，task_completed hook 可用。
- 插件 plugins: 部分插件不可用，已列出异常和下一步验证方式。

结论：系统可继续运行，但 MCP 和插件项处于 degraded 状态，需要后续处理。
"""

    status, reason = evaluate_task_outcome(workspace, output)

    assert status == "completed"
    assert reason is None
