"""Tests for OpenTelemetry tracer - initialization and span creation."""

import pytest
from src.observability.tracer import (
    get_tracer,
    initialize_tracer,
)


class TestTracerInitialization:
    """Test tracer initialization."""

    def setup_method(self) -> None:
        """Reset tracer state before each test."""
        import src.observability.tracer as tracer_module
        tracer_module._tracer = None

    def test_initialize_tracer(self) -> None:
        """Test that tracer initializes without error."""
        # Should not raise even if OTel packages are missing
        initialize_tracer("test-service")

    def test_get_tracer_after_init(self) -> None:
        """Test getting tracer after initialization."""
        initialize_tracer("test-service")
        tracer = get_tracer()
        
        # Tracer may be None if OTel not installed, but should not crash
        assert tracer is None or hasattr(tracer, "start_as_current_span")

    def test_initialize_multiple_times(self) -> None:
        """Test that multiple initializations don't cause issues."""
        initialize_tracer("service-1")
        initialize_tracer("service-2")  # Should not crash


class TestTracerFunctionality:
    """Test tracer functionality (graceful degradation)."""

    def setup_method(self) -> None:
        """Reset tracer state before each test."""
        import src.observability.tracer as tracer_module
        tracer_module._tracer = None

    def test_create_span_without_init(self) -> None:
        """Test create_span when tracer is not initialized."""
        from src.observability.tracer import create_span
        
        # create_span is a generator, use next() to get the yielded value
        gen = create_span("test-span")
        span = next(gen)
        
        # Should yield None when tracer is not available
        assert span is None

    def test_add_span_attributes_none(self) -> None:
        """Test add_span_attributes with None span."""
        from src.observability.tracer import add_span_attributes
        
        # Should not crash
        add_span_attributes(None, key="value")