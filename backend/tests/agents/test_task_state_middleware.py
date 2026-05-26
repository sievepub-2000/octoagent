from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agents.middlewares.task_state_middleware import TaskStateMiddleware


class _Runtime:
    def __init__(self, context: dict[str, object] | None = None) -> None:
        self.context = context or {}


def test_complex_task_creates_and_injects_checkpoint() -> None:
    middleware = TaskStateMiddleware()
    messages = [HumanMessage(content="请分析系统问题，修复上下文压缩，并完成测试验证。")]

    update = middleware.before_agent({"messages": messages, "runtime": {}}, _Runtime())

    assert update is not None
    assert update["task_state"]["status"] == "active"
    assert update["runtime"]["task_state_status"] == "active"
    assert any(isinstance(message, SystemMessage) and "OctoAgent persistent task state" in str(message.content) for message in update["messages"])


def test_after_agent_marks_unfinished_action_as_recoverable() -> None:
    middleware = TaskStateMiddleware()
    state = {
        "messages": [
            HumanMessage(content="请完整排查并修复系统问题。"),
            AIMessage(content="现在让我检查系统日志中的错误信息："),
        ],
        "runtime": {},
        "task_state": {
            "goal": "请完整排查并修复系统问题。",
            "status": "active",
        },
    }

    update = middleware.after_agent(state, _Runtime())

    assert update is not None
    assert update["task_state"]["status"] == "incomplete"
    assert update["runtime"]["recoverable_failure"]["status"] == "recoverable"
    assert update["runtime"]["recommended_memory_action"] == "continue"


def test_after_agent_carries_tool_failures_into_task_state() -> None:
    middleware = TaskStateMiddleware()
    state = {
        "messages": [
            HumanMessage(content="请研究公开资料并完成报告。"),
            ToolMessage(
                content="Error: low-quality webpage extraction for https://github.com/x/y",
                name="read_webpage",
                tool_call_id="call-1",
                status="error",
            ),
            AIMessage(content="工具调用连续失败，已按恢复策略停止继续消耗工具调用。"),
        ],
        "runtime": {},
        "task_state": {
            "goal": "请研究公开资料并完成报告。",
            "status": "active",
        },
    }

    update = middleware.after_agent(state, _Runtime())

    assert update is not None
    assert update["task_state"]["status"] == "incomplete"
    assert "read_webpage" in update["task_state"]["failed_attempts"][0]
    assert update["runtime"]["incomplete_state"]["status"] == "recoverable"


def test_completed_todos_are_removed_from_pending_after_compaction_resume() -> None:
    middleware = TaskStateMiddleware()
    state = {
        "messages": [
            HumanMessage(content="continue the long task"),
            AIMessage(content="I completed environment audit and will continue with dependency verification."),
        ],
        "runtime": {"context_guard_state": "compacted"},
        "task_state": {
            "goal": "repair long running agent execution",
            "status": "active",
            "completed_steps": ["audit environment"],
            "pending_steps": ["audit environment", "verify dependencies"],
            "next_action": "audit environment",
        },
        "todos": [
            {"content": "audit environment", "status": "completed"},
            {"content": "audit environment", "status": "pending"},
            {"content": "verify dependencies", "status": "pending"},
        ],
    }

    update = middleware.after_agent(state, _Runtime({"thread_id": "thread-repeat"}))

    assert update is not None
    assert update["task_state"]["completed_steps"] == ["audit environment"]
    assert update["task_state"]["pending_steps"] == ["verify dependencies"]
    assert update["task_state"]["current_step"] == "verify dependencies"
    assert update["task_state"]["next_action"] == "verify dependencies"


def test_task_checkpoint_marks_completed_steps_as_non_repeatable() -> None:
    middleware = TaskStateMiddleware()
    state = {
        "messages": [HumanMessage(content="continue")],
        "runtime": {},
        "task_state": {
            "goal": "repair continuation",
            "status": "active",
            "completed_steps": ["write regression test"],
            "pending_steps": ["run validation"],
            "next_action": "run validation",
        },
    }

    update = middleware.before_agent(state, _Runtime())

    assert update is not None
    checkpoint = next(message for message in update["messages"] if isinstance(message, SystemMessage))
    assert "Completed steps are historical evidence only" in str(checkpoint.content)
    assert "Continue only pending steps" in str(checkpoint.content)

