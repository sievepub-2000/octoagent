"""Quality monitor — tracks skill health and triggers evolution when degraded.

Inspired by OpenSpace's multi-layer quality monitoring that covers skills,
tool calls, and code execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.skill_evolution.registry import SkillEvolutionRegistry
from src.skill_evolution.types import QualityMetrics

logger = logging.getLogger(__name__)


@dataclass
class HealthReport:
    """Snapshot of a skill's health status."""

    skill_name: str
    healthy: bool
    success_rate: float
    applied_rate: float
    total_executions: int
    recommendation: str = ""


class QualityMonitor:
    """Periodically checks skill metrics and flags underperformers."""

    def __init__(
        self,
        registry: SkillEvolutionRegistry,
        *,
        min_executions: int = 3,
        success_threshold: float = 0.5,
        applied_threshold: float = 0.3,
    ) -> None:
        self._registry = registry
        self._min_executions = min_executions
        self._success_threshold = success_threshold
        self._applied_threshold = applied_threshold

    def check_all(self) -> list[HealthReport]:
        """Return health reports for every tracked skill."""
        reports: list[HealthReport] = []
        for m in self._registry.all_metrics():
            reports.append(self._evaluate(m))
        return reports

    def check_skill(self, name: str) -> HealthReport:
        m = self._registry.get_metrics(name)
        return self._evaluate(m)

    def unhealthy_skills(self) -> list[HealthReport]:
        """Return only skills that are flagged as unhealthy."""
        return [r for r in self.check_all() if not r.healthy]

    # ---------------------------------------------------------------

    def _evaluate(self, m: QualityMetrics) -> HealthReport:
        total = m.success_count + m.failure_count
        if total < self._min_executions:
            return HealthReport(
                skill_name=m.skill_name,
                healthy=True,
                success_rate=m.success_rate,
                applied_rate=m.applied_rate,
                total_executions=total,
                recommendation="Insufficient data",
            )

        healthy = True
        reasons: list[str] = []

        if m.success_rate < self._success_threshold:
            healthy = False
            reasons.append(f"Low success rate ({m.success_rate:.0%} < {self._success_threshold:.0%})")

        if m.applied_rate < self._applied_threshold:
            healthy = False
            reasons.append(f"Low applied rate ({m.applied_rate:.0%} < {self._applied_threshold:.0%})")

        return HealthReport(
            skill_name=m.skill_name,
            healthy=healthy,
            success_rate=m.success_rate,
            applied_rate=m.applied_rate,
            total_executions=total,
            recommendation="; ".join(reasons) if reasons else "Healthy",
        )
