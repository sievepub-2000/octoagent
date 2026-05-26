"""Persistent run journal — root-cause cure for ghost-runs.

``langgraph-runtime-postgres`` (the official Postgres-backed queue) is a
**commercial Elastic-2.0 module** and isn't on PyPI as OSS. We achieve the
same *outcome* (no ghost runs surviving a process restart) by keeping our
own journal in the Postgres database we already use for the
``langgraph-checkpoint-postgres`` checkpointer.

The journal is **observability + recovery**, not a replacement scheduler.
Concretely:

* Every started/finished run is recorded with ``thread_id``, ``run_id``,
  ``status``, ``created_at``, ``updated_at``, ``heartbeat_at``.
* Heartbeat is bumped from the hook executor on every AFTER_MODEL call,
  giving us "the worker is alive" liveness regardless of run age.
* The :class:`OrphanRunSweeper` (in :mod:`src.harness.lifecycle`) can
    consult the journal to find runs whose ``heartbeat_at`` is stale (> N
    seconds) — that's the *true* ghost signature — and observe them.
* On gateway startup we leave still-``running`` rows intact by default.
    The OOM guard is the only automatic hard stop.

Opt-in via env ``OCTO_HARNESS_RUN_JOURNAL=1``. When disabled, all functions
become no-ops returning empty results.

Schema is auto-applied on first connection; ``CREATE TABLE IF NOT EXISTS``
is idempotent and cheap.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS octo_harness_run_journal (
    run_id           TEXT PRIMARY KEY,
    thread_id        TEXT NOT NULL,
    status           TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ,
    cancelled_reason TEXT
);
CREATE INDEX IF NOT EXISTS octo_harness_run_journal_thread_idx
    ON octo_harness_run_journal (thread_id, status);
CREATE INDEX IF NOT EXISTS octo_harness_run_journal_status_idx
    ON octo_harness_run_journal (status, heartbeat_at);
"""


def _journal_enabled() -> bool:
    return os.getenv("OCTO_HARNESS_RUN_JOURNAL", "0").strip().lower() in ("1", "true", "yes", "on")


def _stale_after_seconds() -> int:
    raw = os.getenv("OCTO_HARNESS_RUN_HEARTBEAT_STALE_SEC", "120").strip()
    try:
        v = int(raw)
        return v if v >= 10 else 120
    except ValueError:
        return 120


def _resolve_dsn() -> str | None:
    """Resolve the Postgres DSN.

    Priority: ``OCTO_HARNESS_RUN_JOURNAL_DSN`` → checkpointer DSN from
    ``config.yaml`` → ``DATABASE_URL`` env. Returns ``None`` if nothing is set.
    """
    override = os.getenv("OCTO_HARNESS_RUN_JOURNAL_DSN")
    if override:
        return override
    try:
        from src.runtime.config.app_config import get_app_config

        cfg = get_app_config()
        ckpt = getattr(cfg, "checkpointer", None)
        if ckpt is not None and getattr(ckpt, "type", "") == "postgres":
            conn = getattr(ckpt, "connection_string", None)
            if conn:
                return conn
    except Exception:
        logger.debug("RunJournal: could not read checkpointer config", exc_info=True)
    return os.getenv("DATABASE_URL")


# ---------------------------------------------------------------------------
# Connection helpers — we use async psycopg directly for tight integration
# with FastAPI's loop. Pool is created lazily on first use.
# ---------------------------------------------------------------------------


_pool = None  # AsyncConnectionPool | None
_schema_installed: bool = False


async def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    dsn = _resolve_dsn()
    if not dsn:
        logger.info("RunJournal: no DSN resolvable, journal stays disabled")
        return None
    try:
        from psycopg_pool import AsyncConnectionPool

        # min_size=0 so a closed pool doesn't keep idle conns; max_size kept
        # small because the journal is low-traffic.
        _pool = AsyncConnectionPool(conninfo=dsn, min_size=0, max_size=4, open=False)
        await _pool.open()
    except Exception:
        logger.exception("RunJournal: failed to open connection pool")
        _pool = None
    return _pool


