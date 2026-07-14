"""Coordinator dispatch loop (Phase 6, stage 6.4).

A single elected leader polls ``octo_dispatch_queue`` and routes ready
jobs to in-process handlers. Default handler set is empty; consumers
register via :func:`register_handler`.

When the dispatcher is disabled or no DSN is configured, the loop
silently no-ops.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.harness.dispatcher.leader import is_leader
from src.harness.dispatcher.queue import (
    ack_dispatch,
    claim_dispatch,
    nack_dispatch,
)
from src.harness.dispatcher.schema import (
    dispatch_poll_interval_sec,
    dispatcher_enabled,
)
from src.harness.dispatcher.workers import reap_stale_workers

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]

_handlers: dict[str, Handler] = {}


def register_handler(kind: str, handler: Handler) -> None:
    """Register an async handler for one queue ``kind``."""
    _handlers[kind] = handler
    logger.info("Dispatcher.dispatch: handler registered kind=%s", kind)


def registered_kinds() -> list[str]:
    return list(_handlers.keys())


class DispatchLoop:
    """Polls the queue while this worker is leader; routes due jobs.

    Only the leader sweeps and dispatches; followers idle. This sidesteps
    the need for partitioned queues or per-worker assignment in this
    phase. Throughput scales by N_JOBS_PER_WORKER-equivalents *behind*
    each registered handler, not by multiple leaders racing the same
    table.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _process_one(self) -> bool:
        kinds = list(_handlers.keys())
        if not kinds:
            return False
        row = await claim_dispatch(kinds=kinds)
        if row is None:
            return False
        kind = row.get("kind", "")
        handler = _handlers.get(kind)
        if handler is None:
            await nack_dispatch(row["dispatch_id"], error=f"no handler for kind={kind}")
            return True
        try:
            await handler(row)
            await ack_dispatch(row["dispatch_id"], state="ok")
            return True
        except Exception as exc:
            logger.exception(
                "Dispatcher.dispatch: handler kind=%s id=%s raised",
                kind,
                row.get("dispatch_id"),
            )
            await nack_dispatch(row["dispatch_id"], error=str(exc)[:500])
            return True

    async def _run(self) -> None:
        interval = dispatch_poll_interval_sec()
        reap_every = max(60 // max(interval, 1), 1)  # ~once per 60 s
        tick = 0
        try:
            while not self._stop.is_set():
                if dispatcher_enabled() and is_leader():
                    # Drain whatever's due in a tight inner loop; back off
                    # when nothing claims successfully.
                    for _ in range(50):
                        worked = await self._process_one()
                        if not worked:
                            break
                    tick += 1
                    if tick % reap_every == 0:
                        try:
                            await reap_stale_workers()
                        except Exception:
                            logger.exception("Dispatcher.dispatch: reap_stale_workers failed")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=interval)
                except TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Dispatcher.dispatch: loop crashed")

    def start(self) -> None:
        if not dispatcher_enabled():
            return
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="dispatcher-dispatch")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None


__all__ = [
    "register_handler",
    "registered_kinds",
    "DispatchLoop",
    "Handler",
]
