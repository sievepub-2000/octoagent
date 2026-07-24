"""Realtime workflow Work Bus endpoints."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src.harness.work_bus import get_work_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class WorkBusTraceResponse(BaseModel):
    thread_id: str
    events: list[dict] = Field(default_factory=list)
    count: int = 0


@router.get("/live/{thread_id}/events", response_model=WorkBusTraceResponse)
async def get_work_bus_events(thread_id: str) -> WorkBusTraceResponse:
    """Return the currently cached Work Bus events for a thread."""
    events = await get_work_bus().get_active_steps(thread_id)
    return WorkBusTraceResponse(thread_id=thread_id, events=events, count=len(events))


@router.websocket("/live/{thread_id}")
async def workflow_live_socket(websocket: WebSocket, thread_id: str) -> None:
    """Stream Work Bus events for a thread over WebSocket.

    The connection starts with a snapshot so the frontend can draw the current
    plan immediately, then receives one JSON event per subsequent update.
    """
    await websocket.accept()
    bus = get_work_bus()
    keepalive_task: asyncio.Task[None] | None = None
    try:
        snapshot = await bus.get_active_steps(thread_id)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "snapshot",
                    "thread_id": thread_id,
                    "events": snapshot,
                    "count": len(snapshot),
                },
                ensure_ascii=False,
                default=str,
            )
        )

        async def keepalive() -> None:
            while True:
                await asyncio.sleep(25)
                await websocket.send_text(
                    json.dumps(
                        {"type": "heartbeat", "thread_id": thread_id},
                        ensure_ascii=False,
                    )
                )

        keepalive_task = asyncio.create_task(
            keepalive(),
            name=f"work-bus-ws-heartbeat-{thread_id[:8]}",
        )
        async for event in bus.subscribe(thread_id):
            await websocket.send_text(
                json.dumps(
                    {"type": "event", "thread_id": thread_id, "event": event},
                    ensure_ascii=False,
                    default=str,
                )
            )
    except WebSocketDisconnect:
        logger.debug("WorkBus websocket disconnected for thread %s", thread_id)
    except Exception:
        logger.warning("WorkBus websocket failed for thread %s", thread_id, exc_info=True)
    finally:
        if keepalive_task is not None:
            keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keepalive_task
