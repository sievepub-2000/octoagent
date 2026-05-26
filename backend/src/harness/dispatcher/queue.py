"""Durable job queue (Phase 6, stage 6.3 + 6.4).

Single-row claim uses ``SELECT ... FOR UPDATE SKIP LOCKED`` so multiple
workers can poll the same table without serialising. Each row carries a
stable ``dispatch_id`` (caller-supplied or auto-generated); re-inserting
the same id is idempotent.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from src.harness.dispatcher.schema import (
    dispatcher_enabled,
    ensure_schema,
    get_pool,
    worker_id,
)

logger = logging.getLogger(__name__)


def _backoff_seconds(attempts: int) -> int:
    """Exponential backoff capped at 5 minutes. ``attempts`` is the count
    BEFORE this failure (i.e. starts at 0 for first try)."""
    if attempts <= 0:
        return 1
    seconds = 2 ** min(attempts, 16)
    return min(seconds, 300)


async def enqueue_dispatch(
    kind: str,
    payload: dict[str, Any],
    *,
    dispatch_id: str | None = None,
    priority: int = 0,
    available_in_sec: int = 0,
    max_attempts: int = 5,
) -> str | None:
    """Insert a job. Returns the ``dispatch_id`` on success, else ``None``.

    If ``dispatch_id`` already exists, the call is a no-op and returns
    the existing id (idempotent re-enqueue).
    """
    if not dispatcher_enabled():
        return None
    if not await ensure_schema():
        return None
    pool = await get_pool()
    if pool is None:
        return None
    did = dispatch_id or uuid.uuid4().hex
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO octo_dispatch_queue
                        (dispatch_id, kind, payload, priority,
                         available_at, max_attempts)
                    VALUES (%s, %s, %s::jsonb, %s,
                            now() + (%s::int * interval '1 second'), %s)
                    ON CONFLICT (dispatch_id) DO NOTHING
                    """,
                    (
                        did,
                        kind,
                        json.dumps(payload),
                        int(priority),
                        int(available_in_sec),
                        int(max_attempts),
                    ),
                )
        # Best-effort wake-up notify; channel-name = 'octo_dispatch_<kind>'.
        try:
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"NOTIFY octo_dispatch_{_safe_channel(kind)}, %s",
                        (did,),
                    )
        except Exception:
            logger.debug("Dispatcher.queue: NOTIFY skipped", exc_info=True)
        return did
    except Exception:
        logger.exception("Dispatcher.queue: enqueue_dispatch failed kind=%s", kind)
        return None


def _safe_channel(kind: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in kind)[:32] or "generic"


async def claim_dispatch(*, kinds: list[str] | None = None) -> dict[str, Any] | None:
    """Atomically claim ONE due job using ``FOR UPDATE SKIP LOCKED``.

    Returns the claimed row (with ``payload`` parsed to dict) or ``None``.
    The caller is responsible for invoking :func:`ack_dispatch` or
    :func:`nack_dispatch` after processing.
    """
    if not dispatcher_enabled():
        return None
    pool = await get_pool()
    if pool is None:
        return None
    where = "finished_at IS NULL AND available_at <= now()"
    params: list[Any] = []
    if kinds:
        where += " AND kind = ANY(%s)"
        params.append(list(kinds))
    sql = f"""
        WITH claimed AS (
            SELECT dispatch_id
            FROM octo_dispatch_queue
            WHERE {where}
            ORDER BY priority DESC, available_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE octo_dispatch_queue q
        SET claimed_by=%s, claimed_at=now(), attempts=q.attempts+1
        FROM claimed
        WHERE q.dispatch_id = claimed.dispatch_id
        RETURNING q.dispatch_id, q.kind, q.payload, q.priority,
                  q.attempts, q.max_attempts, q.enqueued_at
    """
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, [*params, worker_id()])
                row = await cur.fetchone()
                if not row:
                    return None
                cols = [d.name for d in cur.description]
        out = dict(zip(cols, row))
        # Payload comes back as parsed dict (psycopg jsonb adapter), but
        # if it came back as a str, parse defensively.
        if isinstance(out.get("payload"), str):
            try:
                out["payload"] = json.loads(out["payload"])
            except Exception:
                pass
        for k, v in list(out.items()):
            if hasattr(v, "isoformat"):
                out[k] = v.isoformat()
        return out
    except Exception:
        logger.exception("Dispatcher.queue: claim_dispatch failed")
        return None


