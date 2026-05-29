"""Realtime work-bus for DeepAgent workflow inspection.

The bus keeps the hot execution path lightweight:

* Redis is optional. When ``redis`` is installed and reachable, events are
  mirrored to a Redis hash and Pub/Sub channel for cross-process fanout.
* PostgreSQL archival is optional. When a DSN is available, terminal plan
  events archive the full trace once into ``work_bus_trace``.
* Without Redis/Postgres the service degrades to an in-process broadcaster so
  local development and tests do not require extra infrastructure.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "octoagent:workbus"
_REDIS_CHANNEL = "octoagent:workbus:events"
_TERMINAL_KINDS = {"plan_completed", "plan_failed", "plan_cancelled", "done"}


@dataclass(slots=True)
class WorkBusEvent:
    """Single workflow event published by the execution harness."""

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
        return {
            "event_id": self.event_id,
            "thread_id": self.thread_id,
            "plan_id": self.plan_id,
            "step_id": self.step_id,
            "kind": self.kind,
            "status": self.status,
            "title": self.title,
            "detail": self.detail,
            "role": self.role,
            "tool_name": self.tool_name,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "payload": self.payload,
            "created_at": self.created_at,
            "sequence": self.sequence,
        }


class WorkBusRedis:
    """Redis-backed work bus with in-process fallback."""

    def __init__(self, *, max_memory_events: int = 500) -> None:
        self._max_memory_events = max_memory_events
        self._events: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=self._max_memory_events)
        )
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._sequence = 0
        self._redis: Any | None = None
        self._postgres_pool: Any | None = None
        self._schema_ready = False
        self._init_lock = asyncio.Lock()
        self._initialised = False
        self._last_redis_error = 0.0

    async def initialize(self) -> None:
        """Open optional Redis/Postgres connections once."""
        if self._initialised:
            return
        async with self._init_lock:
            if self._initialised:
                return
            await self._init_redis()
            await self._init_postgres()
            self._initialised = True

    async def _init_redis(self) -> None:
        url = os.getenv("OCTO_WORK_BUS_REDIS_URL", "redis://127.0.0.1:6379/0").strip()
        if not url or os.getenv("OCTO_WORK_BUS_REDIS", "1").strip().lower() in {
            "0",
            "false",
            "no",
            "off",
        }:
            return
        try:
            from redis import asyncio as redis_asyncio  # type: ignore[import-not-found]

            client = redis_asyncio.from_url(url, decode_responses=True)
            await client.ping()
            self._redis = client
            logger.info("WorkBus: Redis connected")
        except Exception as exc:
            self._redis = None
            logger.info("WorkBus: Redis unavailable, using in-process fanout: %s", exc)

    async def _init_postgres(self) -> None:
        dsn = _resolve_postgres_dsn()
        if not dsn:
            return
        try:
            from psycopg_pool import AsyncConnectionPool

            pool = AsyncConnectionPool(conninfo=dsn, min_size=0, max_size=4, open=False)
            await pool.open()
            self._postgres_pool = pool
            await self._ensure_schema()
            logger.info("WorkBus: PostgreSQL archive connected")
        except Exception:
            self._postgres_pool = None
            logger.warning("WorkBus: PostgreSQL archive unavailable", exc_info=True)

    async def _ensure_schema(self) -> bool:
        if self._schema_ready:
            return True
        if self._postgres_pool is None:
            return False
        try:
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
                            ON work_bus_trace (thread_id, archived_at DESC);
                        """
                    )
            self._schema_ready = True
            return True
        except Exception:
            logger.warning("WorkBus: schema check failed", exc_info=True)
            return False

    async def publish_step_event(self, **kwargs: Any) -> dict[str, Any]:
        """Publish one event and return its serialized payload."""
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

        await self._mirror_to_redis(payload)
        if event.kind in _TERMINAL_KINDS:
            await self.archive_to_postgres(event.thread_id, status=event.status or event.kind)
        return payload

    async def _mirror_to_redis(self, payload: dict[str, Any]) -> None:
        if self._redis is None:
            return
        try:
            key = f"{_REDIS_KEY_PREFIX}:{payload['thread_id']}"
            encoded = json.dumps(payload, ensure_ascii=False, default=str)
            await self._redis.hset(key, payload["event_id"], encoded)
            await self._redis.expire(key, _env_int("OCTO_WORK_BUS_REDIS_TTL_SEC", 86_400))
            await self._redis.publish(_REDIS_CHANNEL, encoded)
        except Exception:
            now = time.monotonic()
            if now - self._last_redis_error > 30:
                logger.warning("WorkBus: Redis mirror failed", exc_info=True)
                self._last_redis_error = now

    async def get_active_steps(self, thread_id: str) -> list[dict[str, Any]]:
        """Return cached events for a thread, newest sequence last."""
        await self.initialize()
        async with self._lock:
            local = list(self._events.get(thread_id, ()))
        if local or self._redis is None:
            return local
        try:
            raw = await self._redis.hgetall(f"{_REDIS_KEY_PREFIX}:{thread_id}")
            parsed = [json.loads(value) for value in raw.values()]
            parsed.sort(key=lambda item: int(item.get("sequence") or 0))
            return parsed
        except Exception:
            logger.warning("WorkBus: Redis read failed", exc_info=True)
            return []

    async def subscribe(self, thread_id: str) -> AsyncIterator[dict[str, Any]]:
        """Yield live events for one thread until the caller disconnects."""
        await self.initialize()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        redis_task: asyncio.Task[None] | None = None
        async with self._lock:
            self._subscribers[thread_id].add(queue)
        if self._redis is not None:
            redis_task = asyncio.create_task(
                self._forward_redis_pubsub(thread_id, queue),
                name=f"work-bus-redis-{thread_id[:8]}",
            )
        try:
            while True:
                yield await queue.get()
        finally:
            async with self._lock:
                self._subscribers[thread_id].discard(queue)
                if not self._subscribers[thread_id]:
                    self._subscribers.pop(thread_id, None)
            if redis_task is not None:
                redis_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await redis_task

    async def _forward_redis_pubsub(
        self,
        thread_id: str,
        queue: asyncio.Queue[dict[str, Any]],
    ) -> None:
        if self._redis is None:
            return
        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(_REDIS_CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    payload = json.loads(message.get("data") or "{}")
                except json.JSONDecodeError:
                    continue
                if payload.get("thread_id") == thread_id:
                    with contextlib.suppress(asyncio.QueueFull):
                        queue.put_nowait(payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("WorkBus: Redis pubsub listener failed", exc_info=True)
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(_REDIS_CHANNEL)
                await pubsub.close()

    async def archive_to_postgres(self, thread_id: str, *, status: str = "done") -> bool:
        """Persist one compact trace row for the thread."""
        if self._postgres_pool is None or not await self._ensure_schema():
            return False
        events = await self.get_active_steps(thread_id)
        if not events:
            return False
        plan_id = next((str(e.get("plan_id")) for e in events if e.get("plan_id")), None)
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
                        (
                            trace_id,
                            thread_id,
                            plan_id,
                            status,
                            len(events),
                            json.dumps(events, ensure_ascii=False, default=str),
                        ),
                    )
            return True
        except Exception:
            logger.warning("WorkBus: archive failed for thread %s", thread_id, exc_info=True)
            return False

    async def close(self) -> None:
        if self._redis is not None:
            with contextlib.suppress(Exception):
                await self._redis.close()
        if self._postgres_pool is not None:
            with contextlib.suppress(Exception):
                await self._postgres_pool.close()


_work_bus: WorkBusRedis | None = None


def get_work_bus() -> WorkBusRedis:
    global _work_bus
    if _work_bus is None:
        _work_bus = WorkBusRedis()
    return _work_bus


def _resolve_postgres_dsn() -> str | None:
    override = os.getenv("OCTO_WORK_BUS_POSTGRES_DSN")
    if override:
        return override
    try:
        from src.runtime.config import get_app_config

        cfg = get_app_config()
        ckpt = getattr(cfg, "checkpointer", None)
        if ckpt is not None and getattr(ckpt, "type", "") == "postgres":
            conn = getattr(ckpt, "connection_string", None)
            if conn:
                return conn
    except Exception:
        logger.debug("WorkBus: could not read checkpointer config", exc_info=True)
    return os.getenv("DATABASE_URL")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


__all__ = ["WorkBusEvent", "WorkBusRedis", "get_work_bus"]
