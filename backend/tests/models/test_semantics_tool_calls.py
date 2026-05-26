from __future__ import annotations

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from src.models.semantics import (
    _normalize_ai_message_tool_calls,
    _normalize_chat_generation_chunks,
    _normalize_streaming_chat_generation_chunks,
)


def test_xmlish_tool_call_text_is_normalized_to_tool_call() -> None:
    message = AIMessage(content=('<tool_call> <function=bash> <parameter=description> 查找系统核心文档和配置 </parameter> <parameter=command> find /mnt -name "SOUL.md" </parameter> </function> </tool_call>'))

    normalized = _normalize_ai_message_tool_calls(message)

    assert normalized.content == ""
    assert len(normalized.tool_calls) == 1
    tool_call = normalized.tool_calls[0]
    assert tool_call["name"] == "bash"
    assert tool_call["args"] == {
        "description": "查找系统核心文档和配置",
        "command": 'find /mnt -name "SOUL.md"',
    }
    assert tool_call["id"].startswith("xmlish_call_1_")
    assert tool_call["type"] == "tool_call"


def test_bare_xml_tool_tag_is_normalized_with_child_arguments() -> None:
    message = AIMessage(content=("I will write the file.\n<write_file><path>/mnt/user-data/workspace/octo_smoke_sales.csv</path><content>product,revenue\nWidget,42</content></write_file>"))

    normalized = _normalize_ai_message_tool_calls(message, allowed_tool_names={"write_file"})

    assert normalized.content == "I will write the file."
    assert normalized.tool_calls[0]["name"] == "write_file"
    assert normalized.tool_calls[0]["args"] == {
        "path": "/mnt/user-data/workspace/octo_smoke_sales.csv",
        "content": "product,revenue\nWidget,42",
        "description": "Execute write_file for the requested task.",
    }
    assert normalized.tool_calls[0]["id"].startswith("barexml_call_1_")


def test_json_tagged_tool_call_text_is_normalized() -> None:
    message = AIMessage(content=('<tool_call>{"name":"bash","arguments":{"command":"pwd","description":"check current directory"}}</tool_call>'))

    normalized = _normalize_ai_message_tool_calls(message)

    assert normalized.content == ""
    assert normalized.tool_calls[0]["name"] == "bash"
    assert normalized.tool_calls[0]["args"] == {
        "command": "pwd",
        "description": "check current directory",
    }


def test_openai_raw_additional_kwargs_tool_calls_are_normalized() -> None:
    message = AIMessage(
        content="",
        additional_kwargs={
            "tool_calls": [
                {
                    "id": "call-openai-1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"file_path":"/tmp/example.txt"}',
                    },
                }
            ]
        },
    )

    normalized = _normalize_ai_message_tool_calls(message)

    assert normalized.tool_calls == [
        {
            "name": "read_file",
            "args": {"file_path": "/tmp/example.txt"},
            "id": "call-openai-1",
            "type": "tool_call",
        }
    ]


def test_gemini_function_call_additional_kwargs_are_normalized() -> None:
    message = AIMessage(
        content="",
        additional_kwargs={
            "function_call": {
                "name": "web_search",
                "arguments": {"query": "octoagent"},
            }
        },
    )

    normalized = _normalize_ai_message_tool_calls(message)

    assert normalized.tool_calls[0]["name"] == "web_search"
    assert normalized.tool_calls[0]["args"] == {"query": "octoagent"}


def test_content_block_tool_use_is_normalized() -> None:
    message = AIMessage(
        content=[
            {"type": "text", "text": "I will inspect it."},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "ls",
                "input": {"path": "/tmp"},
            },
        ]
    )

    normalized = _normalize_ai_message_tool_calls(message)

    assert normalized.content == [{"type": "text", "text": "I will inspect it."}]
    assert normalized.tool_calls[0] == {
        "name": "ls",
        "args": {"path": "/tmp"},
        "id": "toolu_1",
        "type": "tool_call",
    }


def test_bare_tool_calls_json_is_normalized() -> None:
    message = AIMessage(
        content='{"tool_calls":[{"name":"bash","args":{"command":"date"}}]}',
    )

    normalized = _normalize_ai_message_tool_calls(message)

    assert normalized.content == ""
    assert normalized.tool_calls[0]["name"] == "bash"
    assert normalized.tool_calls[0]["args"] == {"command": "date"}


def test_tool_code_python_call_is_normalized() -> None:
    message = AIMessage(
        content="<|tool_code|>diagnostic_echo(text='OCTO_TOOL_OK')<|tool_code|>",
    )

    normalized = _normalize_ai_message_tool_calls(message)

    assert normalized.content == ""
    assert normalized.tool_calls[0]["name"] == "diagnostic_echo"
    assert normalized.tool_calls[0]["args"] == {"text": "OCTO_TOOL_OK"}
    assert normalized.tool_calls[0]["id"].startswith("toolcode_call_1_")


def test_streamed_tool_code_chunks_are_normalized() -> None:
    chunks = [
        ChatGenerationChunk(message=AIMessageChunk(content="<|tool_code|>")),
        ChatGenerationChunk(message=AIMessageChunk(content="diagnostic_echo(text='OCTO_STREAM_OK')")),
        ChatGenerationChunk(message=AIMessageChunk(content="<|tool_code|>")),
    ]

    normalized_chunks = _normalize_chat_generation_chunks(chunks)

    assert len(normalized_chunks) == 1
    message = normalized_chunks[0].message
    assert isinstance(message, AIMessageChunk)
    assert message.content == ""
    assert message.tool_calls[0]["name"] == "diagnostic_echo"
    assert message.tool_calls[0]["args"] == {"text": "OCTO_STREAM_OK"}


def test_streaming_plain_text_chunks_are_yielded_incrementally() -> None:
    advanced = False

    def source():
        nonlocal advanced
        yield ChatGenerationChunk(message=AIMessageChunk(content="流"))
        advanced = True
        yield ChatGenerationChunk(message=AIMessageChunk(content="式"))

    stream = iter(_normalize_streaming_chat_generation_chunks(source()))
    first = next(stream)

    assert first.message.content == "流"
    assert advanced is False
    assert next(stream).message.content == "式"


def test_streaming_tool_text_chunks_are_buffered_for_normalization() -> None:
    chunks = [
        ChatGenerationChunk(message=AIMessageChunk(content="<|tool_code|>")),
        ChatGenerationChunk(message=AIMessageChunk(content="diagnostic_echo(text='OCTO_STREAM_OK')")),
        ChatGenerationChunk(message=AIMessageChunk(content="<|tool_code|>")),
    ]

    normalized_chunks = list(_normalize_streaming_chat_generation_chunks(chunks))

    assert len(normalized_chunks) == 1
    message = normalized_chunks[0].message
    assert isinstance(message, AIMessageChunk)
    assert message.content == ""
    assert message.tool_calls[0]["name"] == "diagnostic_echo"
