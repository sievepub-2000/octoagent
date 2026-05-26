"""Skill Evolution Engine — inspired by OpenSpace (HKUDS/OpenSpace).

Provides self-evolving skills with three evolution modes:
  - FIX: repair broken or outdated skill instructions in-place
  - DERIVED: create enhanced/specialized versions from parent skills
  - CAPTURED: extract novel reusable patterns from successful executions

Also includes quality monitoring for skill health metrics.
"""

from src.storage.skill_evolution.types import EvolutionMode, EvolutionRecord, QualityMetrics, SkillVersion

__all__ = [
    "EvolutionMode",
    "EvolutionRecord",
    "QualityMetrics",
    "SkillVersion",
]