async def ack_dispatch(dispatch_id: str, *, state: str = "ok") -> bool:
    """Mark a claimed job finished. Idempotent."""
    if not dispatcher_enabled() or not dispatch_id:
        return False
    pool = await get_pool()
    if pool is None:
        return False
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE octo_dispatch_queue
                    SET finished_at=now(), finished_state=%s
                    WHERE dispatch_id=%s AND finished_at IS NULL
                    """,
                    (state, dispatch_id),
                )
                return cur.rowcount > 0
    except Exception:
        logger.exception("Dispatcher.queue: ack_dispatch failed id=%s", dispatch_id)
        return False


async def nack_dispatch(
    dispatch_id: str, *, error: str | None = None
) -> dict[str, Any] | None:
    """Re-queue a failed job with exponential backoff, or mark failed
    if ``attempts >= max_attempts``.

    Returns a small status dict ``{retry: bool, attempts: int, ...}``.
    """
    if not dispatcher_enabled() or not dispatch_id:
        return None
    pool = await get_pool()
    if pool is None:
        return None
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT attempts, max_attempts FROM octo_dispatch_queue WHERE dispatch_id=%s",
                    (dispatch_id,),
                )
                row = await cur.fetchone()
                if not row:
                    return None
                attempts, max_attempts = int(row[0]), int(row[1])
                if attempts >= max_attempts:
                    await cur.execute(
                        """
                        UPDATE octo_dispatch_queue
                        SET finished_at=now(), finished_state='failed',
                            last_error=%s
                        WHERE dispatch_id=%s
                        """,
                        (error, dispatch_id),
                    )
                    return {
                        "retry": False,
                        "attempts": attempts,
                        "max_attempts": max_attempts,
                    }
                backoff = _backoff_seconds(attempts)
                await cur.execute(
                    """
                    UPDATE octo_dispatch_queue
                    SET claimed_by=NULL, claimed_at=NULL,
                        available_at=now() + (%s::int * interval '1 second'),
                        last_error=%s
                    WHERE dispatch_id=%s
                    """,
                    (backoff, error, dispatch_id),
                )
                return {
                    "retry": True,
                    "attempts": attempts,
                    "max_attempts": max_attempts,
                    "next_available_in_sec": backoff,
                }
    except Exception:
        logger.exception("Dispatcher.queue: nack_dispatch failed id=%s", dispatch_id)
        return None


async def dispatch_queue_stats() -> dict[str, Any]:
    """Aggregate counts for observability endpoints."""
    if not dispatcher_enabled():
        return {"enabled": False, "by_state": {}, "by_kind": {}, "in_flight": 0}
    pool = await get_pool()
    if pool is None:
        return {"enabled": True, "available": False, "by_state": {}, "by_kind": {}, "in_flight": 0}
    out: dict[str, Any] = {"enabled": True, "available": True, "by_state": {}, "by_kind": {}}
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT COALESCE(finished_state, 'pending'), count(*)
                    FROM octo_dispatch_queue
                    GROUP BY 1
                    """
                )
                out["by_state"] = {row[0]: int(row[1]) for row in await cur.fetchall()}
                await cur.execute(
                    """
                    SELECT kind, count(*)
                    FROM octo_dispatch_queue
                    WHERE finished_at IS NULL
                    GROUP BY 1
                    """
                )
                out["by_kind"] = {row[0]: int(row[1]) for row in await cur.fetchall()}
                await cur.execute(
                    "SELECT count(*) FROM octo_dispatch_queue WHERE claimed_by IS NOT NULL AND finished_at IS NULL"
                )
                row = await cur.fetchone()
                out["in_flight"] = int(row[0]) if row else 0
        return out
    except Exception:
        logger.exception("Dispatcher.queue: dispatch_queue_stats failed")
        return out


__all__ = [
    "enqueue_dispatch",
    "claim_dispatch",
    "ack_dispatch",
    "nack_dispatch",
    "dispatch_queue_stats",
]
