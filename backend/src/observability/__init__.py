"""Observability package for octoagent.

Provides OpenTelemetry tracing, Prometheus metrics, and structured logging.
"""

from .tracer import get_tracer, initialize_tracer

__all__ = ["get_tracer", "initialize_tracer"]
