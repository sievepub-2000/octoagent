"""Shared pytest fixtures for OctoAgent backend tests."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Provide a temporary directory that mimics a workspace root."""
    (tmp_path / "files").mkdir()
    (tmp_path / "logs").mkdir()
    return tmp_path


@pytest.fixture
def mock_llm_response():
    """Return a fake LLM response object with tool_calls."""

    class FakeToolCall:
        def __init__(self, name: str, args: dict[str, Any]) -> None:
            self.name = name
            self.args = args
            self.id = f"call_{name}"

    class FakeMessage:
        type = "ai"
        content = ""
        tool_calls: list[FakeToolCall] = []

    msg = FakeMessage()
    msg.tool_calls = [
        FakeToolCall("file_read", {"path": "/tmp/test.txt"}),
        FakeToolCall("shell_exec", {"command": "echo hello"}),
    ]
    return msg


@pytest.fixture
def mock_tool():
    """Return a fake langchain tool."""

    class FakeTool:
        name = "fake_tool"
        description = "A fake tool for testing."
        args_schema = None
        metadata: dict[str, Any] = {}

        async def ainvoke(self, args: dict[str, Any]) -> str:
            return f"result for {args}"

        def invoke(self, args: dict[str, Any]) -> str:
            return f"result for {args}"

    return FakeTool()


@pytest.fixture
def mock_executor_fn():
    """Return a fake async executor function that returns predictable results."""

    async def _executor(call_dict: dict[str, Any]) -> str:
        tool = call_dict.get("tool", "unknown")
        args = call_dict.get("args", {})
        return f"executed:{tool}:{args}"

    return _executor


@pytest.fixture
def any_loop(request: pytest.FixtureRequest) -> asyncio.AbstractEventLoop:
    """Provide an event loop for async test helpers."""
    loop = asyncio.new_event_loop()
    request.addfinalizer(loop.close)
    return loop


@pytest.fixture
def sample_messages():
    """Return a list of simple message dicts for compressor tests."""
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

    return [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="Hello, help me write a file."),
        AIMessage(content="I will create the file for you. tool_call: create file at /tmp/test.txt"),
        HumanMessage(content="Now read it back."),
        AIMessage(content="Reading the file now. tool_call: read /tmp/test.txt"),
    ]


@pytest.fixture
def sample_tool_calls() -> list[dict[str, Any]]:
    """Return a set of tool calls with varying dependencies for parallel executor tests."""
    return [
        {"tool": "file_read", "args": {"path": "/tmp/a.txt"}},
        {"tool": "shell_exec", "args": {"command": "echo hello"}},
        {"tool": "web_search", "args": {"query": "test"}},
        {"tool": "file_write", "args": {"path": "/tmp/b.txt", "content": "data"}},
        {"tool": "file_read", "args": {"path": "/tmp/b.txt"}},
    ]
