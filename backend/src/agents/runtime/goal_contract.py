"""Agent Runtime goal contract used only to preserve explicit user intent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoalContract:
    goal_summary: str
    success_criteria: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    must_use_tools: list[str] = field(default_factory=list)
    deadline_iso: str | None = None
    issued_at_iso: str = ""
    issued_by_model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_prompt_block(self) -> str:
        lines = ["<goal_contract>", f"  goal: {self.goal_summary}"]
        for label, values in (
            ("success_criteria", self.success_criteria),
            ("forbidden_actions", self.forbidden_actions),
        ):
            if values:
                lines.append(f"  {label}:")
                lines.extend(f"    - {value}" for value in values)
        if self.must_use_tools:
            lines.append(f"  must_use_tools: {', '.join(self.must_use_tools)}")
        if self.deadline_iso:
            lines.append(f"  deadline: {self.deadline_iso}")
        lines.append("</goal_contract>")
        return "\n".join(lines)


__all__ = ["GoalContract"]
