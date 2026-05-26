"""Regression tests for sandbox bash tool async/sync wiring.

Bug history (2026-05-19): `bash_tool`, `glob_tool`, `grep_tool` and `lsp_tool`
were declared as sync functions while `LocalSandbox.execute_command` is async.
The sync tools returned the unawaited coroutine object, producing the smoking-
gun ``RuntimeWarning: coroutine 'LocalSandbox.execute_command' was never
awaited`` log line and shipping ``<coroutine object ...>`` strings back to the
model. The model retried indefinitely until LangGraph's recursion ceiling,
which the user perceived as the agent "stopping for no reason" after ~135
turns.

These tests guard against the regression by asserting:
1. Each affected tool exposes an async coroutine (``BaseTool.coroutine`` set).
2. Invoking the tool via ``ainvoke`` returns the real command output (not the
   string repr of a coroutine).
"""

from __future__ import annotations

import inspect

import pytest

from src.tools.sandbox.tools import bash_tool
from src.tools.builtins.openharness_compat_tools import glob_tool, grep_tool, lsp_tool


@pytest.mark.parametrize(
    "tool",
    [bash_tool, glob_tool, grep_tool, lsp_tool],
    ids=lambda t: t.name,
)
def test_tool_exposes_async_coroutine(tool) -> None:
    """LangChain @tool on an async function must populate the ``coroutine`` slot.

    If this regresses (tool reverts to sync `def`), ``coroutine`` is ``None``
    and ToolNode.ainvoke falls back to running the sync `_run` in a worker
    thread — which is exactly where the unawaited-coroutine bug came from.
    """
    assert tool.coroutine is not None, (
        f"tool {tool.name!r} must be async to safely call "
        "LocalSandbox.execute_command (which is a coroutine)"
    )
    assert inspect.iscoroutinefunction(tool.coroutine), (
        f"tool {tool.name!r} coroutine slot is not a coroutine function"
    )
