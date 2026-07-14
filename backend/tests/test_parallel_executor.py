"""Tests for ParallelExecutor: dependency analysis, grouping, retry logic."""

from __future__ import annotations

import asyncio


def _make_executor(**overrides):
    from src.agents.core.parallel_executor import ParallelExecutor, ParallelExecutorConfig

    config = ParallelExecutorConfig(
        max_workers=4,
        per_tool_timeout=10.0,
        total_batch_timeout=60.0,
        max_retries=2,
        backoff_base=0.1,
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return ParallelExecutor(config=config)


def test_analyze_dependencies_groups_independent_calls() -> None:
    executor = _make_executor()
    tool_calls = [
        {"tool": "file_read", "args": {"path": "/tmp/a.txt"}},
        {"tool": "shell_exec", "args": {"command": "echo hello"}},
        {"tool": "web_search", "args": {"query": "test"}},
    ]
    layers = executor.analyze_dependencies(tool_calls)
    assert len(layers) >= 1
    # All three are read/exec/query - should be in same or adjacent layers
    total_calls = sum(len(layer.calls) for layer in layers)
    assert total_calls == 3


def test_analyze_dependencies_detects_write_read_dependency() -> None:
    executor = _make_executor()
    tool_calls = [
        {"tool": "file_write", "args": {"path": "/tmp/shared.txt", "content": "data"}},
        {"tool": "file_read", "args": {"path": "/tmp/shared.txt"}},
    ]
    layers = executor.analyze_dependencies(tool_calls)
    # The read should be in a later layer than the write
    write_layer_idx = None
    read_layer_idx = None
    for layer in layers:
        for call in layer.calls:
            if call.tool_name == "file_write":
                write_layer_idx = layer.layer_index
            elif call.tool_name == "file_read":
                read_layer_idx = layer.layer_index
    assert write_layer_idx is not None
    assert read_layer_idx is not None
    assert read_layer_idx > write_layer_idx


def test_execute_batch_runs_successfully_with_mock_executor() -> None:
    executor = _make_executor(max_retries=1)

    async def _fake_executor(call_dict):
        return f"ok:{call_dict['tool']}"

    tool_calls = [
        {"tool": "file_read", "args": {"path": "/tmp/x.txt"}},
        {"tool": "shell_exec", "args": {"command": "echo hi"}},
    ]

    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(executor.execute_batch(tool_calls, _fake_executor))
    finally:
        loop.close()

    assert len(results) == 2
    for r in results:
        assert r.error is None
        assert "ok:" in r.result


def test_execute_batch_handles_tool_failure_with_retry() -> None:
    executor = _make_executor(max_retries=2, backoff_base=0.01)

    call_count = 0

    async def _failing_executor(call_dict):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("simulated failure")

    tool_calls = [{"tool": "file_read", "args": {"path": "/tmp/x.txt"}}]

    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(executor.execute_batch(tool_calls, _failing_executor))
    finally:
        loop.close()

    assert len(results) == 1
    assert results[0].error is not None
    assert "simulated failure" in results[0].error
    assert call_count >= 2


def test_execute_batch_empty_input_returns_empty() -> None:
    executor = _make_executor()

    async def _executor(call_dict):
        return "ok"

    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(executor.execute_batch([], _executor))
    finally:
        loop.close()

    assert results == []


def test_handle_failure_returns_correct_action_for_timeout() -> None:
    from src.agents.core.parallel_executor import CallResult

    executor = _make_executor()
    result = CallResult(
        index=0,
        tool_name="shell_exec",
        args={"command": "sleep 100"},
        result=None,
        error="Tool timed out after 10s",
        attempts=1,
    )
    action = executor.handle_failure(result)
    assert action["action"] == "retry_with_timeout_increase"


def test_handle_failure_returns_correct_action_for_not_found() -> None:
    from src.agents.core.parallel_executor import CallResult

    executor = _make_executor()
    result = CallResult(
        index=0,
        tool_name="file_read",
        args={"path": "/nonexistent"},
        result=None,
        error="No such file or directory",
        attempts=1,
    )
    action = executor.handle_failure(result)
    assert action["action"] == "retry_with_path_check"


def test_handle_failure_returns_correct_action_for_permission() -> None:
    from src.agents.core.parallel_executor import CallResult

    executor = _make_executor()
    result = CallResult(
        index=0,
        tool_name="shell_exec",
        args={"command": "cat /etc/shadow"},
        result=None,
        error="Permission denied",
        attempts=1,
    )
    action = executor.handle_failure(result)
    assert action["action"] == "retry_with_sudo"


def test_handle_failure_no_error_returns_none() -> None:
    from src.agents.core.parallel_executor import CallResult

    executor = _make_executor()
    result = CallResult(
        index=0,
        tool_name="file_read",
        args={"path": "/tmp/x"},
        result="content",
        error=None,
        attempts=1,
    )
    action = executor.handle_failure(result)
    assert action["action"] == "none"


def test_classify_tool_returns_expected_categories() -> None:
    from src.agents.core.tool_dependency import ToolCategory, classify_tool

    assert classify_tool("file_write") == ToolCategory.WRITE
    assert classify_tool("file_read") == ToolCategory.READ
    assert classify_tool("shell_exec") == ToolCategory.EXEC
    assert classify_tool("web_search") == ToolCategory.QUERY
    assert classify_tool("unknown_tool") == ToolCategory.READ


def test_group_calls_by_category_separates_writes_from_reads() -> None:
    from src.agents.core.tool_dependency import analyze_tool_calls, group_calls_by_category

    tool_calls = [
        {"tool": "file_write", "args": {"path": "/tmp/a.txt"}},
        {"tool": "file_read", "args": {"path": "/tmp/b.txt"}},
        {"tool": "shell_exec", "args": {"command": "ls"}},
    ]
    layers = analyze_tool_calls(tool_calls)
    groups = group_calls_by_category(layers)

    assert "write" in groups
    assert "read" in groups or "exec" in groups
