"""Bridge ``AgentMiddleware`` lifecycle ↔ ``HookEvent`` taxonomy.

Two layers:

1. :class:`HookDispatchMiddleware` — a single thin ``AgentMiddleware`` that
   fires the declarative-hook surface on every model call. Drop it into the
   agent and any code that does
   ``get_hook_registry().register(HookEvent.AFTER_MODEL, my_fn)`` will run
   automatically without touching agent wiring.

2. Backward-compat shims: register the existing
   ``Critic`` / ``StepReflection`` / ``ProgressStall`` middleware *logic*
   as hook callables, so the legacy middlewares can be removed from the
   agent build list while preserving behaviour. The shims **reuse** the
   battle-tested heuristics inside those classes via composition (no
   re-implementation, no duplication, no behavioural drift).
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from src.harness.hooks import (
    AggregatedHookResult,
    HookContext,
    HookEvent,
    HookResult,
    get_hook_executor,
    get_hook_registry,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The dispatcher middleware
# ---------------------------------------------------------------------------


class HookDispatchMiddleware(AgentMiddleware[AgentState]):
    """Fires declarative hooks at AgentMiddleware lifecycle points."""

    def __init__(self) -> None:
        super().__init__()

    # ------- sync paths -------

    def _dispatch_sync(self, event: HookEvent, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        ctx = HookContext(event=event, state=state, runtime=runtime)
        agg = get_hook_executor().run_sync(ctx)
        return self._apply_aggregate(agg)

    def before_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._dispatch_sync(HookEvent.BEFORE_MODEL, state, runtime)

    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._dispatch_sync(HookEvent.AFTER_MODEL, state, runtime)

    # ------- async paths -------

    async def _adispatch(self, event: HookEvent, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        ctx = HookContext(event=event, state=state, runtime=runtime)
        agg = await get_hook_executor().run(ctx)
        return self._apply_aggregate(agg)

    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return await self._adispatch(HookEvent.BEFORE_MODEL, state, runtime)

    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return await self._adispatch(HookEvent.AFTER_MODEL, state, runtime)

    # ------- merging -------

    @staticmethod
    def _apply_aggregate(agg: AggregatedHookResult) -> dict[str, Any] | None:
        if not agg.results:
            return None
        merged = agg.merged_state_update()
        if agg.blocked:
            # Surface the block reason as a SystemMessage so the operator sees it.
            from langchain_core.messages import SystemMessage

            extra = {
                "messages": [SystemMessage(content=('<harness_hook_blocked event="{}" reason="{}">\n'.format(agg.event.value, agg.reason.replace('"', "'")) + "</harness_hook_blocked>"))],
                "jump_to": "END",
            }
            if merged is None:
                return extra
            merged.setdefault("messages", [])
            merged["messages"].extend(extra["messages"])
            merged["jump_to"] = "END"
            return merged
        return merged


# ---------------------------------------------------------------------------
# Default hook registration (migrate Critic / StepReflection / ProgressStall)
# ---------------------------------------------------------------------------


def _register_legacy_middleware_as_hooks() -> None:
    """Wrap the three legacy middlewares as ``AFTER_MODEL`` hooks.

    We **do not re-implement** the logic; we instantiate the existing
    middleware once and forward the ``after_model`` call through. This
    keeps behaviour identical while letting us drop them from the explicit
    middleware list and centralise observation via the hook surface.
    """
    registry = get_hook_registry()

    # ----- ProgressStall (highest priority: should run before reflection
    #       and critic so SystemMessage ordering remains sane) -----
    try:
        from src.agents.middlewares.progress_stall_middleware import ProgressStallMiddleware  # type: ignore

        _stall_mw = ProgressStallMiddleware()

        def _progress_stall_hook(ctx: HookContext) -> HookResult:
            # ProgressStallMiddleware acts in before_model — call the right hook.
            update = _stall_mw.before_model(ctx.state, ctx.runtime)
            block = False
            reason = ""
            # The middleware signals a hard circuit-breaker by including
            # ``jump_to: END`` in its state update. Translate that into the
            # sanctioned block=True path so ``_apply_aggregate`` performs the
            # actual graph termination (jump_to END). We strip jump_to from the
            # state_update itself because the aggregate re-adds it on block.
            if isinstance(update, dict) and str(update.get("jump_to", "")).upper() == "END":
                block = True
                reason = "progress_stall_hard_stop: repeated tool calls keep failing with no new progress; finalizing to break the loop"
                update = {k: v for k, v in update.items() if k != "jump_to"}
            return HookResult(
                hook_name="progress_stall",
                event=ctx.event,
                state_update=update if isinstance(update, dict) else None,
                block=block,
                reason=reason,
                metadata={"legacy_middleware": "ProgressStallMiddleware"},
            )

        registry.register(
            HookEvent.BEFORE_MODEL,
            _progress_stall_hook,
            name="progress_stall",
            priority=30,
        )
        # Also expose as the specialised ON_STALL event so external code can
        # extend / observe.
        registry.register(
            HookEvent.ON_STALL,
            _progress_stall_hook,
            name="progress_stall",
            priority=30,
        )
        logger.info("Harness hooks: registered ProgressStallMiddleware → BEFORE_MODEL + ON_STALL")
    except Exception:
        logger.exception("Harness hooks: failed to register ProgressStallMiddleware")

    # ----- StepReflection (medium priority) -----
    try:
        from src.agents.middlewares.step_reflection_middleware import StepReflectionMiddleware  # type: ignore

        _step_mw = StepReflectionMiddleware()

        def _step_reflection_hook(ctx: HookContext) -> HookResult:
            # StepReflectionMiddleware acts in before_model.
            update = _step_mw.before_model(ctx.state, ctx.runtime)
            return HookResult(
                hook_name="step_reflection",
                event=ctx.event,
                state_update=update if isinstance(update, dict) else None,
                metadata={"legacy_middleware": "StepReflectionMiddleware"},
            )

        registry.register(
            HookEvent.BEFORE_MODEL,
            _step_reflection_hook,
            name="step_reflection",
            priority=20,
        )
        registry.register(
            HookEvent.ON_REFLECTION_DUE,
            _step_reflection_hook,
            name="step_reflection",
            priority=20,
        )
        logger.info("Harness hooks: registered StepReflectionMiddleware → BEFORE_MODEL + ON_REFLECTION_DUE")
    except Exception:
        logger.exception("Harness hooks: failed to register StepReflectionMiddleware")

    # ----- Critic (lowest priority) -----
    try:
        from src.agents.middlewares.critic_middleware import CriticMiddleware  # type: ignore

        _critic_mw = CriticMiddleware()

        def _critic_hook(ctx: HookContext) -> HookResult:
            update = _critic_mw.after_model(ctx.state, ctx.runtime)
            return HookResult(
                hook_name="critic",
                event=ctx.event,
                state_update=update if isinstance(update, dict) else None,
                metadata={"legacy_middleware": "CriticMiddleware"},
            )

        registry.register(
            HookEvent.AFTER_MODEL,
            _critic_hook,
            name="critic",
            priority=10,
        )
        registry.register(
            HookEvent.ON_CRITIC_CHECK,
            _critic_hook,
            name="critic",
            priority=10,
        )
        logger.info("Harness hooks: registered CriticMiddleware → AFTER_MODEL + ON_CRITIC_CHECK")
    except Exception:
        logger.exception("Harness hooks: failed to register CriticMiddleware")


_DEFAULTS_INSTALLED = False


def install_default_hooks() -> None:
    """Idempotent — install the legacy-middleware → hook bridges once."""
    global _DEFAULTS_INSTALLED
    if _DEFAULTS_INSTALLED:
        return
    _register_legacy_middleware_as_hooks()
    _DEFAULTS_INSTALLED = True
    logger.info(
        "Harness hooks: defaults installed (registry_total=%d)",
        get_hook_registry().total_count(),
    )


__all__ = ["HookDispatchMiddleware", "install_default_hooks"]
