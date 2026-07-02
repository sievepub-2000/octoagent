"""OpenTelemetry tracing configuration for octoagent.

This module initializes the OpenTelemetry TracerProvider and sets up
automatic instrumentation for FastAPI requests and LangGraph calls.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_tracer: Optional[Any] = None


def initialize_tracer(service_name: str = "octoagent") -> None:
    """Initialize the OpenTelemetry TracerProvider.

    Args:
        service_name: The name of the service for trace context.
    """
    global _tracer
    
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        
        # Configure resource
        resource = Resource.create({
            "service.name": service_name,
            "service.version": "2026.7.1",
        })
        
        # Create tracer provider
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)
        
        _tracer = trace.get_tracer(__name__)
        logger.info("OpenTelemetry tracer initialized for %s", service_name)
        
    except ImportError:
        logger.warning(
            "OpenTelemetry packages not installed, tracing disabled. "
            "Install with: pip install opentelemetry-api opentelemetry-sdk"
        )
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to initialize OpenTelemetry tracer: %s", str(e))


def get_tracer() -> Optional[Any]:
    """Get the current OpenTelemetry tracer.

    Returns:
        The tracer instance, or None if not initialized.
    """
    return _tracer


def create_span(name: str, **kwargs: Any):
    """Create a new span for distributed tracing.

    Args:
        name: The span name.
        **kwargs: Additional span attributes.

    Yields:
        The span object, or None if tracer not available.
    """
    if _tracer is None:
        yield None
        return
    
    try:
        with _tracer.start_as_current_span(name) as span:
            for key, value in kwargs.items():
                span.set_attribute(key, str(value))
            yield span
    except Exception:
        yield None


def add_span_attributes(span: Any, **kwargs: Any) -> None:
    """Add attributes to an existing span.

    Args:
        span: The span to add attributes to.
        **kwargs: Key-value pairs to set as span attributes.
    """
    if span is not None:
        for key, value in kwargs.items():
            try:
                span.set_attribute(key, str(value))
            except Exception:
                pass