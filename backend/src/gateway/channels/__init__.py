"""IM Channel integration for OctoAgent.

Provides a pluggable channel system that connects external messaging platforms
(Slack and Telegram) to the OctoAgent agent via the ChannelManager,
which uses ``langgraph-sdk`` to communicate with the underlying LangGraph Server.
"""

from src.gateway.channels.base import Channel
from src.gateway.channels.message_bus import InboundMessage, MessageBus, OutboundMessage

__all__ = [
    "Channel",
    "InboundMessage",
    "MessageBus",
    "OutboundMessage",
]
