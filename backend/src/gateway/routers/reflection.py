"""Reflection service gateway router — observations, insights, and execution summary.

Exposes the ReflectionService over HTTP for frontend dashboards and
operator tooling.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Header, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from src.gateway.security import require_operator_or_403
from src.harness.reflection import get_reflection_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reflection", tags=["reflection"])

# ── Models ─────────────────────────────────────────────────────────────────────

ObservationCategory = Literal["outcome", "performance", "error", "tool_usage", "model_quality"]
ObservationSeverity = Literal["info", "warning", "critical"]
InsightCategory = Literal["skill_gap", "model_mismatch", "tool_failure", "prompt_quality", "efficiency"]
ReflectionExportDataset = Literal["observations", "insights"]
ReflectionExportFormat = Literal["jsonl", "csv"]


class ObservationResponse(BaseModel):
    observation_id: str
    task_id: str
    timestamp: float
    category: ObservationCategory
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    severity: ObservationSeverity


class ObservationsListResponse(BaseModel):
    observations: list[ObservationResponse] = Field(default_factory=list)
    total: int = 0


class InsightResponse(BaseModel):
    insight_id: str
    source_observations: list[str] = Field(default_factory=list)
    category: InsightCategory
    description: str
    suggested_action: str
    confidence: float


class InsightsListResponse(BaseModel):
    insights: list[InsightResponse] = Field(default_factory=list)
    total: int = 0


class ExecutionSummaryResponse(BaseModel):
    window_size: int
    outcomes: dict[str, int]
    error_count: int
    success_rate: float
    insight_count: int


class RecordObservationRequest(BaseModel):
    task_id: str
    category: ObservationCategory = "outcome"
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    severity: ObservationSeverity = "info"


def _attachment_headers(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("/observations", response_model=ObservationsListResponse)
async def list_observations(
    task_id: str | None = Query(default=None),
    category: ObservationCategory | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> ObservationsListResponse:
    """List recent execution observations with optional filters."""
    svc = get_reflection_service()
    obs = svc.get_observations(task_id=task_id, category=category, limit=limit)
    return ObservationsListResponse(
        observations=[
            ObservationResponse(
                observation_id=o.observation_id,
                task_id=o.task_id,
                timestamp=o.timestamp,
                category=o.category,
                summary=o.summary,
                details=o.details,
                severity=o.severity,
            )
            for o in obs
        ],
        total=len(obs),
    )


@router.post("/observations", response_model=ObservationResponse, status_code=201)
async def record_observation(
    request: RecordObservationRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> ObservationResponse:
    """Record a new execution observation."""
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    from src.harness.reflection.service import ExecutionObservation

    obs = ExecutionObservation(
        observation_id=uuid.uuid4().hex[:16],
        task_id=request.task_id,
        timestamp=time.time(),
        category=request.category,
        summary=request.summary,
        details=request.details,
        severity=request.severity,
    )
    get_reflection_service().record_observation(obs)
    return ObservationResponse(
        observation_id=obs.observation_id,
        task_id=obs.task_id,
        timestamp=obs.timestamp,
        category=obs.category,
        summary=obs.summary,
        details=obs.details,
        severity=obs.severity,
    )


@router.get("/insights", response_model=InsightsListResponse)
async def list_insights() -> InsightsListResponse:
    """Return the most recently derived reflection insights (cached)."""
    svc = get_reflection_service()
    insights = svc.get_insights()
    return InsightsListResponse(
        insights=[
            InsightResponse(
                insight_id=i.insight_id,
                source_observations=i.source_observations,
                category=i.category,
                description=i.description,
                suggested_action=i.suggested_action,
                confidence=i.confidence,
            )
            for i in insights
        ],
        total=len(insights),
    )


@router.post("/insights/derive", response_model=InsightsListResponse)
async def derive_insights(
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> InsightsListResponse:
    """Trigger a fresh insight derivation pass over recent observations."""
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    svc = get_reflection_service()
    insights = svc.derive_insights()
    return InsightsListResponse(
        insights=[
            InsightResponse(
                insight_id=i.insight_id,
                source_observations=i.source_observations,
                category=i.category,
                description=i.description,
                suggested_action=i.suggested_action,
                confidence=i.confidence,
            )
            for i in insights
        ],
        total=len(insights),
    )


@router.get("/summary", response_model=ExecutionSummaryResponse)
async def execution_summary(
    window: int = Query(default=20, ge=5, le=200),
) -> ExecutionSummaryResponse:
    """Return a compact execution quality summary for Brain integration."""
    svc = get_reflection_service()
    summary = svc.execution_summary(window=window)
    return ExecutionSummaryResponse(
        window_size=summary["window_size"],
        outcomes=summary["outcomes"],
        error_count=summary["error_count"],
        success_rate=summary["success_rate"],
        insight_count=summary["insight_count"],
    )


@router.get("/export", response_class=PlainTextResponse)
async def export_reflection_dataset(
    dataset: ReflectionExportDataset = Query(default="observations"),
    format: ReflectionExportFormat = Query(default="jsonl"),
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> PlainTextResponse:
    """Export reflection observations or insights for audit / operator review."""
    require_operator_or_403(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    svc = get_reflection_service()
    if dataset == "insights":
        content = svc.export_insights(format=format)
    else:
        content = svc.export_observations(format=format)

    media_type = "text/csv" if format == "csv" else "application/x-ndjson"
    filename = f"reflection-{dataset}-{int(time.time())}.{format}"
    return PlainTextResponse(content=content, media_type=media_type, headers=_attachment_headers(filename))
