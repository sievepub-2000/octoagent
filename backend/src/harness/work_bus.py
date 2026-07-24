"""Harness event bus: in-process fanout with terminal PostgreSQL archival."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)
_TERMINAL_KINDS = {"plan_completed", "plan_failed", "plan_cancelled", "done"}


@dataclass(slots=True)
class WorkBusEvent:
    thread_id: str
    kind: str
    step_id: str | None = None
    plan_id: str | None = None
    status: str | None = None
    title: str | None = None
    detail: str | None = None
    role: str | None = None
    tool_name: str | None = None
    input: Any = None
    output: Any = None
    error: str | None = None
    duration_ms: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


class WorkBus:
    """Process-local live stream; PostgreSQL is the durable terminal store."""

    def __init__(self, *, max_memory_events: int = 500) -> None:
        self._events: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=max_memory_events))
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self._sequence = 0
        self._postgres_pool: Any | None = None
        self._initialised = False
        self._schema_ready = False

    async def initialize(self) -> None:
        if self._initialised:
            return
        async with self._init_lock:
            if self._initialised:
                return
            await self._init_postgres()
            self._initialised = True

    async def _init_postgres(self) -> None:
        dsn = _resolve_postgres_dsn()
        if not dsn:
            logger.info("WorkBus: live-only mode; PostgreSQL DSN not configured")
            return
        try:
            from psycopg_pool import AsyncConnectionPool

            self._postgres_pool = AsyncConnectionPool(conninfo=dsn, min_size=0, max_size=4, open=False)
            await self._postgres_pool.open()
            if await self._ensure_schema():
                logger.info("WorkBus: PostgreSQL archive connected")
        except Exception:
            self._postgres_pool = None
            logger.exception("WorkBus: PostgreSQL archive initialization failed")

    async def _ensure_schema(self) -> bool:
        if self._schema_ready:
            return True
        if self._postgres_pool is None:
            return False
        async with self._postgres_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS work_bus_trace (
                        trace_id TEXT PRIMARY KEY,
                        thread_id TEXT NOT NULL,
                        plan_id TEXT,
                        status TEXT NOT NULL,
                        event_count INTEGER NOT NULL DEFAULT 0,
                        events JSONB NOT NULL,
                        archived_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    CREATE INDEX IF NOT EXISTS work_bus_trace_thread_idx
                        ON work_bus_trace (thread_id, archived_at DESC)
                    """
                )
        self._schema_ready = True
        return True

    async def publish_step_event(self, **kwargs: Any) -> dict[str, Any]:
        await self.initialize()
        event = WorkBusEvent(**kwargs)
        async with self._lock:
            self._sequence += 1
            event.sequence = self._sequence
            payload = event.to_dict()
            self._events[event.thread_id].append(payload)
            subscribers = list(self._subscribers.get(event.thread_id, set()))
        for queue in subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(payload)
        if event.kind in _TERMINAL_KINDS:
            await self.archive_to_postgres(event.thread_id, status=event.status or event.kind)
        return payload

    async def get_active_steps(self, thread_id: str) -> list[dict[str, Any]]:
        await self.initialize()
        async with self._lock:
            return list(self._events.get(thread_id, ()))

    async def subscribe(self, thread_id: str) -> AsyncIterator[dict[str, Any]]:
        await self.initialize()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        async with self._lock:
            self._subscribers[thread_id].add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            async with self._lock:
                self._subscribers[thread_id].discard(queue)
                if not self._subscribers[thread_id]:
                    self._subscribers.pop(thread_id, None)

    async def archive_to_postgres(self, thread_id: str, *, status: str = "done") -> bool:
        if self._postgres_pool is None or not await self._ensure_schema():
            return False
        events = await self.get_active_steps(thread_id)
        if not events:
            return False
        plan_id = next((str(event.get("plan_id")) for event in events if event.get("plan_id")), None)
        trace_id = f"{thread_id}:{plan_id or events[-1].get('event_id')}"
        try:
            async with self._postgres_pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO work_bus_trace
                            (trace_id, thread_id, plan_id, status, event_count, events)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (trace_id) DO UPDATE SET
                            status = EXCLUDED.status,
                            event_count = EXCLUDED.event_count,
                            events = EXCLUDED.events,
                            archived_at = now()
                        """,
                        (trace_id, thread_id, plan_id, status, len(events), json.dumps(events, ensure_ascii=False, default=str)),
                    )
            return True
        except Exception:
            logger.exception("WorkBus: archive failed for thread %s", thread_id)
            return False

    async def close(self) -> None:
        if self._postgres_pool is not None:
            with contextlib.suppress(Exception):
                await self._postgres_pool.close()


_work_bus: WorkBus | None = None


def get_work_bus() -> WorkBus:
    global _work_bus
    if _work_bus is None:
        _work_bus = WorkBus()
    return _work_bus


def _resolve_postgres_dsn() -> str | None:
    override = os.getenv("OCTO_WORK_BUS_POSTGRES_DSN")
    if override:
        return override
    try:
        from src.runtime.config import get_app_config

        checkpoint = getattr(get_app_config(), "checkpointer", None)
        connection = getattr(checkpoint, "connection_string", None)
        if connection:
            return str(connection)
    except Exception:
        logger.debug("WorkBus: could not read checkpointer config", exc_info=True)
    return os.getenv("DATABASE_URL")


__all__ = ["WorkBus", "WorkBusEvent", "get_work_bus"]
