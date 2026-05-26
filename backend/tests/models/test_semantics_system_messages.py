from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.models.semantics import ModelSemanticProfile, ModelSemanticTranslator, _invocation_tool_names, _normalize_ai_message_tool_calls


def test_normalize_messages_merges_runtime_system_messages_at_front() -> None:
    translator = ModelSemanticTranslator()
    messages = [
        HumanMessage(content="start"),
        SystemMessage(content="runtime checkpoint"),
        AIMessage(content="working"),
        ToolMessage(content="tool result", tool_call_id="call-1"),
        SystemMessage(content="tool budget guidance"),
        HumanMessage(content="continue"),
    ]

    normalized = translator.normalize_messages(messages, ModelSemanticProfile())

    assert [message.type for message in normalized] == ["system", "human", "ai", "tool", "human"]
    assert normalized[0].content == "runtime checkpoint\n\ntool budget guidance"
    assert [message.content for message in normalized[1:]] == ["start", "working", "tool result", "continue"]


def test_normalize_messages_keeps_existing_leading_system_message_when_already_valid() -> None:
    translator = ModelSemanticTranslator()
    messages = [SystemMessage(content="primary"), HumanMessage(content="hello")]

    normalized = translator.normalize_messages(messages, ModelSemanticProfile())

    assert normalized == messages


def test_normalize_messages_adds_human_when_provider_payload_has_no_user_query() -> None:
    translator = ModelSemanticTranslator()
    messages = [SystemMessage(content="runtime only"), AIMessage(content="prior assistant state")]

    normalized = translator.normalize_messages(messages, ModelSemanticProfile())

    assert [message.type for message in normalized] == ["system", "ai", "human"]
    assert "No explicit user message" in str(normalized[-1].content)


def test_normalize_messages_adds_human_to_system_only_payload() -> None:
    translator = ModelSemanticTranslator()
    messages = [SystemMessage(content="runtime only")]

    normalized = translator.normalize_messages(messages, ModelSemanticProfile())

    assert [message.type for message in normalized] == ["system", "human"]
    assert "Continue the current task" in str(normalized[-1].content)


def test_normalize_messages_repairs_consecutive_assistant_tail() -> None:
    translator = ModelSemanticTranslator()
    messages = [
        HumanMessage(content="finish the tool audit"),
        AIMessage(content="partial report"),
        AIMessage(content="我在执行这轮任务时遇到了运行时错误，当前结果不完整。"),
    ]

    normalized = translator.normalize_messages(messages, ModelSemanticProfile())

    assert [message.type for message in normalized] == ["human", "ai", "ai", "human"]
    assert "multiple assistant messages" in str(normalized[-1].content)


def test_normalize_ai_message_parses_trailing_json_tool_request() -> None:
    message = AIMessage(
        content=(
            "我将先测试 bash 工具。\n\n"
            '{"tool":"bash","arguments":{"command":"echo ok","description":"smoke test"}}'
        )
    )

    normalized = _normalize_ai_message_tool_calls(message, allowed_tool_names={"bash"})

    assert normalized.content == "我将先测试 bash 工具。"
    assert normalized.tool_calls == [
        {
            "name": "bash",
            "args": {"command": "echo ok", "description": "smoke test"},
            "id": normalized.tool_calls[0]["id"],
            "type": "tool_call",
        }
    ]


def test_normalize_ai_message_parses_document_json_tool_request() -> None:
    message = AIMessage(content='{"tool":"ls","arguments":{"path":"."}}')

    normalized = _normalize_ai_message_tool_calls(message, allowed_tool_names={"ls"})

    assert normalized.content == ""
    assert normalized.tool_calls[0]["name"] == "ls"
    assert normalized.tool_calls[0]["args"] == {"path": "."}


def test_normalize_ai_message_does_not_parse_unknown_trailing_tool_request() -> None:
    message = AIMessage(content='Ready.\n\n{"tool":"not_registered","arguments":{"value":1}}')

    normalized = _normalize_ai_message_tool_calls(message, allowed_tool_names={"bash"})

    assert normalized == message


def test_normalize_ai_message_does_not_parse_report_json_without_tool_shape() -> None:
    message = AIMessage(content='报告：\n\n{"tool":"bash","status":"passed"}')

    normalized = _normalize_ai_message_tool_calls(message, allowed_tool_names={"bash"})

    assert normalized == message


def test_invocation_tool_names_reads_provider_tool_schema() -> None:
    names = _invocation_tool_names(
        None,
        {
            "tools": [
                {"type": "function", "function": {"name": "bash"}},
                {"name": "read_file"},
            ]
        },
    )

    assert names == {"bash", "read_file"}
