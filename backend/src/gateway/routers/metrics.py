"""Prometheus-compatible /metrics endpoint plus JSON and write endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Path
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from src.gateway.monitoring import get_metrics_registry
from src.gateway.security import require_operator_or_403
from src.governance.operator import signed_audit_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["monitoring"])


# ── Models ─────────────────────────────────────────────────────────────────────


class MetricSnapshot(BaseModel):
    name: str
    value: float
    labels: dict[str, str] = Field(default_factory=dict)
    kind: str = "counter"


class MetricsJsonResponse(BaseModel):
    metrics: list[MetricSnapshot] = Field(default_factory=list)
    count: int = 0


class IncrementRequest(BaseModel):
    amount: float = 1.0
    labels: dict[str, str] = Field(default_factory=dict)


class IncrementResponse(BaseModel):
    metric_name: str
    new_value: float


class MetricsGovernanceResponse(BaseModel):
    metric_count: int = 0
    counter_count: int = 0
    gauge_count: int = 0
    histogram_count: int = 0
    default_metrics_present: list[str] = Field(default_factory=list)
    audit: dict[str, object] = Field(default_factory=dict)


# ── Read endpoints ─────────────────────────────────────────────────────────────


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics() -> str:
    """Expose Prometheus-compatible metrics in text exposition format."""
    registry = get_metrics_registry()
    return registry.render()


@router.get("/api/metrics/json", response_model=MetricsJsonResponse)
async def metrics_json() -> MetricsJsonResponse:
    """Return all metrics as structured JSON for dashboard consumption."""
    registry = get_metrics_registry()
    snapshots: list[MetricSnapshot] = []
    try:
        for entry in registry.snapshot():
            snapshots.append(
                MetricSnapshot(
                    name=entry.get("name", ""),
                    value=float(entry.get("value", 0)),
                    labels=entry.get("labels", {}),
                    kind=entry.get("kind", "counter"),
                )
            )
    except Exception:
        # Registry may not expose snapshot(); fall back gracefully
        pass
    return MetricsJsonResponse(metrics=snapshots, count=len(snapshots))


@router.get("/api/metrics/governance", response_model=MetricsGovernanceResponse)
async def metrics_governance() -> MetricsGovernanceResponse:
    """Return operator-facing monitoring registry coverage and signed audit metadata."""
    registry = get_metrics_registry()
    snapshots = registry.snapshot()
    names = {str(item.get("name") or "") for item in snapshots}
    default_names = [
        "octoagent_requests_total",
        "octoagent_task_completed_total",
        "octoagent_task_failed_total",
        "octoagent_active_workspaces",
        "octoagent_active_agents",
        "octoagent_skill_evolutions_total",
        "octoagent_reflection_observations_total",
    ]
    return MetricsGovernanceResponse(
        metric_count=len(snapshots),
        counter_count=sum(1 for item in snapshots if item.get("kind") == "counter"),
        gauge_count=sum(1 for item in snapshots if item.get("kind") == "gauge"),
        histogram_count=len(getattr(registry, "_histograms", {})),  # noqa: SLF001
        default_metrics_present=[name for name in default_names if name in names],
        audit=signed_audit_event("monitoring.governance_snapshot", metric_count=len(snapshots)),
    )


# ── Write endpoints ────────────────────────────────────────────────────────────


@router.post("/api/metrics/increment/{metric_name}", response_model=IncrementResponse)
async def increment_metric(
    metric_name: str = Path(description="Dot-separated metric name, e.g. tasks.completed"),
    request: IncrementRequest = None,  # type: ignore[assignment]
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> IncrementResponse:
    """Increment a named counter metric by *amount* (default 1).

    Creates the metric if it does not already exist. Useful for
    instrumenting external processes that cannot use the Python client directly.
    """
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    if request is None:
        request = IncrementRequest()

    registry = get_metrics_registry()
    try:
        new_value = registry.increment(metric_name, amount=request.amount, labels=request.labels)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return IncrementResponse(metric_name=metric_name, new_value=new_value)


# ── Memory / performance health endpoints ──────────────────────────────────────


class MemoryHealthResponse(BaseModel):
    store_stats: dict = Field(default_factory=dict)
    cleanup_scheduler: dict = Field(default_factory=dict)
    queue_stats: dict = Field(default_factory=dict)
    degradation: dict = Field(default_factory=dict)


@router.get("/api/metrics/memory-health", response_model=MemoryHealthResponse)
async def memory_health() -> MemoryHealthResponse:
    """Return the Harness-owned Markdown/pgvector memory health."""
    try:
        from src.harness.memory import get_harness_memory

        store_data = get_harness_memory().stats()
    except Exception as exc:
        store_data = {"error": str(exc)}

    # Degradation level
    degradation_data: dict = {}
    try:
        from src.agents.degradation import get_degradation_controller

        ctrl = get_degradation_controller()
        degradation_data = {
            "level": ctrl.get_level(),
            "psutil_available": ctrl._psutil_available,  # noqa: SLF001
        }
    except Exception as exc:
        degradation_data = {"error": str(exc)}

    return MemoryHealthResponse(
        store_stats=store_data,
        cleanup_scheduler={"owner": "harness", "running": False},
        queue_stats={"pending_index": store_data.get("pending", 0)},
        degradation=degradation_data,
    )


@router.delete("/api/metrics/{metric_name}", status_code=204)
async def reset_metric(
    metric_name: str = Path(description="Dot-separated metric name to reset to 0"),
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> None:
    """Reset a counter metric back to zero."""
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    registry = get_metrics_registry()
    try:
        registry.reset(metric_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Metric '{metric_name}' not found")