async def _ensure_schema() -> bool:
    global _schema_installed
    if _schema_installed:
        return True
    pool = await _get_pool()
    if pool is None:
        return False
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(_SCHEMA_SQL)
        _schema_installed = True
        logger.info("RunJournal: schema verified / installed")
        return True
    except Exception:
        logger.exception("RunJournal: schema install failed")
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def init_run_journal() -> bool:
    """Initialise pool + schema. Safe to call multiple times.

    Returns True if the journal is operational, False otherwise (caller
    should treat the journal as a no-op).
    """
    if not _journal_enabled():
        return False
    return await _ensure_schema()


async def record_run_started(run_id: str, thread_id: str) -> None:
    if not _journal_enabled() or not run_id:
        return
    pool = await _get_pool()
    if pool is None:
        return
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO octo_harness_run_journal (run_id, thread_id, status) VALUES (%s, %s, 'running') ON CONFLICT (run_id) DO UPDATE SET     status='running', updated_at=now(), heartbeat_at=now()",
                    (run_id, thread_id),
                )
    except Exception:
        logger.exception("RunJournal: record_run_started failed run=%s thread=%s", run_id, thread_id)


async def heartbeat(run_id: str) -> None:
    if not _journal_enabled() or not run_id:
        return
    pool = await _get_pool()
    if pool is None:
        return
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE octo_harness_run_journal SET heartbeat_at=now(), updated_at=now() WHERE run_id=%s",
                    (run_id,),
                )
    except Exception:
        logger.exception("RunJournal: heartbeat failed run=%s", run_id)


async def record_run_finished(run_id: str, status: str = "success") -> None:
    if not _journal_enabled() or not run_id:
        return
    pool = await _get_pool()
    if pool is None:
        return
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE octo_harness_run_journal SET status=%s, finished_at=now(), updated_at=now() WHERE run_id=%s",
                    (status, run_id),
                )
    except Exception:
        logger.exception("RunJournal: record_run_finished failed run=%s", run_id)


async def find_stale_runs(stale_after_sec: int | None = None) -> list[dict[str, Any]]:
    """Return rows with status='running' and heartbeat older than threshold."""
    if not _journal_enabled():
        return []
    pool = await _get_pool()
    if pool is None:
        return []
    threshold = stale_after_sec if stale_after_sec is not None else _stale_after_seconds()
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT run_id, thread_id, status, created_at, heartbeat_at FROM octo_harness_run_journal WHERE status='running'   AND heartbeat_at < now() - (%s::int * interval '1 second')",
                    (threshold,),
                )
                rows = await cur.fetchall()
                cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]
    except Exception:
        logger.exception("RunJournal: find_stale_runs failed")
        return []


async def mark_orphans_on_startup() -> int:
    """Optionally mark still-`running` rows as orphaned. Returns count flipped.

    Default is observe-only so a process restart does not become a task-stop
    condition. Set OCTO_HARNESS_MARK_ORPHANS_ON_STARTUP=1 for manual recovery.
    """
    if not _journal_enabled():
        return 0
    if os.getenv("OCTO_HARNESS_MARK_ORPHANS_ON_STARTUP", "0").strip().lower() not in {"1", "true", "yes", "on"}:
        logger.info("RunJournal: startup orphan marking disabled; leaving running rows intact")
        return 0
    pool = await _get_pool()
    if pool is None:
        return 0
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("UPDATE octo_harness_run_journal SET status='orphaned_at_startup', updated_at=now(),     cancelled_reason='process restart' WHERE status='running' RETURNING run_id")
                rows = await cur.fetchall()
        if rows:
            logger.warning("RunJournal: marked %d runs as orphaned_at_startup", len(rows))
        return len(rows)
    except Exception:
        logger.exception("RunJournal: mark_orphans_on_startup failed")
        return 0


async def shutdown_run_journal() -> None:
    global _pool, _schema_installed
    if _pool is None:
        return
    try:
        await _pool.close()
    except Exception:
        logger.exception("RunJournal: pool close failed")
    _pool = None
    _schema_installed = False


__all__ = [
    "init_run_journal",
    "record_run_started",
    "record_run_finished",
    "heartbeat",
    "find_stale_runs",
    "mark_orphans_on_startup",
    "shutdown_run_journal",
]
