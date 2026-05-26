from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.middleware.types import ModelResponse
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from src.agents.middlewares.dangling_tool_call_middleware import DanglingToolCallMiddleware


class BindableFakeChatModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[override]
        return self


def _xmlish_call(command: str = 'find /mnt -name "SOUL.md"') -> str:
    return f"<tool_call> <function=bash> <parameter=description> 查找系统核心文档和配置 </parameter> <parameter=command> {command} </parameter> </function> </tool_call>"


def test_xmlish_assistant_history_is_normalized_and_patched() -> None:
    middleware = DanglingToolCallMiddleware()
    messages = [
        HumanMessage(content="继续完成所有工作"),
        AIMessage(content=_xmlish_call()),
        AIMessage(content=_xmlish_call("ls -la /root/.config/octoagent/")),
        AIMessage(content="我在执行这轮任务时遇到了运行时错误，当前结果不完整。"),
    ]

    patched = middleware._build_patched_messages(messages)

    assert patched is not None
    ai_with_tools = [msg for msg in patched if isinstance(msg, AIMessage) and msg.tool_calls]
    tool_results = [msg for msg in patched if isinstance(msg, ToolMessage)]
    assert len(ai_with_tools) == 2
    assert len(tool_results) == 2
    assert ai_with_tools[0].content == ""
    assert ai_with_tools[1].content == ""
    assert ai_with_tools[0].tool_calls[0]["id"] != ai_with_tools[1].tool_calls[0]["id"]
    assert tool_results[0].status == "error"
    assert tool_results[1].status == "error"
    assert [message.type for message in patched[-2:]] == ["system", "human"]


def test_consecutive_runtime_error_tail_is_repaired_before_model_call() -> None:
    middleware = DanglingToolCallMiddleware()
    runtime_error = "我在执行这轮任务时遇到了运行时错误，当前结果不完整。\n\n错误类型：NormalizedModelError\n原始错误：Error code: 400 - {'error': {'message': 'Cannot have 2 or more assistant messages at the end of the list.'}}"
    messages = [
        HumanMessage(content="继续完成所有工作"),
        AIMessage(content=runtime_error),
        AIMessage(content=runtime_error),
        AIMessage(content=runtime_error),
    ]

    patched = middleware._build_patched_messages(messages)

    assert patched is not None
    assert [message.type for message in patched[-2:]] == ["system", "human"]
    assert "message contract repair" in patched[-2].content
    assert "Continue the latest unfinished user task" in patched[-1].content


def test_single_runtime_error_tail_is_repaired_before_model_call() -> None:
    middleware = DanglingToolCallMiddleware()
    messages = [
        HumanMessage(content="继续完成所有工作"),
        AIMessage(content="我在执行这轮任务时遇到了运行时错误，当前结果不完整。\n错误类型：NormalizedModelError"),
    ]

    patched = middleware._build_patched_messages(messages)

    assert patched is not None
    assert [message.type for message in patched[-2:]] == ["system", "human"]


def test_xmlish_model_response_is_normalized_before_graph_state() -> None:
    middleware = DanglingToolCallMiddleware()
    response = ModelResponse(result=[AIMessage(content=_xmlish_call())])

    normalized = middleware._normalize_response(response)

    assert len(normalized.result) == 1
    message = normalized.result[0]
    assert isinstance(message, AIMessage)
    assert message.content == ""
    assert message.tool_calls[0]["name"] == "bash"
    assert message.tool_calls[0]["args"]["command"] == 'find /mnt -name "SOUL.md"'


def test_xmlish_model_response_invokes_real_tool() -> None:
    calls: list[tuple[str, str]] = []

    @tool
    def bash(description: str, command: str) -> str:
        """Record command execution for regression testing."""
        calls.append((description, command))
        return f"executed:{command}"

    model = BindableFakeChatModel(
        responses=[
            AIMessage(content=_xmlish_call()),
            AIMessage(content="完成"),
        ]
    )
    agent = create_agent(model=model, tools=[bash], middleware=[DanglingToolCallMiddleware()])

    result = agent.invoke({"messages": [{"role": "user", "content": "查找"}]})

    assert calls == [("查找系统核心文档和配置", 'find /mnt -name "SOUL.md"')]
    messages = result["messages"]
    assert messages[1].type == "ai"
    assert messages[1].tool_calls
    assert messages[1].content == ""
    assert messages[2].type == "tool"
    assert messages[2].name == "bash"
    assert messages[2].content == 'executed:find /mnt -name "SOUL.md"'
