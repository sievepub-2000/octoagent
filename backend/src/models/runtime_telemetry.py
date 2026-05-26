"""Per-invocation runtime telemetry for model fallback execution."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class ModelRuntimeTelemetry:
    primary_model: str | None = None
    active_model: str | None = None
    fallback_switches: list[dict[str, str]] = field(default_factory=list)
    final_error: str | None = None


_telemetry_var: ContextVar[ModelRuntimeTelemetry | None] = ContextVar(
    "model_runtime_telemetry",
    default=None,
)


def begin_model_runtime_telemetry(primary_model: str | None) -> None:
    _telemetry_var.set(ModelRuntimeTelemetry(primary_model=primary_model))


def get_model_runtime_telemetry() -> ModelRuntimeTelemetry | None:
    return _telemetry_var.get()


def clear_model_runtime_telemetry() -> None:
    _telemetry_var.set(None)


def set_active_model(model_name: str) -> None:
    telemetry = _telemetry_var.get()
    if telemetry is None:
        return
    telemetry.active_model = model_name


def record_fallback_switch(from_model: str, to_model: str, reason: str) -> None:
    telemetry = _telemetry_var.get()
    if telemetry is None:
        return
    telemetry.fallback_switches.append(
        {
            "from_model": from_model,
            "to_model": to_model,
            "reason": reason,
        }
    )


def record_final_error(message: str) -> None:
    telemetry = _telemetry_var.get()
    if telemetry is None:
        return
    telemetry.final_error = message
