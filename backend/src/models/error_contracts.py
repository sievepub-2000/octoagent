"""Normalized model-provider error contracts."""

from __future__ import annotations

from typing import Any


class NormalizedModelError(RuntimeError):
    """Provider-neutral model invocation error."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        status_code: int | None = None,
        model_name: str | None = None,
        provider_name: str | None = None,
        interface_type: str | None = None,
        adapter_type: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code
        self.model_name = model_name
        self.provider_name = provider_name
        self.interface_type = interface_type
        self.adapter_type = adapter_type
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "status_code": self.status_code,
            "model_name": self.model_name,
            "provider_name": self.provider_name,
            "interface_type": self.interface_type,
            "adapter_type": self.adapter_type,
            "details": dict(self.details),
        }


def _normalize_message(exc: Exception) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


def _detect_status_code(message: str) -> int | None:
    lowered = message.lower()
    if "429" in lowered or "rate limit" in lowered or "rate-limit" in lowered or "rate-limited" in lowered:
        return 429
    if "401" in lowered or "unauthorized" in lowered or "authentication" in lowered:
        return 401
    if "403" in lowered or "forbidden" in lowered:
        return 403
    if "408" in lowered or "timed out" in lowered or "timeout" in lowered:
        return 408
    if "503" in lowered or "service unavailable" in lowered or "overloaded" in lowered:
        return 503
    if "context length" in lowered or "maximum context" in lowered or "too many tokens" in lowered:
        return 400
    return None


def normalize_model_exception(
    exc: Exception,
    *,
    model_name: str,
    provider_name: str | None,
    interface_type: str,
    adapter_type: str,
) -> NormalizedModelError:
    """Translate provider-specific failures into a stable model error."""

    if isinstance(exc, NormalizedModelError):
        return exc

    message = _normalize_message(exc)
    lowered = message.lower()
    status_code = _detect_status_code(message)
    code = "provider_error"
    retryable = False

    if "context length" in lowered or "maximum context" in lowered or "too many tokens" in lowered:
        code = "context_length_exceeded"
        retryable = False
    elif "429" in lowered or "rate limit" in lowered or "rate-limit" in lowered or "rate-limited" in lowered:
        code = "rate_limit_exceeded"
        retryable = True
    elif any(marker in lowered for marker in ("401", "403", "unauthorized", "forbidden", "authentication", "api key")):
        code = "authentication_failed"
        retryable = False
    elif any(marker in lowered for marker in ("timeout", "timed out", "connection", "network", "temporarily unavailable", "service unavailable", "503", "502", "504", "overloaded", "refused")):
        code = "upstream_unavailable"
        retryable = True

    return NormalizedModelError(
        code=code,
        message=message,
        retryable=retryable,
        status_code=status_code,
        model_name=model_name,
        provider_name=provider_name,
        interface_type=interface_type,
        adapter_type=adapter_type,
        details={"source_exception": exc.__class__.__name__},
    )