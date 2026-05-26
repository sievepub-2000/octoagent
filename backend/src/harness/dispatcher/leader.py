"""Leader election via ``pg_try_advisory_lock`` (Phase 6, stage 6.2).

Postgres advisory locks are **session-scoped**: when the leader's
connection drops (crash / network partition / clean shutdown), Postgres
auto-releases the lock and any other waiting worker can claim it. No
TTL renewal logic needed.

The leader role is identified by a magic ``(key1, key2)`` tuple. We use
``(0x6F63746F, 1)`` — 0x6F63746F == ASCII 'octo'.
"""

from __future__ import annotations

import asyncio
import logging

from src.harness.dispatcher.schema import (
    dispatcher_enabled,
    get_pool,
    leader_poll_interval_sec,
    worker_id,
)

logger = logging.getLogger(__name__)

_LEADER_KEY_1 = 0x6F63746F  # 'octo'
_LEADER_KEY_2 = 1

_state: dict[str, object] = {
    "is_leader": False,
    "leader_conn": None,  # psycopg AsyncConnection holding the advisory lock
    "since": None,
}


def is_leader() -> bool:
    """Synchronous, non-blocking check. Returns last known state."""
    return bool(_state.get("is_leader"))


def leader_status() -> dict:
    return {
        "worker_id": worker_id(),
        "is_leader": is_leader(),
        "since": _state.get("since"),
    }


async def _try_acquire_lock() -> bool:
    """Attempt to acquire the advisory lock. Returns True if acquired now.

    On success keeps the connection alive in ``_state["leader_conn"]`` so
    the session-scoped lock persists.
    """
    if _state.get("is_leader"):
        return True
    pool = await get_pool()
    if pool is None:
        return False
    try:
        conn = await pool.getconn()
    except Exception:
        logger.exception("Dispatcher.leader: failed to get conn")
        return False
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT pg_try_advisory_lock(%s, %s)",
                (_LEADER_KEY_1, _LEADER_KEY_2),
            )
            row = await cur.fetchone()
            acquired = bool(row and row[0])
        if not acquired:
            await pool.putconn(conn)
            return False
        # Promote this worker to leader role in registry.
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE octo_dispatch_workers SET role='leader' WHERE worker_id=%s",
                    (worker_id(),),
                )
        except Exception:
            logger.exception("Dispatcher.leader: failed to mark role=leader")
        _state["is_leader"] = True
        _state["leader_conn"] = conn  # KEEP — releasing returns lock
        from datetime import UTC, datetime

        _state["since"] = datetime.now(UTC).isoformat()
        logger.warning("Dispatcher.leader: ACQUIRED lock worker=%s", worker_id())
        return True
    except Exception:
        logger.exception("Dispatcher.leader: lock acquire failed")
        try:
            await pool.putconn(conn)
        except Exception:
            pass
        return False


async def _release_lock() -> None:
    if not _state.get("is_leader"):
        return
    conn = _state.get("leader_conn")
    pool = await get_pool()
    try:
        if conn is not None:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT pg_advisory_unlock(%s, %s)",
                        (_LEADER_KEY_1, _LEADER_KEY_2),
                    )
                    await cur.execute(
                        "UPDATE octo_dispatch_workers SET role='worker' WHERE worker_id=%s",
                        (worker_id(),),
                    )
            except Exception:
                logger.exception("Dispatcher.leader: unlock failed")
            if pool is not None:
                try:
                    await pool.putconn(conn)
                except Exception:
                    logger.exception("Dispatcher.leader: putconn failed")
    finally:
        _state["is_leader"] = False
        _state["leader_conn"] = None
        _state["since"] = None
        logger.warning("Dispatcher.leader: RELEASED lock worker=%s", worker_id())


class LeaderLoop:
    """Background loop that tries to acquire the leader lock periodically."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _run(self) -> None:
        interval = leader_poll_interval_sec()
        try:
            while not self._stop.is_set():
                if not _state.get("is_leader"):
                    await _try_acquire_lock()
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=interval)
                except TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Dispatcher.leader: loop crashed")
        finally:
            await _release_lock()

    def start(self) -> None:
        if not dispatcher_enabled():
            return
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="dispatcher-leader")

    async def stop(self) -> None:
        if self._task is None:
            await _release_lock()
            return
        self._stop.set()
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None
        await _release_lock()


__all__ = ["is_leader", "leader_status", "LeaderLoop"]
