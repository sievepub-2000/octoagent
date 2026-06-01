"""Async checkpointer factory.

Provides an **async context manager** for long-running async servers that need
proper resource cleanup.

Supported backends: memory, sqlite, postgres.

Usage (e.g. FastAPI lifespan)::

    from src.agents.checkpointer.async_provider import make_checkpointer

    async with make_checkpointer() as checkpointer:
        app.state.checkpointer = checkpointer  # InMemorySaver if not configured

For sync usage see :mod:`src.agents.checkpointer.provider`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Iterable, Sequence

from langgraph.types import Checkpointer

from src.agents.checkpointer.provider import (
    POSTGRES_CONN_REQUIRED,
    POSTGRES_INSTALL,
    SQLITE_INSTALL,
    _resolve_sqlite_conn_str,
)
from src.agents.checkpointer.sqlite_maintenance import ensure_async_sqlite_maintenance_hooks

logger = logging.getLogger(__name__)


class OctoAgentAsyncPostgresSaverMixin:
    """LangGraph maintenance hooks for the Postgres checkpointer."""

    async def acopy_thread(
        self,
        source_thread_id: str | None = None,
        target_thread_id: str | None = None,
        **kwargs: object,
    ) -> None:
        """Bulk-copy a thread's checkpoints/blobs/writes within Postgres.

        Replaces the langgraph_api generic fallback that re-inserts
        checkpoints one-by-one via aput/aput_writes (slow). ON CONFLICT
        DO NOTHING makes the copy idempotent and safe for a fresh target.
        """
        source = str(source_thread_id) if source_thread_id is not None else None
        target = str(target_thread_id) if target_thread_id is not None else None
        if not source:
            source = str(kwargs.get("source") or kwargs.get("from_thread_id") or "")
        if not target:
            target = str(kwargs.get("target") or kwargs.get("to_thread_id") or "")
        if not source or not target:
            raise ValueError("acopy_thread requires source and target thread ids")
        async with self._cursor(pipeline=True) as cur:
            await cur.execute(
                """
                INSERT INTO checkpoint_blobs (thread_id, checkpoint_ns, channel, version, type, blob)
                SELECT %s, checkpoint_ns, channel, version, type, blob
                FROM checkpoint_blobs WHERE thread_id = %s
                ON CONFLICT (thread_id, checkpoint_ns, channel, version) DO NOTHING
                """,
                (target, source),
            )
            await cur.execute(
                """
                INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata)
                SELECT %s, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata
                FROM checkpoints WHERE thread_id = %s
                ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id) DO NOTHING
                """,
                (target, source),
            )
            await cur.execute(
                """
                INSERT INTO checkpoint_writes (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, blob, task_path)
                SELECT %s, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, blob, task_path
                FROM checkpoint_writes WHERE thread_id = %s
                ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id, task_id, idx) DO NOTHING
                """,
                (target, source),
            )

    async def adelete_for_runs(self, run_ids: Iterable[str]) -> None:
        normalized = [str(run_id) for run_id in run_ids if run_id]
        if not normalized:
            return
        async with self._cursor(pipeline=True) as cur:
            await cur.execute(
                """
                WITH doomed AS (
                    SELECT thread_id, checkpoint_ns, checkpoint_id
                    FROM checkpoints
                    WHERE metadata ->> 'run_id' = ANY(%s)
                )
                DELETE FROM checkpoint_writes writes
                USING doomed
                WHERE writes.thread_id = doomed.thread_id
                  AND writes.checkpoint_ns = doomed.checkpoint_ns
                  AND writes.checkpoint_id = doomed.checkpoint_id
                """,
                (normalized,),
            )
            await cur.execute(
                "DELETE FROM checkpoints WHERE metadata ->> 'run_id' = ANY(%s)",
                (normalized,),
            )
            await cur.execute(
                """
                DELETE FROM checkpoint_blobs blobs
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM checkpoints checkpoints,
                         jsonb_each_text(checkpoints.checkpoint -> 'channel_versions') AS versions(channel, version)
                    WHERE checkpoints.thread_id = blobs.thread_id
                      AND checkpoints.checkpoint_ns = blobs.checkpoint_ns
                      AND versions.channel = blobs.channel
                      AND versions.version = blobs.version
                )
                """,
            )

    async def aprune(self, thread_ids: Sequence[str], *, strategy: str = "keep_latest") -> None:
        if strategy == "delete_all":
            for thread_id in thread_ids:
                await self.adelete_thread(str(thread_id))
            return
        if strategy != "keep_latest":
            raise ValueError(f"Unsupported checkpoint prune strategy: {strategy!r}")

        for thread_id in [str(thread_id) for thread_id in thread_ids if thread_id]:
            async with self._cursor(pipeline=True) as cur:
                await cur.execute(
                    """
                    WITH latest AS (
                        SELECT DISTINCT ON (checkpoint_ns)
                            thread_id,
                            checkpoint_ns,
                            checkpoint_id
                        FROM checkpoints
                        WHERE thread_id = %s
                        ORDER BY checkpoint_ns, checkpoint_id DESC
                    ),
                    doomed AS (
                        SELECT checkpoints.thread_id, checkpoints.checkpoint_ns, checkpoints.checkpoint_id
                        FROM checkpoints
                        LEFT JOIN latest
                          ON latest.thread_id = checkpoints.thread_id
                         AND latest.checkpoint_ns = checkpoints.checkpoint_ns
                         AND latest.checkpoint_id = checkpoints.checkpoint_id
                        WHERE checkpoints.thread_id = %s
                          AND latest.checkpoint_id IS NULL
                    )
                    DELETE FROM checkpoint_writes writes
                    USING doomed
                    WHERE writes.thread_id = doomed.thread_id
                      AND writes.checkpoint_ns = doomed.checkpoint_ns
                      AND writes.checkpoint_id = doomed.checkpoint_id
                    """,
                    (thread_id, thread_id),
                )
                await cur.execute(
                    """
                    WITH latest AS (
                        SELECT DISTINCT ON (checkpoint_ns)
                            thread_id,
                            checkpoint_ns,
                            checkpoint_id
                        FROM checkpoints
                        WHERE thread_id = %s
                        ORDER BY checkpoint_ns, checkpoint_id DESC
                    )
                    DELETE FROM checkpoints checkpoints
                    WHERE checkpoints.thread_id = %s
                      AND NOT EXISTS (
                          SELECT 1
                          FROM latest
                          WHERE latest.thread_id = checkpoints.thread_id
                            AND latest.checkpoint_ns = checkpoints.checkpoint_ns
                            AND latest.checkpoint_id = checkpoints.checkpoint_id
                      )
                    """,
                    (thread_id, thread_id),
                )
                await cur.execute(
                    """
                    UPDATE checkpoints checkpoints
                    SET parent_checkpoint_id = NULL
                    WHERE checkpoints.thread_id = %s
                      AND checkpoints.parent_checkpoint_id IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1
                          FROM checkpoints parents
                          WHERE parents.thread_id = checkpoints.thread_id
                            AND parents.checkpoint_ns = checkpoints.checkpoint_ns
                            AND parents.checkpoint_id = checkpoints.parent_checkpoint_id
                      )
                    """,
                    (thread_id,),
                )
            await self._delete_orphaned_blobs()

    async def _delete_orphaned_blobs(self) -> None:
        async with self._cursor(pipeline=True) as cur:
            await cur.execute(
                """
                DELETE FROM checkpoint_blobs blobs
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM checkpoints checkpoints,
                         jsonb_each_text(checkpoints.checkpoint -> 'channel_versions') AS versions(channel, version)
                    WHERE checkpoints.thread_id = blobs.thread_id
                      AND checkpoints.checkpoint_ns = blobs.checkpoint_ns
                      AND versions.channel = blobs.channel
                      AND versions.version = blobs.version
                )
                """,
            )


@contextlib.contextmanager
def _timed(label: str):
    """Log how long the wrapped block took at INFO level."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        logger.info("%s took %.3fs", label, time.perf_counter() - t0)


