"""Shared schema + connection-pool + DSN resolution for the dispatcher.

Uses lazy connection pooling, predictable DSN priority and idempotent schema
bootstrap.
"""

from __future__ import annotations

import logging
import os
import socket
import uuid

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS octo_dispatch_queue (
    dispatch_id    text        PRIMARY KEY,
    kind           text        NOT NULL,
    payload        jsonb       NOT NULL,
    priority       smallint    NOT NULL DEFAULT 0,
    available_at   timestamptz NOT NULL DEFAULT now(),
    enqueued_at    timestamptz NOT NULL DEFAULT now(),
    claimed_by     text        NULL,
    claimed_at     timestamptz NULL,
    attempts       smallint    NOT NULL DEFAULT 0,
    max_attempts   smallint    NOT NULL DEFAULT 5,
    last_error     text        NULL,
    finished_at    timestamptz NULL,
    finished_state text        NULL
);
CREATE INDEX IF NOT EXISTS octo_dispatch_queue_claim_idx
    ON octo_dispatch_queue (available_at, priority DESC)
    WHERE finished_at IS NULL;
CREATE INDEX IF NOT EXISTS octo_dispatch_queue_kind_idx
    ON octo_dispatch_queue (kind, finished_at);

CREATE TABLE IF NOT EXISTS octo_dispatch_workers (
    worker_id     text        PRIMARY KEY,
    host          text        NOT NULL,
    pid           integer     NOT NULL,
    started_at    timestamptz NOT NULL DEFAULT now(),
    heartbeat_at  timestamptz NOT NULL DEFAULT now(),
    role          text        NOT NULL DEFAULT 'worker',
    draining      boolean     NOT NULL DEFAULT false,
    capabilities  jsonb       NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS octo_dispatch_workers_heartbeat_idx
    ON octo_dispatch_workers (heartbeat_at);
"""


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------


def dispatcher_enabled() -> bool:
    """True iff the dispatcher should run on this process."""
    return os.getenv("OCTO_DISPATCHER_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v >= minimum else default
    except ValueError:
        return default


def heartbeat_interval_sec() -> int:
    return _env_int("OCTO_DISPATCHER_HEARTBEAT_SEC", 5, minimum=1)


def worker_stale_after_sec() -> int:
    return _env_int("OCTO_DISPATCHER_WORKER_STALE_SEC", 30, minimum=10)


def leader_poll_interval_sec() -> int:
    return _env_int("OCTO_DISPATCHER_LEADER_POLL_SEC", 5, minimum=1)


def dispatch_poll_interval_sec() -> int:
    return _env_int("OCTO_DISPATCHER_DISPATCH_POLL_SEC", 2, minimum=1)


def job_stall_timeout_sec() -> int:
    return _env_int("OCTO_DISPATCHER_JOB_STALL_SEC", 600, minimum=30)


def drain_timeout_sec() -> int:
    return _env_int("OCTO_GRACEFUL_DRAIN_TIMEOUT", 600, minimum=10)


# ---------------------------------------------------------------------------
# Worker identity
# ---------------------------------------------------------------------------

_WORKER_ID: str | None = None


def worker_id() -> str:
    """Stable per-process worker id of the form host:pid:bootuuid."""
    global _WORKER_ID
    if _WORKER_ID is None:
        host = socket.gethostname()
        boot = uuid.uuid4().hex[:8]
        _WORKER_ID = f"{host}:{os.getpid()}:{boot}"
    return _WORKER_ID


def worker_host_pid() -> tuple[str, int]:
    return socket.gethostname(), os.getpid()


# ---------------------------------------------------------------------------
# DSN + pool
# ---------------------------------------------------------------------------

_pool = None  # AsyncConnectionPool | None
_schema_installed: bool = False


def _resolve_dsn() -> str | None:
    """Resolve Postgres DSN. Identical priority to run_journal."""
    override = os.getenv("OCTO_DISPATCHER_DSN")
    if override:
        return override
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
        logger.debug("Dispatcher: could not read checkpointer config", exc_info=True)
    return os.getenv("DATABASE_URL")


async def get_pool():
    """Return the lazily-opened pool, or ``None`` if unavailable."""
    global _pool
    if _pool is not None:
        return _pool
    dsn = _resolve_dsn()
    if not dsn:
        logger.info("Dispatcher: no DSN resolvable, dispatcher stays disabled")
        return None
    try:
        from psycopg_pool import AsyncConnectionPool

        # max_size=8: leader election + heartbeat + dispatch loop + queue ops
        # need a handful of concurrent conns. min_size=0 lets idle drain.
        _pool = AsyncConnectionPool(conninfo=dsn, min_size=0, max_size=8, open=False)
        await _pool.open()
    except Exception:
        logger.exception("Dispatcher: failed to open connection pool")
        _pool = None
    return _pool


async def ensure_schema() -> bool:
    """Idempotently create dispatcher tables. Safe to call repeatedly."""
    global _schema_installed
    if _schema_installed:
        return True
    pool = await get_pool()
    if pool is None:
        return False
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(SCHEMA_SQL)
        _schema_installed = True
        logger.info("Dispatcher: schema verified / installed")
        return True
    except Exception:
        logger.exception("Dispatcher: schema install failed")
        return False


async def close_pool() -> None:
    global _pool, _schema_installed
    if _pool is None:
        return
    try:
        await _pool.close()
    except Exception:
        logger.exception("Dispatcher: pool close failed")
    _pool = None
    _schema_installed = False


__all__ = [
    "SCHEMA_SQL",
    "dispatcher_enabled",
    "heartbeat_interval_sec",
    "worker_stale_after_sec",
    "leader_poll_interval_sec",
    "dispatch_poll_interval_sec",
    "job_stall_timeout_sec",
    "drain_timeout_sec",
    "worker_id",
    "worker_host_pid",
    "get_pool",
    "ensure_schema",
    "close_pool",
]
