"""Drain helpers (Phase 6, stage 6.5).

``drain_self()`` marks this worker as draining and waits up to
``OCTO_GRACEFUL_DRAIN_TIMEOUT`` seconds for in-flight rows owned by
this worker to finish (``finished_at IS NOT NULL``). After the timeout
or once the count reaches zero, the function returns a summary dict.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from src.harness.dispatcher.schema import (
    dispatcher_enabled,
    drain_timeout_sec,
    get_pool,
    worker_id,
)
from src.harness.dispatcher.workers import mark_draining

logger = logging.getLogger(__name__)


async def _inflight_count_for_self() -> int:
    pool = await get_pool()
    if pool is None:
        return 0
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT count(*)
                    FROM octo_dispatch_queue
                    WHERE claimed_by=%s AND finished_at IS NULL
                    """,
                    (worker_id(),),
                )
                row = await cur.fetchone()
                return int(row[0]) if row else 0
    except Exception:
        logger.exception("Dispatcher.drain: inflight count failed")
        return 0


async def drain_self(timeout_sec: int | None = None) -> dict[str, Any]:
    """Mark this worker draining; wait for in-flight rows to finish.

    Returns ``{"drained": bool, "remaining": int, "elapsed_sec": float}``.
    Safe to call when the dispatcher is disabled — returns an immediate
    ``drained=True, remaining=0`` so callers can wire it unconditionally
    into shutdown paths.
    """
    if not dispatcher_enabled():
        return {"drained": True, "remaining": 0, "elapsed_sec": 0.0, "enabled": False}
    await mark_draining()
    deadline = (timeout_sec if timeout_sec is not None else drain_timeout_sec())
    started = time.monotonic()
    poll = 1.0
    while True:
        remaining = await _inflight_count_for_self()
        if remaining == 0:
            return {
                "drained": True,
                "remaining": 0,
                "elapsed_sec": round(time.monotonic() - started, 2),
                "enabled": True,
            }
        if time.monotonic() - started >= deadline:
            logger.warning(
                "Dispatcher.drain: timeout reached worker=%s remaining=%d",
                worker_id(),
                remaining,
            )
            return {
                "drained": False,
                "remaining": remaining,
                "elapsed_sec": round(time.monotonic() - started, 2),
                "enabled": True,
            }
        await asyncio.sleep(poll)


__all__ = ["drain_self"]
