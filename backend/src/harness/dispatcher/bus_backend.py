"""Optional Postgres backend for :class:`channels.message_bus.MessageBus`
(Phase 6, stage 6.3).

Default behaviour unchanged: the in-memory ``MessageBus`` is what the
channel service constructs. To switch on durability:

    OCTO_DISPATCHER_ENABLED=1
    OCTO_DISPATCH_BACKEND=postgres

When active, ``publish_inbound()`` writes the message to
``octo_dispatch_queue`` (kind = ``channel_inbound``) before returning;
``get_inbound()`` claims one due row and reconstitutes an
:class:`InboundMessage`. Crash/restart no longer drops in-flight
messages.

This module deliberately does NOT auto-wire itself into the channel
service. Call :func:`maybe_install_postgres_bus_backend` from the
channel-service startup when the env flag is set.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any

from src.gateway.channels.message_bus import (
    InboundMessage,
    InboundMessageType,
    MessageBus,
)
from src.harness.dispatcher.queue import (
    ack_dispatch,
    claim_dispatch,
    enqueue_dispatch,
)
from src.harness.dispatcher.schema import dispatcher_enabled

logger = logging.getLogger(__name__)

_INBOUND_KIND = "channel_inbound"


def bus_backend_is_postgres() -> bool:
    return dispatcher_enabled() and os.getenv("OCTO_DISPATCH_BACKEND", "inmemory").strip().lower() == "postgres"


def _to_payload(msg: InboundMessage) -> dict[str, Any]:
    return {
        "channel_name": msg.channel_name,
        "chat_id": msg.chat_id,
        "user_id": msg.user_id,
        "text": msg.text,
        "msg_type": msg.msg_type.value,
        "thread_ts": msg.thread_ts,
        "topic_id": msg.topic_id,
        "files": msg.files,
        "metadata": msg.metadata,
        "created_at": msg.created_at,
    }


def _from_payload(p: dict[str, Any]) -> InboundMessage:
    return InboundMessage(
        channel_name=p.get("channel_name", ""),
        chat_id=p.get("chat_id", ""),
        user_id=p.get("user_id", ""),
        text=p.get("text", ""),
        msg_type=InboundMessageType(p.get("msg_type") or InboundMessageType.CHAT.value),
        thread_ts=p.get("thread_ts"),
        topic_id=p.get("topic_id"),
        files=p.get("files") or [],
        metadata=p.get("metadata") or {},
        created_at=float(p.get("created_at") or time.time()),
    )


class PostgresInboundBus(MessageBus):
    """``MessageBus`` whose inbound path is durable Postgres-backed.

    Outbound dispatch stays in-memory (channels are alive-while-process
    so a callback-list is the right semantics).
    """

    async def publish_inbound(self, msg: InboundMessage) -> None:  # type: ignore[override]
        # Also push to in-memory queue so a same-process consumer sees
        # it immediately without waiting for a claim poll.
        await super().publish_inbound(msg)
        try:
            await enqueue_dispatch(
                _INBOUND_KIND,
                _to_payload(msg),
                dispatch_id=msg.metadata.get("dispatch_id") or uuid.uuid4().hex,
                max_attempts=int(os.getenv("OCTO_DISPATCH_CHANNEL_MAX_ATTEMPTS", "5") or 5),
            )
        except Exception:
            logger.exception("[Bus] postgres enqueue failed; in-memory fallback only")

    async def get_inbound(self) -> InboundMessage:  # type: ignore[override]
        """Prefer in-memory queue (low latency); fall back to claim poll."""
        # Fast path: in-memory queue has something already.
        if not self._inbound_queue.empty():
            return await self._inbound_queue.get()
        # Slow path: poll Postgres for a claim. We sleep between polls
        # rather than blocking the loop. LISTEN/NOTIFY wake-up can be
        # added later; for now a 1-2 s poll cadence is fine for the
        # channel-inbound traffic shape.
        poll_interval = float(os.getenv("OCTO_DISPATCH_CLAIM_POLL_SEC", "2") or 2)
        while True:
            row = await claim_dispatch(kinds=[_INBOUND_KIND])
            if row is not None:
                payload = row.get("payload") or {}
                try:
                    msg = _from_payload(payload if isinstance(payload, dict) else json.loads(payload))
                except Exception:
                    logger.exception("[Bus] could not reconstitute InboundMessage")
                    await ack_dispatch(row["dispatch_id"], state="failed")
                    continue
                # Mark done — channel dispatcher commits success implicitly
                # by consuming. (Phase 6.4 nack on dispatcher error.)
                await ack_dispatch(row["dispatch_id"], state="ok")
                return msg
            # No work; check in-memory once more in case race; else wait.
            if not self._inbound_queue.empty():
                return await self._inbound_queue.get()
            try:
                await asyncio.wait_for(self._inbound_queue.get(), timeout=poll_interval)
            except TimeoutError:
                continue


def maybe_install_postgres_bus_backend(existing: MessageBus | None = None) -> MessageBus:
    """Factory: return a PostgresInboundBus when the flag is set, else the
    plain in-memory MessageBus.

    Channel-service startup should call this when constructing its bus
    singleton.
    """
    if bus_backend_is_postgres():
        logger.info("[Bus] selecting PostgresInboundBus (durable inbound)")
        return PostgresInboundBus()
    logger.info("[Bus] selecting in-memory MessageBus (default)")
    return existing if existing is not None else MessageBus()


__all__ = [
    "PostgresInboundBus",
    "bus_backend_is_postgres",
    "maybe_install_postgres_bus_backend",
]
