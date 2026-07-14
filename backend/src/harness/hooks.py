"""Declarative hooks for the agent harness.

Ported from the conceptual model of ``openharness.hooks`` but adapted to the
LangGraph + ``langchain.agents.AgentMiddleware`` world:

* No shell / HTTP / sandboxed sub-process hooks (octoagent doesn't need that
  attack surface). Hooks here are plain async / sync Python callables.
* The hook lifecycle is anchored to ``AgentMiddleware`` lifecycle points
  (``before_model`` / ``after_model`` / ``before_tool`` / ``after_tool``)
  rather than OpenHarness's bespoke `query` engine events.
* Results carry a ``block`` flag: a single blocking hook short-circuits the
  current step and surfaces the reason to the operator (via a SystemMessage
  written by :mod:`src.harness.hook_middleware`).

This module contains **only data types + registry + executor**. Wiring lives
in :mod:`src.harness.hook_middleware`. Default hook implementations live in
:mod:`src.harness.hook_adapters`.
"""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event taxonomy
# ---------------------------------------------------------------------------


class HookEvent(str, Enum):
    """Lifecycle events at which hooks may run.

    The four user-asked events are PRE_RUN / POST_RUN / ON_TOOL / ON_ERROR.
    We expand ON_TOOL into START + END for clarity, and add the migration
    targets ON_STALL / ON_REFLECTION_DUE / ON_CRITIC_CHECK.
    """

    PRE_RUN = "pre_run"  # before the very first model call of a user turn
    POST_RUN = "post_run"  # after the last model call of a user turn
    BEFORE_MODEL = "before_model"  # every model call
    AFTER_MODEL = "after_model"  # every model call (post-stream)
    ON_TOOL_START = "on_tool_start"  # before a tool batch
    ON_TOOL_END = "on_tool_end"  # after a tool batch
    ON_ERROR = "on_error"  # any uncaught exception in the harness path
    ON_STALL = "on_stall"  # progress-stall detector trigger
    ON_REFLECTION_DUE = "on_reflection_due"  # cadence-based step review
    ON_CRITIC_CHECK = "on_critic_check"  # goal-contract critic trigger
    ON_BUDGET_EXCEEDED = "on_budget_exceeded"  # wall-clock or max-turns


# ---------------------------------------------------------------------------
# Result + context types
# ---------------------------------------------------------------------------


@dataclass
class HookResult:
    """Result from a single hook invocation."""

    hook_name: str
    event: HookEvent
    success: bool = True
    block: bool = False
    reason: str = ""
    # State-mutation payload returned to the caller (e.g. messages to inject).
    # Shape matches what an AgentMiddleware's before/after_model returns:
    #   None | {"messages": [...]} | {"jump_to": "..."} | etc.
    state_update: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


@dataclass
class AggregatedHookResult:
    """Aggregated result for a single ``run(event, ...)`` invocation."""

    event: HookEvent
    results: list[HookResult] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(r.block for r in self.results)

    @property
    def reason(self) -> str:
        for r in self.results:
            if r.block:
                return r.reason or r.hook_name
        return ""

    def merged_state_update(self) -> dict[str, Any] | None:
        """Merge state updates from every hook in registration order.

        Same shape as a single middleware return value. Hooks producing a
        ``messages`` list have their messages concatenated; other keys take
        the last-writer-wins value.
        """
        out: dict[str, Any] | None = None
        for r in self.results:
            update = r.state_update
            if not update:
                continue
            if out is None:
                out = {}
            for key, value in update.items():
                if key == "messages":
                    out.setdefault("messages", [])
                    if isinstance(value, list):
                        out["messages"].extend(value)
                    else:
                        out["messages"].append(value)
                else:
                    out[key] = value
        return out


@dataclass
class HookContext:
    """Per-invocation context passed to every hook callable.

    Hooks should treat ``state`` and ``runtime`` as **read-only**; mutations
    must be returned via ``HookResult.state_update`` so the harness can
    aggregate cleanly.
    """

    event: HookEvent
    state: Mapping[str, Any]
    runtime: Any = None
    # Optional, set by ON_TOOL_* / ON_ERROR hooks
    tool_name: str | None = None
    tool_args: Mapping[str, Any] | None = None
    tool_result: Any = None
    error: BaseException | None = None
    # Free-form annotations from earlier hooks in the same event run
    annotations: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Registry + executor
# ---------------------------------------------------------------------------


HookCallable = Callable[[HookContext], "HookResult | Awaitable[HookResult] | dict[str, Any] | None"]


@dataclass
class _RegisteredHook:
    name: str
    event: HookEvent
    fn: HookCallable
    block_on_failure: bool = False
    priority: int = 0  # higher runs first


