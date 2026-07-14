"""Budget middleware: wall-clock + max-turns soft review points.

A LangGraph ``AgentMiddleware`` that bounds an agent run:

* ``OCTO_HARNESS_MAX_TURNS`` (default 0 = unlimited) — total number of model
  calls permitted per agent run. **0 means unlimited**: the system relies on
  resource-pressure guards (``should_abort()``) instead of a fixed turn cap.
  This is enforced per ``before_model`` call.
* ``OCTO_HARNESS_MAX_WALLCLOCK_SEC`` (default 0 = unlimited) — total wallclock
  seconds permitted between PRE_RUN and now. **0 means unlimited**.

When either soft budget is exceeded (and non-zero), the middleware:

1. Fires the ``ON_BUDGET_EXCEEDED`` hook so observers can record the event.
2. Injects a hidden ``SystemMessage`` asking the agent to summarise lessons,
    write useful experience into memory when available, and continue.

Design rationale (2026-05-16): the previous default of max_turns=60 caused
tasks to stop unexpectedly after ~30-33 tool calls because each tool call
consumes approximately 2 model turns (model->tool->model). The new default
is unlimited (0) so the system can execute long-running tasks without
artificial interruption. The OOM guard is the only hard safety net: cleanup at
85% memory and task stop at 90% memory.

Env knobs:
* ``OCTO_HARNESS_MAX_TURNS`` (int, default 0 = unlimited)
* ``OCTO_HARNESS_MAX_WALLCLOCK_SEC`` (int, default 0 = unlimited)
* ``OCTO_HARNESS_BUDGET_ENABLED`` (``0`` to disable, default ``1``)
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from src.harness.hooks import HookContext, HookEvent, get_hook_executor
from src.utils.messages import latest_human_index as _latest_human_index

logger = logging.getLogger(__name__)


_ADVISORY_MARKER = '<harness_budget_advisory origin="budget_middleware"'

_HOOK_THREAD_POOL = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="budget-hook-executor",
)


def _run_budget_hook(ctx: HookContext) -> None:
    get_hook_executor().run_sync(ctx)


def _dispatch_budget_hook(ctx: HookContext) -> None:
    """Dispatch the sync observability hook off the model hot path."""

    future = _HOOK_THREAD_POOL.submit(_run_budget_hook, ctx)

    def _log_failure(done) -> None:  # type: ignore[no-untyped-def]
        try:
            done.result()
        except Exception:
            logger.exception("BudgetMiddleware: ON_BUDGET_EXCEEDED hook dispatch failed")

    future.add_done_callback(_log_failure)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        # Allow 0 (unlimited) as a valid value
        return v if v >= 0 else default
    except ValueError:
        return default


def _env_flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() not in ("0", "false", "no", "off", "")


def _already_advised(messages: list[Any]) -> bool:
    for msg in reversed(messages):
        content = getattr(msg, "content", "")
        if isinstance(content, str) and _ADVISORY_MARKER in content:
            return True
    return False


class BudgetMiddleware(AgentMiddleware[AgentState]):
    """Adds soft review guidance for total turns and wall-clock seconds.

    When max_turns or max_wallclock_sec is 0 (the default), that dimension
    is treated as unlimited — the system relies on resource-pressure guards
    (``should_abort()``) instead of artificial turn/time caps.
    """

    def __init__(
        self,
        *,
        max_turns: int | None = None,
        max_wallclock_sec: int | None = None,
    ) -> None:
        super().__init__()
        self.max_turns = max_turns if max_turns is not None else _env_int("OCTO_HARNESS_MAX_TURNS", 0)
        self.max_wallclock_sec = max_wallclock_sec if max_wallclock_sec is not None else _env_int("OCTO_HARNESS_MAX_WALLCLOCK_SEC", 0)
        # Per-instance turn counter; reset when a new HumanMessage appears.
        self._turn_anchor: int = -1
        self._turn_count: int = 0
        self._wallclock_start: float | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_reset(self, messages: list[Any]) -> None:
        anchor = _latest_human_index(messages)
        if anchor != self._turn_anchor:
            self._turn_anchor = anchor
            self._turn_count = 0
            self._wallclock_start = time.monotonic()

    def _budget_breach_reason(self) -> str | None:
        # 0 means unlimited — skip the check entirely
        if self.max_turns > 0 and self._turn_count >= self.max_turns:
            return f"max_turns budget exhausted (turns={self._turn_count}, ceiling={self.max_turns})"
        if self.max_wallclock_sec > 0 and self._wallclock_start is not None:
            elapsed = time.monotonic() - self._wallclock_start
            if elapsed >= self.max_wallclock_sec:
                return f"max_wallclock budget exhausted (elapsed={elapsed:.1f}s, ceiling={self.max_wallclock_sec}s)"
        return None

    def _build_advisory_update(self, reason: str) -> dict[str, Any]:
        msg = SystemMessage(
            content=(
                f"{_ADVISORY_MARKER}>\n"
                f"  reason: {reason}\n"
                "  policy: this is soft guidance only; do not stop because of this budget.\n"
                "  next: summarise what has worked, avoid repeating dead ends, and write reusable lessons to the memory system when memory tools are available.\n"
                "</harness_budget_advisory>"
            )
        )
        return {"messages": [msg], "runtime": {"budget_advisory": {"reason": reason, "hard_stop": False}}}

    def _check_budget(self, state: AgentState) -> dict[str, Any] | None:
        messages = list(state.get("messages", []) or [])
        if _already_advised(messages):
            return None
        self._maybe_reset(messages)
        reason = self._budget_breach_reason()
        if reason is None:
            return None
        logger.warning("BudgetMiddleware: %s — injecting advisory only", reason)
        # Fire observability hook (best-effort) outside the model hot path.
        ctx = HookContext(
            event=HookEvent.ON_BUDGET_EXCEEDED,
            state=state,
            annotations={
                "reason": reason,
                "turn_count": self._turn_count,
                "max_turns": self.max_turns,
                "max_wallclock_sec": self.max_wallclock_sec,
            },
        )
        _dispatch_budget_hook(ctx)
        return self._build_advisory_update(reason)

    async def _acheck_budget(self, state: AgentState) -> dict[str, Any] | None:
        messages = list(state.get("messages", []) or [])
        if _already_advised(messages):
            return None
        self._maybe_reset(messages)
        reason = self._budget_breach_reason()
        if reason is None:
            return None
        logger.warning("BudgetMiddleware: %s — injecting advisory only", reason)
        try:
            executor = get_hook_executor()
            ctx = HookContext(
                event=HookEvent.ON_BUDGET_EXCEEDED,
                state=state,
                annotations={
                    "reason": reason,
                    "turn_count": self._turn_count,
                    "max_turns": self.max_turns,
                    "max_wallclock_sec": self.max_wallclock_sec,
                },
            )
            await executor.run(ctx)
        except Exception:
            logger.exception("BudgetMiddleware: ON_BUDGET_EXCEEDED hook dispatch failed")
        return self._build_advisory_update(reason)

    # ------------------------------------------------------------------
    # AgentMiddleware lifecycle
    # ------------------------------------------------------------------

    def before_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        out = self._check_budget(state)
        # Count every before_model call as one turn (only when we did not
        # short-circuit) so the next before_model can detect the breach.
        if out is None:
            self._turn_count += 1
        return out

    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        out = await self._acheck_budget(state)
        if out is None:
            self._turn_count += 1
        return out


def maybe_build_budget_middleware() -> BudgetMiddleware | None:
    """Return a configured ``BudgetMiddleware`` unless disabled via env."""
    if not _env_flag("OCTO_HARNESS_BUDGET_ENABLED", "1"):
        logger.info("BudgetMiddleware: disabled via OCTO_HARNESS_BUDGET_ENABLED=0")
        return None
    return BudgetMiddleware()


__all__ = ["BudgetMiddleware", "maybe_build_budget_middleware"]
