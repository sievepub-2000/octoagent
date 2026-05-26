"""WebSocket channel for real-time event streaming.

Provides bidirectional communication between clients and the OctoAgent
runtime through WebSocket connections, enabling live event streaming
for task execution, agent status, and system notifications.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


class ChannelEventType(StrEnum):
    """Event types that flow through the WebSocket channel."""

    # Runtime events
    RUNTIME_STATE = "runtime.state"
    RUNTIME_HEARTBEAT = "runtime.heartbeat"

    # Task events
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"

    # Agent events
    AGENT_MESSAGE = "agent.message"
    AGENT_STATUS_CHANGED = "agent.status_changed"
    AGENT_UPDATED = "agent.updated"
    AGENTS_TERMINATED = "agents.terminated"
    HANDOFF_CREATED = "handoff.created"
    AGENT_TOOL_CALL = "agent.tool_call"
    AGENT_THINKING = "agent.thinking"
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    CAPABILITY_REFRESH = "capability.refresh"
    CHANNEL_MESSAGE = "channel.message"

    # System events
    SYSTEM_ERROR = "system.error"
    SYSTEM_NOTIFICATION = "system.notification"
    WORKSPACE_CREATED = "workspace.created"
    WORKSPACE_UPDATED = "workspace.updated"


@dataclass
class ChannelEvent:
    """A single event emitted through the channel."""

    event_type: ChannelEventType
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    source: str = "system"

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.event_id,
                "type": self.event_type.value,
                "payload": self.payload,
                "timestamp": self.timestamp,
                "source": self.source,
            }
        )


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------


@dataclass
class WebSocketConnection:
    """Represents a single WebSocket client connection."""

    connection_id: str
    subscriptions: set[str] = field(default_factory=set)
    connected_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class WebSocketChannelManager:
    """Manages WebSocket connections and event broadcasting.

    This manager handles:
    - Connection registration/deregistration
    - Event subscription filtering
    - Broadcasting events to subscribed connections
    - Connection health monitoring
    """

    def __init__(self) -> None:
        self._connections: dict[str, WebSocketConnection] = {}
        self._queues: dict[str, asyncio.Queue[ChannelEvent]] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        connection_id: str | None = None,
        subscriptions: set[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WebSocketConnection:
        """Register a new WebSocket connection."""
        conn_id = connection_id or uuid.uuid4().hex[:16]
        conn = WebSocketConnection(
            connection_id=conn_id,
            subscriptions=subscriptions or {"*"},
            metadata=metadata or {},
        )
        async with self._lock:
            self._connections[conn_id] = conn
            self._queues[conn_id] = asyncio.Queue(maxsize=256)
        logger.info("WebSocket connection registered: %s", conn_id)
        return conn

    async def unregister(self, connection_id: str) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            self._connections.pop(connection_id, None)
            self._queues.pop(connection_id, None)
        logger.info("WebSocket connection unregistered: %s", connection_id)

    async def broadcast(self, event: ChannelEvent) -> int:
        """Broadcast an event to all subscribed connections.

        Returns the number of connections that received the event.
        """
        delivered = 0
        async with self._lock:
            for conn_id, conn in self._connections.items():
                if self._matches_subscription(event, conn.subscriptions):
                    queue = self._queues.get(conn_id)
                    if queue and not queue.full():
                        await queue.put(event)
                        delivered += 1
        return delivered

    async def receive(self, connection_id: str, timeout: float = 30.0) -> ChannelEvent | None:
        """Receive the next event for a connection (blocking with timeout)."""
        queue = self._queues.get(connection_id)
        if not queue:
            return None
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except TimeoutError:
            return None

    def get_connection(self, connection_id: str) -> WebSocketConnection | None:
        return self._connections.get(connection_id)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def runtime_state(self) -> dict[str, Any]:
        """Return manager state for diagnostics."""
        return {
            "active_connections": self.connection_count,
            "connections": [
                {
                    "id": c.connection_id,
                    "subscriptions": sorted(c.subscriptions),
                    "connected_at": c.connected_at,
                }
                for c in self._connections.values()
            ],
        }

    @staticmethod
    def _matches_subscription(event: ChannelEvent, subscriptions: set[str]) -> bool:
        """Check if an event matches any subscription filter."""
        if "*" in subscriptions:
            return True
        event_type = event.event_type.value
        for sub in subscriptions:
            if event_type == sub:
                return True
            # Prefix matching: "task.*" matches "task.started"
            if sub.endswith(".*") and event_type.startswith(sub[:-1]):
                return True
        return False
