"""SQLite checkpointer maintenance helpers.

LangGraph API can opportunistically call newer async maintenance hooks when
they are present.  Older ``langgraph-checkpoint-sqlite`` versions still work
for normal checkpointing but do not expose every hook, which leaves long-lived
servers without a stable pruning/copy/delete surface.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)


def _normalize_thread_pair(
    source_thread_id: str | None,
    target_thread_id: str | None,
    kwargs: dict[str, Any],
) -> tuple[str, str]:
    source = source_thread_id or kwargs.get("source_thread_id") or kwargs.get("from_thread_id") or kwargs.get("thread_id")
    target = target_thread_id or kwargs.get("target_thread_id") or kwargs.get("to_thread_id") or kwargs.get("new_thread_id")
    if not source or not target:
        raise ValueError("source_thread_id and target_thread_id are required")
    return str(source), str(target)


def _normalize_run_ids(run_ids: Iterable[str] | str | None) -> list[str]:
    if run_ids is None:
        return []
    if isinstance(run_ids, str):
        return [run_ids]
    return [str(run_id) for run_id in run_ids if str(run_id)]


def _normalize_keep_latest(value: int | None) -> int:
    if value is None:
        return 50
    return max(int(value), 1)


class AsyncSqliteMaintenanceSaver:
    """Delegating wrapper that adds async maintenance hooks to SQLite savers."""

    def __init__(self, saver: Any) -> None:
        self._saver = saver
        self._maintenance_metrics: dict[str, dict[str, int]] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._saver, name)

    @property
    def conn(self) -> Any:
        return self._saver.conn

    @property
    def lock(self) -> Any:
        return self._saver.lock

    @property
    def maintenance_metrics(self) -> dict[str, dict[str, int]]:
        return deepcopy(self._maintenance_metrics)

    def _record_maintenance(self, operation: str, result: dict[str, int], **details: Any) -> None:
        metrics = self._maintenance_metrics.setdefault(operation, {"calls": 0})
        metrics["calls"] += 1
        for key, value in result.items():
            metrics[key] = metrics.get(key, 0) + int(value)
        logger.info(
            "SQLite checkpointer maintenance: operation=%s result=%s details=%s",
            operation,
            result,
            details,
        )

    async def adelete_thread(self, thread_id: str) -> None:
        deleter = getattr(self._saver, "adelete_thread", None)
        if deleter is not None:
            await deleter(thread_id)
            self._record_maintenance("delete_thread", {"threads": 1}, thread_id=thread_id)
            return
        async with self.lock, self.conn.cursor() as cur:
            await cur.execute("DELETE FROM writes WHERE thread_id = ?", (str(thread_id),))
            await cur.execute("DELETE FROM checkpoints WHERE thread_id = ?", (str(thread_id),))
            await self.conn.commit()
        self._record_maintenance("delete_thread", {"threads": 1}, thread_id=thread_id)

    async def acopy_thread(
        self,
        source_thread_id: str | None = None,
        target_thread_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, int]:
        source, target = _normalize_thread_pair(source_thread_id, target_thread_id, kwargs)
        async with self.lock, self.conn.cursor() as cur:
            await cur.execute(
                """
                INSERT OR REPLACE INTO checkpoints (
                    thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                    type, checkpoint, metadata
                )
                SELECT ?, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                    type, checkpoint, metadata
                FROM checkpoints
                WHERE thread_id = ?
                """,
                (target, source),
            )
            checkpoints = cur.rowcount if cur.rowcount is not None else 0
            await cur.execute(
                """
                INSERT OR REPLACE INTO writes (
                    thread_id, checkpoint_ns, checkpoint_id, task_id, idx,
                    channel, type, value
                )
                SELECT ?, checkpoint_ns, checkpoint_id, task_id, idx,
                    channel, type, value
                FROM writes
                WHERE thread_id = ?
                """,
                (target, source),
            )
            writes = cur.rowcount if cur.rowcount is not None else 0
            await self.conn.commit()
        result = {"checkpoints": checkpoints, "writes": writes}
        self._record_maintenance(
            "copy_thread",
            result,
            source_thread_id=source,
            target_thread_id=target,
        )
        return result

    async def adelete_for_runs(
        self,
        thread_id: str | None = None,
        run_ids: Sequence[str] | str | None = None,
        **kwargs: Any,
    ) -> dict[str, int]:
        target_thread_id = str(thread_id or kwargs.get("thread_id") or "")
        target_run_ids = _normalize_run_ids(run_ids or kwargs.get("run_ids"))
        if not target_thread_id or not target_run_ids:
            self._record_maintenance(
                "delete_for_runs",
                {"writes": 0},
                thread_id=target_thread_id,
                run_count=len(target_run_ids),
            )
            return {"writes": 0}

        placeholders = ",".join("?" for _ in target_run_ids)
        async with self.lock, self.conn.cursor() as cur:
            await cur.execute(
                f"""
                DELETE FROM writes
                WHERE thread_id = ?
                  AND task_id IN ({placeholders})
                """,
                (target_thread_id, *target_run_ids),
            )
            writes = cur.rowcount if cur.rowcount is not None else 0
            await self.conn.commit()
        result = {"writes": writes}
        self._record_maintenance(
            "delete_for_runs",
            result,
            thread_id=target_thread_id,
            run_count=len(target_run_ids),
        )
        return result

    async def aprune(
        self,
        thread_id: str | None = None,
        *,
        keep_latest: int | None = None,
        keep_last: int | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> dict[str, int]:
        target_thread_id = thread_id or kwargs.get("thread_id")
        keep = _normalize_keep_latest(keep_latest or keep_last or limit)
        thread_filter = "WHERE (? IS NULL OR thread_id = ?)"
        params: tuple[Any, ...] = (target_thread_id, target_thread_id, keep)

        async with self.lock, self.conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FROM writes WHERE (? IS NULL OR thread_id = ?)",
                (target_thread_id, target_thread_id),
            )
            writes_before = int((await cur.fetchone())[0])
            await cur.execute(
                "SELECT count(*) FROM checkpoints WHERE (? IS NULL OR thread_id = ?)",
                (target_thread_id, target_thread_id),
            )
            checkpoints_before = int((await cur.fetchone())[0])
            await cur.execute(
                f"""
                WITH ranked AS (
                    SELECT thread_id, checkpoint_ns, checkpoint_id,
                           row_number() OVER (
                               PARTITION BY thread_id, checkpoint_ns
                               ORDER BY rowid DESC
                           ) AS rn
                    FROM checkpoints
                    {thread_filter}
                )
                DELETE FROM writes
                WHERE EXISTS (
                    SELECT 1
                    FROM ranked
                    WHERE ranked.rn > ?
                      AND ranked.thread_id = writes.thread_id
                      AND ranked.checkpoint_ns = writes.checkpoint_ns
                      AND ranked.checkpoint_id = writes.checkpoint_id
                )
                """,
                params,
            )
            await cur.execute(
                f"""
                WITH ranked AS (
                    SELECT thread_id, checkpoint_ns, checkpoint_id,
                           row_number() OVER (
                               PARTITION BY thread_id, checkpoint_ns
                               ORDER BY rowid DESC
                           ) AS rn
                    FROM checkpoints
                    {thread_filter}
                )
                DELETE FROM checkpoints
                WHERE EXISTS (
                    SELECT 1
                    FROM ranked
                    WHERE ranked.rn > ?
                      AND ranked.thread_id = checkpoints.thread_id
                      AND ranked.checkpoint_ns = checkpoints.checkpoint_ns
                      AND ranked.checkpoint_id = checkpoints.checkpoint_id
                )
                """,
                params,
            )
            await self.conn.commit()
            await cur.execute(
                "SELECT count(*) FROM writes WHERE (? IS NULL OR thread_id = ?)",
                (target_thread_id, target_thread_id),
            )
            writes_after = int((await cur.fetchone())[0])
            await cur.execute(
                "SELECT count(*) FROM checkpoints WHERE (? IS NULL OR thread_id = ?)",
                (target_thread_id, target_thread_id),
            )
            checkpoints_after = int((await cur.fetchone())[0])
        result = {
            "checkpoints": max(checkpoints_before - checkpoints_after, 0),
            "writes": max(writes_before - writes_after, 0),
        }
        self._record_maintenance("prune", result, thread_id=target_thread_id, keep_latest=keep)
        return result


def ensure_async_sqlite_maintenance_hooks(saver: Any) -> Any:
    """Return a saver with the async maintenance hooks LangGraph API expects."""

    required = ("adelete_for_runs", "acopy_thread", "aprune")
    if all(hasattr(saver, name) for name in required):
        return saver
    return AsyncSqliteMaintenanceSaver(saver)
