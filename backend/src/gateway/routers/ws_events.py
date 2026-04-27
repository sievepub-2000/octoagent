"""WebSocket endpoint for real-time event streaming."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.channel_sdk import ChannelEvent, ChannelEventType, WebSocketChannelManager

logger = logging.getLogger(__name__)

router = APIRouter()

# Singleton manager — shared across the gateway process.
_manager: WebSocketChannelManager | None = None


def get_ws_channel_manager() -> WebSocketChannelManager:
    """Return the global WebSocketChannelManager instance."""
    global _manager
    if _manager is None:
        _manager = WebSocketChannelManager()
    return _manager


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    """Accept a WebSocket connection and stream real-time events.

    Protocol:
    1. Client connects to ``/ws/events``.
    2. Server accepts and registers the connection.
    3. Client *may* send a JSON subscribe message::

           {"action": "subscribe", "events": ["task.*", "agent.message"]}

       If no subscribe message arrives within 5 s the connection defaults
       to ``*`` (all events).
    4. Server pushes ``ChannelEvent`` JSON objects as they arrive.
    5. A ``runtime.heartbeat`` event is sent whenever the receive timeout
       expires so the connection stays alive.
    """
    await websocket.accept()

    manager = get_ws_channel_manager()
    conn = await manager.register()
    conn_id = conn.connection_id
    logger.info("WS client connected: %s", conn_id)

    try:
        # ------ Subscription handshake (best-effort, non-blocking) ------
        try:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            if isinstance(msg, dict) and msg.get("action") == "subscribe":
                events = msg.get("events")
                if isinstance(events, list) and events:
                    conn.subscriptions = set(events)
                    logger.info("WS %s subscribed to %s", conn_id, conn.subscriptions)
        except (WebSocketDisconnect, json.JSONDecodeError):
            pass  # Use default wildcard subscription

        # ------ Event loop ------
        while True:
            event = await manager.receive(conn_id, timeout=25.0)
            if event is None:
                # Send heartbeat to keep the connection alive
                heartbeat = ChannelEvent(
                    event_type=ChannelEventType.RUNTIME_HEARTBEAT,
                    payload={"connections": manager.connection_count},
                )
                await websocket.send_text(heartbeat.to_json())
            else:
                await websocket.send_text(event.to_json())

    except WebSocketDisconnect:
        logger.info("WS client disconnected: %s", conn_id)
    except Exception:
        logger.exception("WS error for connection %s", conn_id)
    finally:
        await manager.unregister(conn_id)
