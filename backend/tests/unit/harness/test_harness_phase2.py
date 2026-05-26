"""Unit tests for src.harness.{hooks,budget,run_journal}.

Pure-Python, no external services.
"""

from __future__ import annotations

import asyncio

from src.harness.hooks import (
    HookContext,
    HookEvent,
    HookExecutor,
    HookRegistry,
    HookResult,
)

# --------------------- hooks ---------------------


def test_registry_register_and_get_ordered():
    reg = HookRegistry()
    calls: list[str] = []

    def low(_ctx: HookContext) -> HookResult:
        calls.append("low")
        return HookResult(hook_name="low", event=HookEvent.AFTER_MODEL)

    def high(_ctx: HookContext) -> HookResult:
        calls.append("high")
        return HookResult(hook_name="high", event=HookEvent.AFTER_MODEL)

    reg.register(HookEvent.AFTER_MODEL, low, priority=1)
    reg.register(HookEvent.AFTER_MODEL, high, priority=10)
    names = [h.name for h in reg.get(HookEvent.AFTER_MODEL)]
    assert names == ["high", "low"]


def test_executor_aggregates_state_updates():
    reg = HookRegistry()
    reg.register(
        HookEvent.AFTER_MODEL,
        lambda _c: HookResult(hook_name="a", event=HookEvent.AFTER_MODEL, state_update={"messages": ["m1"]}),
    )
    reg.register(
        HookEvent.AFTER_MODEL,
        lambda _c: HookResult(hook_name="b", event=HookEvent.AFTER_MODEL, state_update={"messages": ["m2"], "x": 1}),
    )
    ex = HookExecutor(reg)
    ctx = HookContext(event=HookEvent.AFTER_MODEL, state={})
    agg = ex.run_sync(ctx)
    merged = agg.merged_state_update()
    assert merged is not None
    assert merged["messages"] == ["m1", "m2"]
    assert merged["x"] == 1
    assert not agg.blocked


def test_executor_block_short_circuits():
    reg = HookRegistry()
    seen: list[str] = []

    def a(_c: HookContext) -> HookResult:
        seen.append("a")
        return HookResult(hook_name="a", event=HookEvent.AFTER_MODEL, block=True, reason="nope")

    def b(_c: HookContext) -> HookResult:
        seen.append("b")
        return HookResult(hook_name="b", event=HookEvent.AFTER_MODEL)

    reg.register(HookEvent.AFTER_MODEL, a, priority=10)
    reg.register(HookEvent.AFTER_MODEL, b, priority=1)
    agg = HookExecutor(reg).run_sync(HookContext(event=HookEvent.AFTER_MODEL, state={}))
    assert seen == ["a"]
    assert agg.blocked
    assert agg.reason == "nope"


def test_executor_async_path():
    reg = HookRegistry()

    async def a(_c: HookContext) -> HookResult:
        await asyncio.sleep(0)
        return HookResult(hook_name="a", event=HookEvent.AFTER_MODEL, state_update={"messages": ["async"]})

    reg.register(HookEvent.AFTER_MODEL, a)
    agg = asyncio.run(HookExecutor(reg).run(HookContext(event=HookEvent.AFTER_MODEL, state={})))
    assert agg.merged_state_update() == {"messages": ["async"]}


def test_hook_exception_does_not_propagate():
    reg = HookRegistry()

    def boom(_c: HookContext) -> HookResult:
        raise RuntimeError("kaboom")

    reg.register(HookEvent.AFTER_MODEL, boom)
    agg = HookExecutor(reg).run_sync(HookContext(event=HookEvent.AFTER_MODEL, state={}))
    assert not agg.blocked  # not blocking by default
    assert agg.results and not agg.results[0].success


def test_hook_exception_blocks_when_marked():
    reg = HookRegistry()

    def boom(_c: HookContext) -> HookResult:
        raise RuntimeError("kaboom")

    reg.register(HookEvent.AFTER_MODEL, boom, block_on_failure=True)
    agg = HookExecutor(reg).run_sync(HookContext(event=HookEvent.AFTER_MODEL, state={}))
    assert agg.blocked


# --------------------- budget ---------------------


from langchain_core.messages import HumanMessage  # noqa: E402

from src.harness.budget import BudgetMiddleware  # noqa: E402
from src.harness.deep_agent import DeepAgentConfig, DeepAgentExecutor, StepStatus, TaskStep  # noqa: E402


def test_budget_max_turns_injects_advisory_without_terminating():
    mw = BudgetMiddleware(max_turns=3, max_wallclock_sec=10_000)
    state = {"messages": [HumanMessage(content="hello")]}
    # First 3 before_model calls increment turn_count; 4th is advisory only.
    for i in range(3):
        assert mw.before_model(state, runtime=None) is None
    out = mw.before_model(state, runtime=None)
    assert out is not None
    assert out.get("jump_to") is None
    assert out.get("runtime", {}).get("budget_advisory", {}).get("hard_stop") is False
    msgs = out.get("messages") or []
    assert msgs and "max_turns budget exhausted" in (msgs[0].content if hasattr(msgs[0], "content") else str(msgs[0]))


def test_budget_wallclock_zero_is_unlimited():
    mw = BudgetMiddleware(max_turns=10_000, max_wallclock_sec=0)
    state = {"messages": [HumanMessage(content="hello")]}
    # max_wallclock_sec=0 is the long-task mode: no artificial wall-clock cap.
    out = mw.before_model(state, runtime=None)
    assert out is None


def test_budget_resets_on_new_human_turn():
    mw = BudgetMiddleware(max_turns=2, max_wallclock_sec=10_000)
    state_a = {"messages": [HumanMessage(content="first")]}
    assert mw.before_model(state_a, runtime=None) is None
    assert mw.before_model(state_a, runtime=None) is None
    # Third should advise only
    assert mw.before_model(state_a, runtime=None) is not None
    # New human turn → counter resets
    state_b = {"messages": [HumanMessage(content="first"), HumanMessage(content="second")]}
    out = mw.before_model(state_b, runtime=None)
    assert out is None


def test_deep_agent_async_step_timeout_config_is_soft():
    async def slow_executor(_tool_name: str, _tool_args: dict):
        await asyncio.sleep(0.03)
        return "slow-ok"

    executor = DeepAgentExecutor(
        config=DeepAgentConfig(step_timeout_seconds=0.001),
        async_tool_executor=slow_executor,
    )
    step = TaskStep(tool_name="slow", max_retries=0)

    result = asyncio.run(executor.aexecute_step(step))

    assert result.status == StepStatus.COMPLETED
    assert result.result == "slow-ok"


# --------------------- run_journal ---------------------


def test_run_journal_disabled_is_noop(monkeypatch):
    monkeypatch.delenv("OCTO_HARNESS_RUN_JOURNAL", raising=False)
    from src.harness import run_journal as rj

    async def _t():
        assert await rj.init_run_journal() is False
        await rj.record_run_started("test-run-1", "test-thread-1")
        await rj.heartbeat("test-run-1")
        stale = await rj.find_stale_runs(stale_after_sec=0)
        assert stale == []
        assert await rj.mark_orphans_on_startup() == 0
        await rj.record_run_finished("test-run-1", status="cancelled_stale_heartbeat")
        await rj.shutdown_run_journal()

    asyncio.run(_t())
