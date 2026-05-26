"""OctoAgent Python SDK — external consumption package.

Provides typed clients for interacting with OctoAgent's HTTP and WebSocket APIs.
"""

from src.gateway.channel_sdk.client import ChannelEventType, OctoAgentClient, SDKEvent
from src.interfaces.python_sdk.async_client import OctoAgentAsyncClient
from src.interfaces.python_sdk.http_client import OctoAgentHTTPClient

__all__ = [
    "OctoAgentClient",
    "OctoAgentHTTPClient",
    "OctoAgentAsyncClient",
    "SDKEvent",
    "ChannelEventType",
]
__version__ = "0.2.0"