class HookRegistry:
    """Process-wide registry mapping event → ordered list of hooks."""

    def __init__(self) -> None:
        self._hooks: dict[HookEvent, list[_RegisteredHook]] = {ev: [] for ev in HookEvent}

    def register(
        self,
        event: HookEvent,
        fn: HookCallable,
        *,
        name: str | None = None,
        block_on_failure: bool = False,
        priority: int = 0,
    ) -> None:
        hook = _RegisteredHook(
            name=name or getattr(fn, "__name__", "<hook>"),
            event=event,
            fn=fn,
            block_on_failure=block_on_failure,
            priority=priority,
        )
        bucket = self._hooks.setdefault(event, [])
        bucket.append(hook)
        bucket.sort(key=lambda h: -h.priority)
        logger.debug("HookRegistry: registered %s for %s (priority=%d)", hook.name, event.value, priority)

    def unregister_all(self, event: HookEvent | None = None) -> None:
        if event is None:
            for ev in self._hooks:
                self._hooks[ev] = []
        else:
            self._hooks[event] = []

    def get(self, event: HookEvent) -> Iterable[_RegisteredHook]:
        return tuple(self._hooks.get(event, ()))

    def event_count(self, event: HookEvent) -> int:
        return len(self._hooks.get(event, ()))

    def total_count(self) -> int:
        return sum(len(b) for b in self._hooks.values())

    def list_registered(self) -> list[tuple[str, str]]:
        """Return stable hook-name/event pairs for health and UI inspection."""
        return sorted((hook.name, event.value) for event, hooks in self._hooks.items() for hook in hooks)


class HookExecutor:
    """Run hooks for a given event with safe error isolation."""

    def __init__(self, registry: HookRegistry) -> None:
        self._registry = registry

    def replace_registry(self, registry: HookRegistry) -> None:
        self._registry = registry

    async def run(self, ctx: HookContext) -> AggregatedHookResult:
        results: list[HookResult] = []
        for hook in self._registry.get(ctx.event):
            t0 = time.perf_counter()
            try:
                raw = hook.fn(ctx)
                if inspect.isawaitable(raw):
                    raw = await raw
            except Exception as exc:
                logger.exception("HookExecutor: hook=%s event=%s raised", hook.name, ctx.event.value)
                results.append(
                    HookResult(
                        hook_name=hook.name,
                        event=ctx.event,
                        success=False,
                        block=hook.block_on_failure,
                        reason=f"{type(exc).__name__}: {exc}",
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                    )
                )
                if hook.block_on_failure:
                    break
                continue

            result = _coerce_result(raw, hook.name, ctx.event)
            result.duration_ms = (time.perf_counter() - t0) * 1000.0
            results.append(result)
            if result.block:
                break
        return AggregatedHookResult(event=ctx.event, results=results)

    def run_sync(self, ctx: HookContext) -> AggregatedHookResult:
        """Synchronous-only execution: skips awaitable hooks with a warning."""
        results: list[HookResult] = []
        for hook in self._registry.get(ctx.event):
            t0 = time.perf_counter()
            try:
                raw = hook.fn(ctx)
                if inspect.isawaitable(raw):
                    # Drop the coroutine to avoid resource warning, then skip
                    try:
                        raw.close()  # type: ignore[union-attr]
                    except Exception:
                        pass
                    logger.warning(
                        "HookExecutor.run_sync: skipping async hook %s on %s",
                        hook.name,
                        ctx.event.value,
                    )
                    continue
            except Exception as exc:
                logger.exception("HookExecutor.run_sync: hook=%s event=%s raised", hook.name, ctx.event.value)
                results.append(
                    HookResult(
                        hook_name=hook.name,
                        event=ctx.event,
                        success=False,
                        block=hook.block_on_failure,
                        reason=f"{type(exc).__name__}: {exc}",
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                    )
                )
                if hook.block_on_failure:
                    break
                continue

            result = _coerce_result(raw, hook.name, ctx.event)
            result.duration_ms = (time.perf_counter() - t0) * 1000.0
            results.append(result)
            if result.block:
                break
        return AggregatedHookResult(event=ctx.event, results=results)


def _coerce_result(raw: Any, hook_name: str, event: HookEvent) -> HookResult:
    if isinstance(raw, HookResult):
        return raw
    if raw is None:
        return HookResult(hook_name=hook_name, event=event)
    if isinstance(raw, dict):
        # Treat as state_update
        return HookResult(hook_name=hook_name, event=event, state_update=raw)
    # Anything else: log and accept as success without payload
    logger.debug("HookExecutor: hook %s returned unexpected type %s", hook_name, type(raw).__name__)
    return HookResult(hook_name=hook_name, event=event)


# ---------------------------------------------------------------------------
# Process-global registry singleton (lazy)
# ---------------------------------------------------------------------------


_registry_singleton: HookRegistry | None = None


def get_hook_registry() -> HookRegistry:
    global _registry_singleton
    if _registry_singleton is None:
        _registry_singleton = HookRegistry()
    return _registry_singleton


def get_hook_executor() -> HookExecutor:
    return HookExecutor(get_hook_registry())


def hook(event: HookEvent, *, name: str | None = None, priority: int = 0, block_on_failure: bool = False):
    """Decorator: register a function as a hook for ``event`` on import."""

    def deco(fn: HookCallable) -> HookCallable:
        get_hook_registry().register(
            event,
            fn,
            name=name or fn.__name__,
            block_on_failure=block_on_failure,
            priority=priority,
        )
        return fn

    return deco


__all__ = [
    "HookEvent",
    "HookResult",
    "AggregatedHookResult",
    "HookContext",
    "HookRegistry",
    "HookExecutor",
    "get_hook_registry",
    "get_hook_executor",
    "hook",
]