def test_new_complex_user_goal_replaces_stale_task_state() -> None:
    middleware = TaskStateMiddleware()
    new_goal = "如果我有一台服务器4核心24g内存，arm服务器ubuntu系统，可以接cloude flare分发cdn，那么以此服务器为基础，你建议我做什么服务最快赚钱？具体怎样部署？"
    state = {
        "messages": [
            HumanMessage(content="帮我分析全球无人值守 SaaS 行业。"),
            AIMessage(content="已完成 SaaS 行业分析。"),
            HumanMessage(content=new_goal),
        ],
        "runtime": {},
        "task_state": {
            "goal": "帮我分析全球无人值守 SaaS 行业。",
            "status": "completed",
            "completed_steps": ["调研全球SaaS市场规模和增长趋势数据"],
            "pending_steps": [],
        },
    }

    update = middleware.before_agent(state, _Runtime())

    assert update is not None
    assert update["task_state"]["goal"] == new_goal
    assert update["task_state"]["status"] == "active"
    assert update["task_state"]["pending_steps"] == [new_goal]


def test_think_only_answer_keeps_task_recoverable_despite_completed_todos() -> None:
    middleware = TaskStateMiddleware()
    state = {
        "messages": [
            HumanMessage(content="请给出服务器最快赚钱服务和部署方案。"),
            AIMessage(content="<think>\n\n</think>\n\n"),
        ],
        "runtime": {},
        "task_state": {
            "goal": "请给出服务器最快赚钱服务和部署方案。",
            "status": "active",
        },
        "todos": [{"content": "给出部署方案", "status": "completed"}],
    }

    update = middleware.after_agent(state, _Runtime())

    assert update is not None
    assert update["task_state"]["status"] == "incomplete"
    assert update["runtime"]["recoverable_failure"]["reason"] == "assistant produced no user-visible final answer"


def test_tool_failure_final_keeps_task_incomplete() -> None:
    middleware = TaskStateMiddleware()
    state = {
        "messages": [HumanMessage(content="请联网分析并给结论。"), AIMessage(content="工具调用连续失败，已按恢复策略停止继续消耗工具调用。")],
        "runtime": {},
        "task_state": {"goal": "请联网分析并给结论。", "status": "active"},
        "todos": [{"content": "调研资料", "status": "completed"}],
    }

    update = middleware.after_agent(state, _Runtime())

    assert update is not None
    assert update["task_state"]["status"] == "incomplete"

def test_substantive_advisory_answer_completes_task_state_without_todos() -> None:
    middleware = TaskStateMiddleware()
    goal = "如果我有一台服务器4核心24g内存，arm服务器ubuntu系统，可以接cloude flare分发cdn，那么以此服务器为基础，你建议我做什么服务最快赚钱？具体怎样部署？"
    answer = (
        "基于你的4核24G ARM Ubuntu服务器和Cloudflare CDN，推荐优先做轻量级AI应用网关。"
        "具体部署方案如下：第一步安装Docker和Nginx，第二步用FastAPI提供API鉴权和限流，"
        "第三步用Cloudflare Workers做入口保护、缓存和订阅校验，第四步接入Stripe或Paddle收费。"
        "赚钱路径是先做垂直场景SaaS，提供免费试用，然后按月订阅。"
        "同时可以备选部署静态资源CDN节点和RSS聚合服务，但首选方案变现最快、部署步骤最短。"
        "上线后先做一个MVP页面、支付回调、用户额度表、日志告警和备份脚本，逐步验证转化率。"
    )
    state = {
        "messages": [HumanMessage(content=goal), AIMessage(content=answer)],
        "runtime": {},
        "task_state": {"goal": goal, "status": "active", "pending_steps": [goal]},
    }

    update = middleware.after_agent(state, _Runtime({"thread_id": "advisory-complete"}))

    assert update is not None
    assert update["task_state"]["status"] == "completed"
    assert update["task_state"]["pending_steps"] == []
    assert update["runtime"]["recoverable_failure"] is None
