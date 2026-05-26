"""Scrapling community wrapper.

Provides scrapling_fetch (HTTP) and scrapling_fetch_stealth (browser-based,
graceful degradation) for OctoAgent's tiered web-fetch strategy.
"""

from .tools import scrapling_fetch, scrapling_fetch_stealth

__all__ = ["scrapling_fetch", "scrapling_fetch_stealth"]
