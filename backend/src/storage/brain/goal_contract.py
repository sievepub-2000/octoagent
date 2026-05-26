"""Goal-Contract schema (Sprint-2 skeleton — NOT wired yet).

Defines the structured representation of "what the user actually wants" that
every long-horizon task should be evaluated against. Plan: the producer agent
emits one ``GoalContract`` at task entry; the ``GoalDriftMiddleware`` (TODO)
embeds it and compares against the rolling action window every N steps.

Status: schema only. Producer + critic wiring is Sprint-2 work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoalContract:
    """User-intent contract for a long-horizon task."""

    goal_summary: str  # one-sentence restatement of user intent
    success_criteria: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    must_use_tools: list[str] = field(default_factory=list)
    deadline_iso: str | None = None
    issued_at_iso: str = ""
    issued_by_model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_prompt_block(self) -> str:
        lines = [
            "<goal_contract>",
            f"  goal: {self.goal_summary}",
        ]
        if self.success_criteria:
            lines.append("  success_criteria:")
            for c in self.success_criteria:
                lines.append(f"    - {c}")
        if self.forbidden_actions:
            lines.append("  forbidden_actions:")
            for c in self.forbidden_actions:
                lines.append(f"    - {c}")
        if self.must_use_tools:
            lines.append(f"  must_use_tools: {', '.join(self.must_use_tools)}")
        if self.deadline_iso:
            lines.append(f"  deadline: {self.deadline_iso}")
        lines.append("</goal_contract>")
        return "\n".join(lines)


__all__ = ["GoalContract"]
