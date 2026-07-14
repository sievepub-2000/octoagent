"""Tests for common exceptions module - edge cases and error handling."""

from src.common.exceptions import (
    ConfigurationError,
    ExecutionError,
    OctoAgentError,
    ResourceExhaustedError,
    ValidationError,
    retry_with_backoff,
    safe_execute,
)


class TestOctoAgentError:
    """Test base exception class."""

    def test_basic_error(self) -> None:
        err = OctoAgentError("test error")
        assert str(err) == "test error"
        assert err.message == "test error"
        assert err.details == {}

    def test_error_with_details(self) -> None:
        details = {"key": "value"}
        err = OctoAgentError("test", details=details)
        assert err.details == details

    def test_is_exception(self) -> None:
        assert issubclass(OctoAgentError, Exception)


class TestSubclassErrors:
    """Test exception subclasses."""

    def test_configuration_error(self) -> None:
        err = ConfigurationError("config issue")
        assert isinstance(err, OctoAgentError)

    def test_validation_error(self) -> None:
        err = ValidationError("validation failed")
        assert isinstance(err, OctoAgentError)

    def test_execution_error(self) -> None:
        err = ExecutionError("execution failed")
        assert isinstance(err, OctoAgentError)

    def test_resource_exhausted_error(self) -> None:
        err = ResourceExhaustedError("out of resources")
        assert isinstance(err, OctoAgentError)


class TestSafeExecute:
    """Test safe_execute utility."""

    def test_successful_execution(self) -> None:
        result = safe_execute(lambda x: x * 2, 5)
        assert result == 10

    def test_exception_returns_default(self) -> None:
        def failing_func() -> int:
            raise ValueError("fail")

        result = safe_execute(failing_func, default=42)
        assert result == 42

    def test_exception_no_default(self) -> None:
        def failing_func() -> int:
            raise ValueError("fail")

        result = safe_execute(failing_func, log_errors=False)
        assert result is None

    def test_exception_logged_by_default(self) -> None:
        """Test that errors are logged by default (no assertion, just verify no crash)."""

        def failing_func() -> int:
            raise ValueError("fail")

        # Should not raise
        result = safe_execute(failing_func)
        assert result is None


class TestRetryWithBackoff:
    """Test retry_with_backoff utility."""

    def test_success_on_first_try(self) -> None:
        call_count = 0

        def succeeds() -> int:
            nonlocal call_count
            call_count += 1
            return 42

        result = retry_with_backoff(succeeds, max_retries=3, base_delay=0.01)
        assert result == 42
        assert call_count == 1

    def test_success_after_retry(self) -> None:
        call_count = 0

        def fails_twice() -> int:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary failure")
            return "success"

        result = retry_with_backoff(fails_twice, max_retries=5, base_delay=0.01)
        assert result == "success"
        assert call_count == 3

    def test_all_retries_fail(self) -> None:
        call_count = 0

        def always_fails() -> int:
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent failure")

        result = retry_with_backoff(always_fails, max_retries=2, base_delay=0.01)
        assert result is None
        assert call_count == 3  # initial + 2 retries

    def test_custom_base_delay(self) -> None:
        """Test that backoff delay is calculated correctly (just verify no crash)."""
        call_count = 0

        def fails() -> int:
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        # Should not crash, just verify it runs
        result = retry_with_backoff(fails, max_retries=1, base_delay=0.01)
        assert result is None
