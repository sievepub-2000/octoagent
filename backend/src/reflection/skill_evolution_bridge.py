"""Bridge between ReflectionService and SkillEvolution.

Registers a HookCore listener on task completion/failure events.
When fired, records an observation in ReflectionService, derives
insights, and feeds actionable insights to the SkillEvolution pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _insight_to_trace(insight):
    """Convert a ReflectionInsight into an ExecutionTrace for SkillAnalyzer."""
    from src.skill_evolution.analyzer import ExecutionTrace

    trace = ExecutionTrace(
        task_description=insight.description,
        success=insight.category not in ("skill_gap", "tool_failure"),
        error_message=insight.suggested_action,
    )
    if insight.category == "skill_gap":
        trace.skills_failed = [f"skill-gap-{insight.insight_id}"]
    elif insight.category == "tool_failure":
        trace.tools_failed = [f"tool-{insight.insight_id}"]
    return trace


async def _on_task_event(event: str, payload: dict[str, Any]) -> None:
    """HookCore listener for task completion/failure events."""
    try:
        from src.reflection import ExecutionObservation, get_reflection_service

        task_id = payload.get("task_id", "unknown")
        is_failure = "fail" in event.lower()

        # 1. Record observation
        obs = ExecutionObservation(
            observation_id=f"obs-{task_id}-{event}",
            task_id=task_id,
            category="error" if is_failure else "outcome",
            summary=payload.get("summary", f"Task event: {event}"),
            details=payload,
            severity="critical" if is_failure else "info",
        )
        reflection = get_reflection_service()
        reflection.record_observation(obs)

        # 2. Derive insights
        insights = reflection.derive_insights()
        if not insights:
            return

        # 3. Feed actionable insights to skill evolution
        from src.skill_evolution.analyzer import SkillAnalyzer
        from src.skill_evolution.evolver import SkillEvolver
        from src.skill_evolution.registry import SkillEvolutionRegistry

        try:
            from src.config import get_paths

            data_dir = get_paths().runtime_root / "skill_evolution"
        except Exception:
            return

        registry = SkillEvolutionRegistry(data_dir=data_dir)
        analyzer = SkillAnalyzer()
        from src.skill_evolution.types import EvolutionConfig

        evolver = SkillEvolver(
            registry=registry,
            skills_root=data_dir / "skills",
            config=EvolutionConfig(),
        )

        for insight in insights:
            if insight.confidence < 0.5:
                continue
            trace = _insight_to_trace(insight)
            suggestions = analyzer.analyze(trace)
            for suggestion in suggestions:
                if suggestion.confidence >= analyzer._threshold:
                    try:
                        evolver.evolve(suggestion)
                        logger.info(
                            "Evolved skill %s (%s) from insight %s",
                            suggestion.skill_name,
                            suggestion.mode.value,
                            insight.insight_id,
                        )
                    except Exception:
                        logger.warning(
                            "Failed to evolve skill %s",
                            suggestion.skill_name,
                            exc_info=True,
                        )
        registry.save()
    except Exception:
        logger.warning("Reflection→SkillEvolution bridge error", exc_info=True)


def register_reflection_hooks() -> None:
    """Register HookCore listeners that bridge Reflection → SkillEvolution."""
    try:
        from src.hook_core import (
            EVENT_TASK_COMPLETED,
            EVENT_TASK_FAILED,
            get_hook_core_service,
        )

        hook = get_hook_core_service()

        async def on_completed(payload: dict[str, Any]) -> None:
            await _on_task_event(EVENT_TASK_COMPLETED, payload)

        async def on_failed(payload: dict[str, Any]) -> None:
            await _on_task_event(EVENT_TASK_FAILED, payload)

        hook.on(EVENT_TASK_COMPLETED, on_completed)
        hook.on(EVENT_TASK_FAILED, on_failed)
        logger.info("Reflection→SkillEvolution bridge listeners registered")
    except Exception:
        logger.warning("Failed to register reflection→skill_evolution hooks", exc_info=True)
