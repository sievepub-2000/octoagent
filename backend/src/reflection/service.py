"""Runtime reflection service for self-observation and evaluation.

The reflection module enables the system to observe its own execution,
evaluate task outcomes, and generate improvement suggestions that feed
back into the skill evolution and brain planning pipelines.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class ExecutionObservation:
    """A single observation captured during or after task execution."""

    observation_id: str
    task_id: str
    timestamp: float = field(default_factory=time.time)
    category: Literal[
        "outcome", "performance", "error", "tool_usage", "model_quality"
    ] = "outcome"
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    severity: Literal["info", "warning", "critical"] = "info"


@dataclass
class ReflectionInsight:
    """An actionable insight derived from one or more observations."""

    insight_id: str
    source_observations: list[str] = field(default_factory=list)
    category: Literal[
        "skill_gap", "model_mismatch", "tool_failure", "prompt_quality", "efficiency"
    ] = "efficiency"
    description: str = ""
    suggested_action: str = ""
    confidence: float = 0.0


class ReflectionService:
    """Observe execution outcomes and derive actionable insights.

    The service maintains a sliding window of recent observations and
    periodically derives insights that can be consumed by the skill
    evolution and brain planning modules.
    """

    MAX_OBSERVATIONS = 500

    def __init__(self, store_dir: Path | None = None) -> None:
        self._observations: list[ExecutionObservation] = []
        self._insights: list[ReflectionInsight] = []
        self._store_dir = store_dir
        if store_dir is not None:
            self._load()

    # ------------------------------------------------------------------
    # Observations
    # ------------------------------------------------------------------

    def record_observation(self, obs: ExecutionObservation) -> None:
        """Record a new execution observation."""
        self._observations.append(obs)
        if len(self._observations) > self.MAX_OBSERVATIONS:
            self._observations = self._observations[-self.MAX_OBSERVATIONS :]
        self._persist()
        logger.debug("Recorded observation %s for task %s", obs.observation_id, obs.task_id)

    def get_observations(
        self,
        task_id: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[ExecutionObservation]:
        """Query recent observations with optional filters."""
        result = self._observations
        if task_id:
            result = [o for o in result if o.task_id == task_id]
        if category:
            result = [o for o in result if o.category == category]
        return list(reversed(result[-limit:]))

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    def derive_insights(self) -> list[ReflectionInsight]:
        """Analyze recent observations and produce actionable insights.

        This is a rule-based analysis pass.  More sophisticated LLM-backed
        analysis can be layered on top by the brain module.
        """
        insights: list[ReflectionInsight] = []

        # 1. Detect repeated errors → skill_gap
        error_obs = [o for o in self._observations if o.category == "error"]
        if len(error_obs) >= 3:
            recent_errors = error_obs[-10:]
            error_summaries = [o.summary for o in recent_errors]
            insights.append(
                ReflectionInsight(
                    insight_id=f"insight-error-cluster-{int(time.time())}",
                    source_observations=[o.observation_id for o in recent_errors],
                    category="skill_gap",
                    description=f"Detected {len(recent_errors)} recent errors: {'; '.join(error_summaries[:3])}",
                    suggested_action="Review error patterns and consider adding error-handling skills or improving prompts.",
                    confidence=min(0.9, 0.3 + len(recent_errors) * 0.1),
                )
            )

        # 2. Detect model quality issues
        quality_obs = [o for o in self._observations if o.category == "model_quality"]
        low_quality = [o for o in quality_obs if o.severity in ("warning", "critical")]
        if len(low_quality) >= 2:
            insights.append(
                ReflectionInsight(
                    insight_id=f"insight-model-quality-{int(time.time())}",
                    source_observations=[o.observation_id for o in low_quality[-5:]],
                    category="model_mismatch",
                    description=f"{len(low_quality)} tasks showed model quality concerns.",
                    suggested_action="Consider upgrading model tier or adjusting Brain routing thresholds.",
                    confidence=0.6,
                )
            )

        # 3. Detect tool failures
        tool_obs = [o for o in self._observations if o.category == "tool_usage"]
        failed_tools = [o for o in tool_obs if o.details.get("success") is False]
        if len(failed_tools) >= 2:
            tool_names = list({o.details.get("tool_name", "unknown") for o in failed_tools})
            insights.append(
                ReflectionInsight(
                    insight_id=f"insight-tool-failure-{int(time.time())}",
                    source_observations=[o.observation_id for o in failed_tools[-5:]],
                    category="tool_failure",
                    description=f"Tools {', '.join(tool_names[:3])} have been failing repeatedly.",
                    suggested_action="Check tool configuration, network connectivity, or disable unreliable tools.",
                    confidence=0.7,
                )
            )

        self._insights = insights
        self._persist()
        return insights

    def get_insights(self) -> list[ReflectionInsight]:
        """Return the most recently derived insights."""
        return list(self._insights)

    def export_observations(self, *, format: Literal["jsonl", "csv"] = "jsonl") -> str:
        observations = list(reversed(self._observations[-self.MAX_OBSERVATIONS :]))
        if format == "csv":
            buffer = io.StringIO()
            writer = csv.DictWriter(
                buffer,
                fieldnames=[
                    "observation_id",
                    "task_id",
                    "timestamp",
                    "category",
                    "summary",
                    "severity",
                    "details_json",
                ],
            )
            writer.writeheader()
            for observation in observations:
                writer.writerow(
                    {
                        "observation_id": observation.observation_id,
                        "task_id": observation.task_id,
                        "timestamp": observation.timestamp,
                        "category": observation.category,
                        "summary": observation.summary,
                        "severity": observation.severity,
                        "details_json": json.dumps(observation.details, ensure_ascii=False, sort_keys=True),
                    }
                )
            return buffer.getvalue()

        return "\n".join(
            json.dumps(
                {
                    "observation_id": observation.observation_id,
                    "task_id": observation.task_id,
                    "timestamp": observation.timestamp,
                    "category": observation.category,
                    "summary": observation.summary,
                    "details": observation.details,
                    "severity": observation.severity,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            for observation in observations
        )

    def export_insights(self, *, format: Literal["jsonl", "csv"] = "jsonl") -> str:
        insights = list(self._insights)
        if format == "csv":
            buffer = io.StringIO()
            writer = csv.DictWriter(
                buffer,
                fieldnames=[
                    "insight_id",
                    "category",
                    "description",
                    "suggested_action",
                    "confidence",
                    "source_observations_json",
                ],
            )
            writer.writeheader()
            for insight in insights:
                writer.writerow(
                    {
                        "insight_id": insight.insight_id,
                        "category": insight.category,
                        "description": insight.description,
                        "suggested_action": insight.suggested_action,
                        "confidence": insight.confidence,
                        "source_observations_json": json.dumps(insight.source_observations, ensure_ascii=False),
                    }
                )
            return buffer.getvalue()

        return "\n".join(
            json.dumps(
                {
                    "insight_id": insight.insight_id,
                    "source_observations": insight.source_observations,
                    "category": insight.category,
                    "description": insight.description,
                    "suggested_action": insight.suggested_action,
                    "confidence": insight.confidence,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            for insight in insights
        )

    # ------------------------------------------------------------------
    # Summary for Brain integration
    # ------------------------------------------------------------------

    def execution_summary(self, window: int = 20) -> dict[str, Any]:
        """Produce a compact summary of recent execution quality.

        Intended for consumption by the Brain planner / policy modules.
        """
        recent = self._observations[-window:] if self._observations else []
        outcomes = [o for o in recent if o.category == "outcome"]
        successes = sum(1 for o in outcomes if o.details.get("status") == "completed")
        failures = sum(1 for o in outcomes if o.details.get("status") == "failed")
        errors = sum(1 for o in recent if o.category == "error")

        return {
            "window_size": len(recent),
            "outcomes": {"completed": successes, "failed": failures},
            "error_count": errors,
            "success_rate": successes / max(successes + failures, 1),
            "insight_count": len(self._insights),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        if self._store_dir is None:
            return
        self._store_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "observations": [
                {
                    "observation_id": o.observation_id,
                    "task_id": o.task_id,
                    "timestamp": o.timestamp,
                    "category": o.category,
                    "summary": o.summary,
                    "details": o.details,
                    "severity": o.severity,
                }
                for o in self._observations[-self.MAX_OBSERVATIONS :]
            ],
            "insights": [
                {
                    "insight_id": i.insight_id,
                    "source_observations": i.source_observations,
                    "category": i.category,
                    "description": i.description,
                    "suggested_action": i.suggested_action,
                    "confidence": i.confidence,
                }
                for i in self._insights
            ],
        }
        path = self._store_dir / "reflection_state.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)

    def _load(self) -> None:
        if self._store_dir is None:
            return
        path = self._store_dir / "reflection_state.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for item in data.get("observations", []):
                self._observations.append(
                    ExecutionObservation(
                        observation_id=item["observation_id"],
                        task_id=item["task_id"],
                        timestamp=item.get("timestamp", 0),
                        category=item.get("category", "outcome"),
                        summary=item.get("summary", ""),
                        details=item.get("details", {}),
                        severity=item.get("severity", "info"),
                    )
                )
            for item in data.get("insights", []):
                self._insights.append(
                    ReflectionInsight(
                        insight_id=item["insight_id"],
                        source_observations=item.get("source_observations", []),
                        category=item.get("category", "efficiency"),
                        description=item.get("description", ""),
                        suggested_action=item.get("suggested_action", ""),
                        confidence=item.get("confidence", 0.0),
                    )
                )
            logger.info(
                "Loaded %d observations, %d insights from %s",
                len(self._observations),
                len(self._insights),
                path,
            )
        except Exception:
            logger.exception("Failed to load reflection state from %s", path)


_service: ReflectionService | None = None


def get_reflection_service() -> ReflectionService:
    """Return the singleton ReflectionService."""
    global _service
    if _service is None:
        store_dir: Path | None = None
        try:
            from src.config import get_paths

            store_dir = get_paths().runtime_root / "reflection"
        except Exception:
            pass
        _service = ReflectionService(store_dir=store_dir)
    return _service
