"""Common exception classes and handlers for octoagent.

This module provides standardized exception types and handling utilities
to reduce code duplication across the codebase.
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class OctoAgentError(Exception):
    """Base exception for all octoagent errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(OctoAgentError):
    """Raised when there is a configuration issue."""

    pass


class ValidationError(OctoAgentError):
    """Raised when validation fails."""

    pass


class ExecutionError(OctoAgentError):
    """Raised when an execution step fails."""

    pass


class ResourceExhaustedError(OctoAgentError):
    """Raised when resources are exhausted (e.g., worker limit)."""

    pass


def safe_execute[T](
    func: Callable[..., T],
    *args: Any,
    default: T | None = None,
    log_errors: bool = True,
    **kwargs: Any,
) -> T | None:
    """Execute a function safely with error handling.

    Args:
        func: The function to execute.
        *args: Positional arguments for the function.
        default: Default value to return on error.
        log_errors: Whether to log errors (default True).
        **kwargs: Keyword arguments for the function.

    Returns:
        The function result, or default if an exception occurs.
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 - Intentional broad catch for safe_execute
        if log_errors:
            logger.error("Error in %s: %s", func.__name__, str(e), exc_info=True)
        return default


def retry_with_backoff(  # noqa: UP047 - shared TypeVar keeps Python 3.11 compatibility
    func: Callable[..., T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    *args: Any,
    **kwargs: Any,
) -> T | None:
    """Execute a function with retry logic and exponential backoff.

    Args:
        func: The function to execute.
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds for backoff calculation.
        *args: Positional arguments for the function.
        **kwargs: Keyword arguments for the function.

    Returns:
        The function result on success, or None if all retries fail.
    """
    import time

    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - Intentional broad catch for retry
            last_exception = e
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "Attempt %d/%d failed for %s, retrying in %.1fs: %s",
                    attempt + 1,
                    max_retries + 1,
                    func.__name__,
                    delay,
                    str(e),
                )
                time.sleep(delay)

    logger.error(
        "All %d retries failed for %s: %s",
        max_retries + 1,
        func.__name__,
        str(last_exception),
    )
    return None
