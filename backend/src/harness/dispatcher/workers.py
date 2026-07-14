"""Worker registry + heartbeat (Phase 6, stage 6.1)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.harness.dispatcher.schema import (
    dispatcher_enabled,
    ensure_schema,
    get_pool,
    heartbeat_interval_sec,
    worker_host_pid,
    worker_id,
    worker_stale_after_sec,
)

logger = logging.getLogger(__name__)


async def register_worker(*, capabilities: dict[str, Any] | None = None) -> bool:
    """Insert/update this process's row in ``octo_dispatch_workers``."""
    if not dispatcher_enabled():
        return False
    if not await ensure_schema():
        return False
    pool = await get_pool()
    if pool is None:
        return False
    host, pid = worker_host_pid()
    caps = capabilities or {}
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                import json

                await cur.execute(
                    """
                    INSERT INTO octo_dispatch_workers
                        (worker_id, host, pid, capabilities)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (worker_id) DO UPDATE
                        SET host=EXCLUDED.host,
                            pid=EXCLUDED.pid,
                            heartbeat_at=now(),
                            capabilities=EXCLUDED.capabilities,
                            draining=false
                    """,
                    (worker_id(), host, pid, json.dumps(caps)),
                )
        logger.info("Dispatcher: worker registered worker_id=%s", worker_id())
        return True
    except Exception:
        logger.exception("Dispatcher: register_worker failed")
        return False


async def heartbeat_once() -> bool:
    """Bump ``heartbeat_at`` for this worker row."""
    if not dispatcher_enabled():
        return False
    pool = await get_pool()
    if pool is None:
        return False
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE octo_dispatch_workers SET heartbeat_at=now() WHERE worker_id=%s",
                    (worker_id(),),
                )
                return cur.rowcount > 0
    except Exception:
        logger.exception("Dispatcher: heartbeat failed")
        return False


async def deregister_worker() -> None:
    if not dispatcher_enabled():
        return
    pool = await get_pool()
    if pool is None:
        return
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM octo_dispatch_workers WHERE worker_id=%s",
                    (worker_id(),),
                )
    except Exception:
        logger.exception("Dispatcher: deregister_worker failed")


async def list_workers() -> list[dict[str, Any]]:
    """Return current registry contents (read-only observability)."""
    if not dispatcher_enabled():
        return []
    pool = await get_pool()
    if pool is None:
        return []
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT worker_id, host, pid, started_at, heartbeat_at,
                           role, draining, capabilities
                    FROM octo_dispatch_workers
                    ORDER BY started_at
                    """
                )
                rows = await cur.fetchall()
                cols = [d.name for d in cur.description]
        return [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in zip(cols, row)} for row in rows]
    except Exception:
        logger.exception("Dispatcher: list_workers failed")
        return []


async def reap_stale_workers() -> int:
    """Delete worker rows older than the heartbeat-stale threshold."""
    if not dispatcher_enabled():
        return 0
    pool = await get_pool()
    if pool is None:
        return 0
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    DELETE FROM octo_dispatch_workers
                    WHERE heartbeat_at < now() - (%s::int * interval '1 second')
                    RETURNING worker_id
                    """,
                    (worker_stale_after_sec(),),
                )
                rows = await cur.fetchall()
        if rows:
            logger.warning(
                "Dispatcher: reaped %d stale worker(s): %s",
                len(rows),
                [r[0] for r in rows],
            )
        return len(rows)
    except Exception:
        logger.exception("Dispatcher: reap_stale_workers failed")
        return 0


async def mark_draining(target_worker_id: str | None = None) -> bool:
    """Set ``draining=true``; coordinator stops sending new work to it."""
    wid = target_worker_id or worker_id()
    if not dispatcher_enabled():
        return False
    pool = await get_pool()
    if pool is None:
        return False
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE octo_dispatch_workers SET draining=true WHERE worker_id=%s",
                    (wid,),
                )
                return cur.rowcount > 0
    except Exception:
        logger.exception("Dispatcher: mark_draining failed worker=%s", wid)
        return False


# ---------------------------------------------------------------------------
# Heartbeat loop
# ---------------------------------------------------------------------------


class HeartbeatLoop:
    """Periodic ``heartbeat_at`` updater. One per process."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _run(self) -> None:
        interval = heartbeat_interval_sec()
        try:
            while not self._stop.is_set():
                await heartbeat_once()
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=interval)
                except TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Dispatcher: heartbeat loop crashed")

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="dispatcher-heartbeat")

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
    "register_worker",
    "heartbeat_once",
    "deregister_worker",
    "list_workers",
    "reap_stale_workers",
    "mark_draining",
    "HeartbeatLoop",
]
