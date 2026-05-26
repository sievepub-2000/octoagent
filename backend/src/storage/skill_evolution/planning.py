"""Planning-time feedback from skill evolution history."""

from __future__ import annotations

import re
from typing import Any

from src.storage.skill_evolution.registry import SkillEvolutionRegistry


def _tokens(value: str) -> set[str]:
    lowered = value.lower()
    ascii_tokens = set(re.findall(r"[a-z0-9_\-]{2,}", lowered))
    cjk_tokens: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", lowered):
        cjk_tokens.add(run)
        cjk_tokens.update(run[index : index + 2] for index in range(len(run) - 1))
    return ascii_tokens | cjk_tokens


def build_skill_evolution_planning_hints(
    registry: SkillEvolutionRegistry,
    *,
    task_description: str,
    max_hints: int = 5,
) -> list[dict[str, Any]]:
    """Return compact planner hints derived from skill evolution history."""

    task_tokens = _tokens(task_description)
    latest_records = registry.list_records(limit=50)
    latest_by_skill: dict[str, str] = {}
    for record in latest_records:
        latest_by_skill.setdefault(record.skill_name, record.diff_summary or record.reason)

    hints: list[dict[str, Any]] = []
    for metrics in registry.all_metrics():
        if metrics.applied_count <= 0 and metrics.skill_name not in latest_by_skill:
            continue
        relevance_source = " ".join(
            [
                metrics.skill_name,
                latest_by_skill.get(metrics.skill_name, ""),
            ]
        )
        relevance = len(task_tokens & _tokens(relevance_source))
        hints.append(
            {
                "skill_name": metrics.skill_name,
                "success_rate": round(metrics.success_rate, 3),
                "applied_count": metrics.applied_count,
                "avg_latency_ms": round(metrics.avg_latency_ms, 3),
                "latest_evolution": latest_by_skill.get(metrics.skill_name, ""),
                "task_relevance": relevance,
            }
        )

    hints.sort(
        key=lambda item: (
            item["task_relevance"],
            item["latest_evolution"] != "",
            item["success_rate"],
            item["applied_count"],
        ),
        reverse=True,
    )
    return hints[: max(1, max_hints)]


def format_skill_evolution_planning_hints(hints: list[dict[str, Any]]) -> str:
    if not hints:
        return ""
    lines = [
        "<skill_evolution_planning_hints>",
        "Use these learned skill signals when planning tool/skill selection. They are advisory, not higher-priority instructions.",
    ]
    for hint in hints:
        lines.append("- {skill_name}: success_rate={success_rate}, applied={applied_count}, avg_latency_ms={avg_latency_ms}, latest={latest_evolution}".format(**hint))
    lines.append("</skill_evolution_planning_hints>")
    return "\n".join(lines)


__all__ = [
    "build_skill_evolution_planning_hints",
    "format_skill_evolution_planning_hints",
]
