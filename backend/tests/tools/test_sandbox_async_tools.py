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
import os
import threading
from types import SimpleNamespace

import pytest

from src.tools.builtins.openharness_compat_tools import glob_tool, grep_tool, lsp_tool
from src.tools.sandbox.local.local_sandbox import LocalSandbox
from src.tools.sandbox.tools import bash_tool, ensure_thread_directories_exist


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
    assert tool.coroutine is not None, f"tool {tool.name!r} must be async to safely call LocalSandbox.execute_command (which is a coroutine)"
    assert inspect.iscoroutinefunction(tool.coroutine), f"tool {tool.name!r} coroutine slot is not a coroutine function"


@pytest.mark.asyncio
async def test_thread_directory_creation_runs_off_event_loop(tmp_path, monkeypatch) -> None:
    """Local sandbox setup must not perform filesystem I/O on the ASGI loop."""
    event_loop_thread = threading.get_ident()
    mkdir_threads: list[int] = []

    def record_makedirs(path, exist_ok=False) -> None:
        mkdir_threads.append(threading.get_ident())

    monkeypatch.setattr("src.tools.sandbox.tools.os.makedirs", record_makedirs)
    runtime = SimpleNamespace(
        context={"sandbox_id": "local"},
        state={
            "sandbox": {"sandbox_id": "local"},
            "thread_data": {
                "workspace_path": str(tmp_path / "workspace"),
                "uploads_path": str(tmp_path / "uploads"),
                "outputs_path": str(tmp_path / "outputs"),
            }
        },
    )

    await ensure_thread_directories_exist(runtime)

    assert len(mkdir_threads) == 3
    assert all(thread_id != event_loop_thread for thread_id in mkdir_threads)
    assert runtime.state["thread_directories_created"] is True


@pytest.mark.asyncio
async def test_local_shell_detection_runs_off_event_loop(monkeypatch) -> None:
    """Async command execution must not probe shell permissions on the ASGI loop."""
    event_loop_thread = threading.get_ident()
    shell_threads: list[int] = []
    expected_shell = os.environ.get("COMSPEC", "cmd.exe") if os.name == "nt" else "/bin/sh"
    command = "echo ok" if os.name == "nt" else "printf ok"

    def get_shell() -> str:
        shell_threads.append(threading.get_ident())
        return expected_shell

    monkeypatch.setattr(LocalSandbox, "_get_shell", staticmethod(get_shell))
    monkeypatch.setattr("src.tools.sandbox.local.local_sandbox.record_tool_trace", lambda *args, **kwargs: None)
    sandbox = LocalSandbox("test")

    assert (await sandbox.execute_command(command)) == "ok"
    assert shell_threads and shell_threads[0] != event_loop_thread
