"""Regression tests for ProgressStallMiddleware soft safety net.

Progress-stall recovery must never end the graph by itself. The repeated-tool
safety net is advisory only: it injects a strategy-change prompt and leaves the
run recoverable. OOM/resource guard remains the only automatic hard stop.
"""

from __future__ import annotations

import inspect

from src.agents.middlewares import progress_stall_middleware as mod
from src.agents.middlewares.progress_stall_middleware import ProgressStallMiddleware


def test_progress_stall_hooks_do_not_declare_end_jump() -> None:
    assert getattr(ProgressStallMiddleware.before_model, "__can_jump_to__", None) is None
    assert getattr(ProgressStallMiddleware.abefore_model, "__can_jump_to__", None) is None


def test_progress_stall_source_has_no_graph_end_jump() -> None:
    source = inspect.getsource(mod)
    assert '"jump_to": "end"' not in source
    assert '"jump_to": "END"' not in source
    assert "operator_hard_stop" not in source
