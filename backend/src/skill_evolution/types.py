"""Data types for the skill evolution engine."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


class EvolutionMode(str, enum.Enum):
    """How a skill evolved."""

    FIX = "fix"
    DERIVED = "derived"
    CAPTURED = "captured"


class QualityMetrics(BaseModel):
    """Quality tracking for a single skill."""

    skill_name: str
    applied_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    fallback_count: int = 0
    avg_latency_ms: float = 0.0
    last_used: datetime | None = None

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    @property
    def applied_rate(self) -> float:
        total = self.applied_count + self.fallback_count
        return self.applied_count / total if total > 0 else 0.0


class SkillVersion(BaseModel):
    """A tracked version in the evolution DAG."""

    skill_name: str
    version: int = 1
    parent_name: str | None = None
    parent_version: int | None = None
    mode: EvolutionMode | None = None
    diff_summary: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    quality: QualityMetrics | None = None


class EvolutionRecord(BaseModel):
    """One evolution event."""

    id: str
    skill_name: str
    from_version: int
    to_version: int
    mode: EvolutionMode
    reason: str = ""
    diff_summary: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvolutionConfig(BaseModel):
    """User-facing configuration for the evolution engine."""

    enabled: bool = True
    auto_fix: bool = True
    auto_derive: bool = True
    auto_capture: bool = True
    quality_monitoring: bool = True
    evolve_interval: int = Field(default=5, description="Trigger evolution every N task executions")
    cloud_enabled: bool = False
    cloud_api_key: str = ""
    cloud_api_base: str = "https://open-space.cloud/api/v1"
