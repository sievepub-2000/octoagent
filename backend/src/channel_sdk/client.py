"""Lightweight OctoAgent SDK client for WebSocket event streaming.

Usage:
    from channel_sdk.client import OctoAgentClient

    client = OctoAgentClient("ws://localhost:8000/ws/events")
    async for event in client.stream(subscriptions={"task.*"}):
        print(event)
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ChannelEventType(str, Enum):
    """Standard event types bridged from HookCore to the channel layer."""

    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    AGENT_STATUS_CHANGED = "agent.status_changed"
    AGENT_UPDATED = "agent.updated"
    AGENTS_TERMINATED = "agents.terminated"
    HANDOFF_CREATED = "handoff.created"
    WORKSPACE_CREATED = "workspace.created"
    WORKSPACE_UPDATED = "workspace.updated"
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    CAPABILITY_REFRESH = "capability.refresh"
    CHANNEL_MESSAGE = "channel.message"


# Map HookCore event constants to channel event types
HOOK_TO_CHANNEL: dict[str, ChannelEventType] = {
    "task.completed": ChannelEventType.TASK_COMPLETED,
    "task.failed": ChannelEventType.TASK_FAILED,
    "agent.status_changed": ChannelEventType.AGENT_STATUS_CHANGED,
    "agent.updated": ChannelEventType.AGENT_UPDATED,
    "agents.terminated": ChannelEventType.AGENTS_TERMINATED,
    "handoff.created": ChannelEventType.HANDOFF_CREATED,
    "workspace.created": ChannelEventType.WORKSPACE_CREATED,
    "workspace.updated": ChannelEventType.WORKSPACE_UPDATED,
    "execution.started": ChannelEventType.EXECUTION_STARTED,
    "execution.completed": ChannelEventType.EXECUTION_COMPLETED,
    "capability.refresh": ChannelEventType.CAPABILITY_REFRESH,
    "channel.message": ChannelEventType.CHANNEL_MESSAGE,
}


@dataclass
class SDKEvent:
    """Deserialized event from the WebSocket stream."""

    id: str
    type: str
    payload: dict[str, Any]
    timestamp: float
    source: str

    @classmethod
    def from_json(cls, raw: str) -> SDKEvent:
        data = json.loads(raw)
        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", 0.0),
            source=data.get("source", "unknown"),
        )


class OctoAgentClient:
    """Minimal async client for connecting to the OctoAgent event stream.

    This client is intentionally lightweight — it only depends on the
    standard library and an optional ``websockets`` package for actual
    WebSocket I/O. When ``websockets`` is not installed, the client
    provides a mock mode for testing.
    """

    def __init__(self, url: str, token: str | None = None) -> None:
        self.url = url
        self.token = token
        self._ws: Any = None

    async def connect(self, subscriptions: set[str] | None = None) -> None:
        """Establish WebSocket connection."""
        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "Install 'websockets' package to use the OctoAgent SDK client: pip install websockets"
            ) from exc

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        self._ws = await websockets.connect(self.url, additional_headers=headers)

        # Send subscription preferences
        if subscriptions:
            await self._ws.send(
                json.dumps({"action": "subscribe", "events": sorted(subscriptions)})
            )

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def stream(self, subscriptions: set[str] | None = None) -> AsyncIterator[SDKEvent]:
        """Connect and yield events as they arrive."""
        if not self._ws:
            await self.connect(subscriptions)

        try:
            async for raw in self._ws:
                try:
                    yield SDKEvent.from_json(raw)
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.warning("Failed to parse event: %s", exc)
        finally:
            await self.disconnect()

    async def __aenter__(self) -> OctoAgentClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.disconnect()


class WebSocketChannelManager:
    """Manages multiple WebSocket channels and routes HookCore events to them.

    Acts as a bridge between the internal HookCore dispatch system and
    external WebSocket consumers (frontends, SDK clients, webhooks).
    """

    def __init__(self) -> None:
        self._handlers: dict[ChannelEventType, list[Callable]] = {}
        self._active_connections: list[Any] = []

    def on(self, event_type: ChannelEventType, handler: Callable) -> None:
        """Register an event handler for a specific channel event type."""
        self._handlers.setdefault(event_type, []).append(handler)

    def off(self, event_type: ChannelEventType, handler: Callable) -> None:
        """Remove an event handler."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def dispatch(self, event_type: ChannelEventType, payload: dict[str, Any]) -> None:
        """Dispatch a channel event to all registered handlers."""
        for handler in self._handlers.get(event_type, []):
            try:
                handler(payload)
            except Exception:
                logger.warning("Channel handler failed for %s", event_type, exc_info=True)

    def bridge_hook_event(self, hook_event_name: str, payload: dict[str, Any]) -> None:
        """Bridge a HookCore event into the channel layer."""
        channel_type = HOOK_TO_CHANNEL.get(hook_event_name)
        if channel_type is not None:
            self.dispatch(channel_type, payload)

    def register_connection(self, ws: Any) -> None:
        """Track an active WebSocket connection."""
        self._active_connections.append(ws)

    def unregister_connection(self, ws: Any) -> None:
        """Remove a WebSocket connection from tracking."""
        if ws in self._active_connections:
            self._active_connections.remove(ws)

    @property
    def connection_count(self) -> int:
        """Number of active WebSocket connections."""
        return len(self._active_connections)

    async def broadcast(self, event_type: ChannelEventType, payload: dict[str, Any]) -> int:
        """Send an event to all active WebSocket connections.

        Returns the number of connections that received the message.
        """
        if not self._active_connections:
            return 0

        message = json.dumps({
            "type": event_type.value,
            "payload": payload,
        })
        sent = 0
        dead: list[Any] = []
        for ws in self._active_connections:
            try:
                send = getattr(ws, "send_text", None) or getattr(ws, "send", None)
                if send is not None:
                    result = send(message)
                    # Await if coroutine
                    if hasattr(result, "__await__"):
                        await result
                    sent += 1
            except Exception:
                logger.warning("Failed to send to WebSocket, removing connection", exc_info=True)
                dead.append(ws)
        for ws in dead:
            self._active_connections.remove(ws)
        return sent

    async def broadcast_hook_event(self, hook_event_name: str, payload: dict[str, Any]) -> int:
        """Bridge a HookCore event and broadcast to all active connections."""
        channel_type = HOOK_TO_CHANNEL.get(hook_event_name)
        if channel_type is not None:
            self.dispatch(channel_type, payload)
            return await self.broadcast(channel_type, payload)
        return 0


_channel_manager: WebSocketChannelManager | None = None


def get_channel_manager() -> WebSocketChannelManager:
    """Get the singleton WebSocketChannelManager instance."""
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = WebSocketChannelManager()
    return _channel_manager
