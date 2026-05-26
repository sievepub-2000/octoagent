"""Post-execution skill analyzer.

After each task completes, the analyzer inspects the execution trace and
decides which skills should be evolved (FIX / DERIVED / CAPTURED).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.storage.skill_evolution.types import EvolutionMode

logger = logging.getLogger(__name__)


@dataclass
class AnalysisSuggestion:
    """A single evolution suggestion produced by the analyzer."""

    skill_name: str
    mode: EvolutionMode
    reason: str
    confidence: float = 0.0  # 0‥1


@dataclass
class ExecutionTrace:
    """Lightweight representation of a task execution for analysis."""

    task_description: str = ""
    skills_used: list[str] = field(default_factory=list)
    skills_failed: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    tools_failed: list[str] = field(default_factory=list)
    success: bool = True
    error_message: str = ""
    token_usage: int = 0


class SkillAnalyzer:
    """Analyzes execution traces and produces evolution suggestions."""

    def __init__(self, *, confirmation_threshold: float = 0.6) -> None:
        self._threshold = confirmation_threshold

    def analyze(self, trace: ExecutionTrace) -> list[AnalysisSuggestion]:
        suggestions: list[AnalysisSuggestion] = []

        # Rule 1: Skills that failed → FIX
        for skill in trace.skills_failed:
            suggestions.append(
                AnalysisSuggestion(
                    skill_name=skill,
                    mode=EvolutionMode.FIX,
                    reason=f"Skill '{skill}' failed during execution: {trace.error_message[:200]}",
                    confidence=0.9,
                )
            )

        # Rule 2: Successful execution with high token usage → DERIVED for optimization
        if trace.success and trace.token_usage > 10000 and trace.skills_used:
            primary_skill = trace.skills_used[0]
            suggestions.append(
                AnalysisSuggestion(
                    skill_name=primary_skill,
                    mode=EvolutionMode.DERIVED,
                    reason=f"High token usage ({trace.token_usage}) suggests optimization opportunity",
                    confidence=0.5,
                )
            )

        # Rule 3: Successful task with no matching skill → CAPTURED
        if trace.success and not trace.skills_used:
            suggestions.append(
                AnalysisSuggestion(
                    skill_name=f"auto-{_slug(trace.task_description[:60])}",
                    mode=EvolutionMode.CAPTURED,
                    reason="Successful execution with novel workflow — candidate for new skill",
                    confidence=0.7,
                )
            )

        # Filter by confidence threshold
        return [s for s in suggestions if s.confidence >= self._threshold]


def _slug(text: str) -> str:
    """Create a simple slug from text."""
    import re

    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
