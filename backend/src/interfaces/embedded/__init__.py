"""Embedded in-process client (formerly ``src.client``, ``src.interfaces.embedded.agent``, ``src.interfaces.embedded.streaming``)."""

from src.interfaces.embedded.agent import ClientAgentBuilder
from src.interfaces.embedded.streaming import ClientStreamSerializer

__all__ = ["ClientAgentBuilder", "ClientStreamSerializer"]
