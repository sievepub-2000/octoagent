"""Research-closure compatibility checks for the active middlewares."""

from __future__ import annotations

import importlib


def _execution_module():
    return importlib.import_module(
        "src.agents.middlewares.execution_middleware"
    )


def _step_reflection_module():
    return importlib.import_module(
        "src.agents.middlewares.step_reflection_middleware"
    )


def test_closure_inactive_on_empty_runtime():
    mod = _execution_module()
    assert mod._research_closure_active({}) is False
    assert mod._research_closure_active({"research_closure": None}) is False
    # A non-dict closure must be ignored.
    assert mod._research_closure_active({"research_closure": "must_finalize"}) is False


def test_closure_only_triggers_on_must_finalize_status():
    mod = _execution_module()
    assert (
        mod._research_closure_active({"research_closure": {"status": "must_finalize"}})
        is True
    )
    # Adjacent statuses must NOT trigger closure (the bug class the hotfix
    # closed).
    for status in ("active", "finalized", "pending", "draft", ""):
        runtime = {"research_closure": {"status": status}}
        assert mod._research_closure_active(runtime) is False, (
            f"closure should not trigger on status={status!r}"
        )


def test_closure_helper_in_step_reflection_matches_execution_middleware():
    """The two middlewares ship parallel helpers; both must agree on
    when the closure short-circuit is active, otherwise the agent
    pipeline drifts into inconsistent finalisation behaviour."""
    exec_mod = _execution_module()
    step_mod = _step_reflection_module()

    closure_state = {"runtime": {"research_closure": {"status": "must_finalize"}}}
    assert step_mod._research_closure_active(closure_state) is True
    assert (
        exec_mod._research_closure_active(closure_state["runtime"])
        is True
    )

    inactive_state = {"runtime": {"research_closure": {"status": "active"}}}
    assert step_mod._research_closure_active(inactive_state) is False
    assert (
        exec_mod._research_closure_active(inactive_state["runtime"])
        is False
    )
