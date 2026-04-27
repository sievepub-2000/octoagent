"""Gateway router for the Skill Evolution Engine (OpenSpace-inspired)."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from src.skill_evolution.quality_monitor import QualityMonitor
from src.skill_evolution.registry import SkillEvolutionRegistry
from src.skill_evolution.trust_score import is_enabled as _trust_enabled
from src.skill_evolution.trust_score import summarize_scores as _trust_summarize
from src.skill_evolution.types import EvolutionConfig, EvolutionRecord, QualityMetrics, SkillVersion
from src.skills.loader import get_skills_root_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/skill-evolution", tags=["skill-evolution"])

# Singleton registry — lazily initialized
_registry: SkillEvolutionRegistry | None = None
_config: EvolutionConfig = EvolutionConfig()


def _get_registry() -> SkillEvolutionRegistry:
    global _registry
    if _registry is None:
        data_dir = Path(get_skills_root_path()).parent / ".evolution"
        _registry = SkillEvolutionRegistry(data_dir)
    return _registry


# ── Response models ──────────────────────────────────────────────

class EvolutionConfigResponse(BaseModel):
    config: EvolutionConfig


class SkillVersionsResponse(BaseModel):
    skill_name: str
    versions: list[SkillVersion]


class EvolutionRecordsResponse(BaseModel):
    records: list[EvolutionRecord]


class QualityMetricsListResponse(BaseModel):
    metrics: list[QualityMetrics]


class HealthReportResponse(BaseModel):
    skill_name: str
    healthy: bool
    success_rate: float
    applied_rate: float
    total_executions: int
    recommendation: str = ""


class SkillListResponse(BaseModel):
    skills: list[str]


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/config", response_model=EvolutionConfigResponse)
async def get_evolution_config() -> EvolutionConfigResponse:
    """Get the current skill evolution configuration."""
    return EvolutionConfigResponse(config=_config)


@router.put("/config", response_model=EvolutionConfigResponse)
async def update_evolution_config(body: EvolutionConfig) -> EvolutionConfigResponse:
    """Update the skill evolution configuration."""
    global _config
    _config = body
    return EvolutionConfigResponse(config=_config)


@router.get("/skills", response_model=SkillListResponse)
async def list_evolved_skills() -> SkillListResponse:
    """List all skills tracked by the evolution engine."""
    reg = _get_registry()
    return SkillListResponse(skills=reg.list_all_skills())


@router.get("/skills/{skill_name}/versions", response_model=SkillVersionsResponse)
async def get_skill_versions(skill_name: str) -> SkillVersionsResponse:
    """Get the version history for a skill."""
    reg = _get_registry()
    versions = reg.list_versions(skill_name)
    return SkillVersionsResponse(skill_name=skill_name, versions=versions)


@router.post("/skills/{skill_name}/register", response_model=SkillVersionsResponse)
async def register_skill(skill_name: str) -> SkillVersionsResponse:
    """Register a skill in the evolution engine (creates v1 if new)."""
    reg = _get_registry()
    reg.register_skill(skill_name)
    versions = reg.list_versions(skill_name)
    return SkillVersionsResponse(skill_name=skill_name, versions=versions)


@router.get("/records", response_model=EvolutionRecordsResponse)
async def list_evolution_records(limit: int = 50) -> EvolutionRecordsResponse:
    """List recent evolution records."""
    reg = _get_registry()
    return EvolutionRecordsResponse(records=reg.list_records(limit=limit))


@router.get("/metrics", response_model=QualityMetricsListResponse)
async def list_quality_metrics() -> QualityMetricsListResponse:
    """Get quality metrics for all tracked skills."""
    reg = _get_registry()
    return QualityMetricsListResponse(metrics=reg.all_metrics())


@router.get("/metrics/{skill_name}", response_model=QualityMetrics)
async def get_skill_metrics(skill_name: str) -> QualityMetrics:
    """Get quality metrics for a specific skill."""
    reg = _get_registry()
    return reg.get_metrics(skill_name)


@router.get("/health", response_model=list[HealthReportResponse])
async def check_health() -> list[HealthReportResponse]:
    """Run health check across all tracked skills."""
    reg = _get_registry()
    monitor = QualityMonitor(reg)
    reports = monitor.check_all()
    return [
        HealthReportResponse(
            skill_name=r.skill_name,
            healthy=r.healthy,
            success_rate=r.success_rate,
            applied_rate=r.applied_rate,
            total_executions=r.total_executions,
            recommendation=r.recommendation,
        )
        for r in reports
    ]


@router.get("/health/unhealthy", response_model=list[HealthReportResponse])
async def check_unhealthy() -> list[HealthReportResponse]:
    """Return only unhealthy skills that may need evolution."""
    reg = _get_registry()
    monitor = QualityMonitor(reg)
    reports = monitor.unhealthy_skills()
    return [
        HealthReportResponse(
            skill_name=r.skill_name,
            healthy=r.healthy,
            success_rate=r.success_rate,
            applied_rate=r.applied_rate,
            total_executions=r.total_executions,
            recommendation=r.recommendation,
        )
        for r in reports
    ]


# -----------------------------------------------------------------------------
# Trust-score observation ledger (observation-only; no promotion/demotion)
# -----------------------------------------------------------------------------


class TrustScoreEntry(BaseModel):
    skill: str
    total: int
    successes: int
    success_rate: float
    p95_latency_ms: float | None
    trust_score: float


class TrustScoreSummaryResponse(BaseModel):
    enabled: bool
    window: int | None
    entries: list[TrustScoreEntry]


@router.get("/trust-scores", response_model=TrustScoreSummaryResponse)
async def get_trust_scores(window: int | None = None) -> TrustScoreSummaryResponse:
    """Return aggregated trust-score observations per skill.

    Observation-only: the ledger is append-only and no promotion logic runs
    here. When ``SKILL_TRUST_OBSERVATION_ENABLED`` is off the response will
    still succeed; it will simply reflect whatever (if anything) has been
    recorded historically and `enabled=false` so the WebUI can dim the panel.
    """

    summary = _trust_summarize(window=window)
    entries = [
        TrustScoreEntry(skill=skill, **data) for skill, data in sorted(summary.items())
    ]
    return TrustScoreSummaryResponse(
        enabled=_trust_enabled(),
        window=window,
        entries=entries,
    )