# ---------------------------------------------------------------------------
# Async factory
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def _async_checkpointer(config) -> AsyncIterator[Checkpointer]:
    """Async context manager that constructs and tears down a checkpointer."""
    if config.type == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        yield InMemorySaver()
        return

    if config.type == "sqlite":
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        except ImportError as exc:
            raise ImportError(SQLITE_INSTALL) from exc

        import pathlib

        conn_str = _resolve_sqlite_conn_str(config.connection_string or "store.db")
        # Only create parent directories for real filesystem paths
        if conn_str != ":memory:" and not conn_str.startswith("file:"):
            await asyncio.to_thread(pathlib.Path(conn_str).parent.mkdir, parents=True, exist_ok=True)
        with _timed(f"checkpointer.sqlite.open conn={conn_str}"):
            async with AsyncSqliteSaver.from_conn_string(conn_str) as saver:
                with _timed("checkpointer.sqlite.setup"):
                    await saver.setup()
                yield ensure_async_sqlite_maintenance_hooks(saver)
        return

    if config.type == "postgres":
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        except ImportError as exc:
            raise ImportError(POSTGRES_INSTALL) from exc

        class OctoAgentAsyncPostgresSaver(OctoAgentAsyncPostgresSaverMixin, AsyncPostgresSaver):
            pass

        if not config.connection_string:
            raise ValueError(POSTGRES_CONN_REQUIRED)

        async with OctoAgentAsyncPostgresSaver.from_conn_string(config.connection_string) as saver:
            await saver.setup()
            yield saver
        return

    raise ValueError(f"Unknown checkpointer type: {config.type!r}")


# ---------------------------------------------------------------------------
# Public async context manager
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def make_checkpointer() -> AsyncIterator[Checkpointer]:
    """Async context manager that yields a checkpointer for the caller's lifetime.
    Resources are opened on enter and closed on exit — no global state::

        async with make_checkpointer() as checkpointer:
            app.state.checkpointer = checkpointer

    Yields an ``InMemorySaver`` when no checkpointer is configured in *config.yaml*.
    """

    # Keep the custom-checkpointer import path lightweight. LangGraph imports
    # this module before it asks for the saver; importing the full app config at
    # module load time also initializes model/provider config and slows startup.
    from src.runtime.config.app_config import get_app_config

    config = get_app_config()

    if config.checkpointer is None:
        from langgraph.checkpoint.memory import InMemorySaver

        yield InMemorySaver()
        return

    async with _async_checkpointer(config.checkpointer) as saver:
        yield saver
