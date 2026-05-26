from __future__ import annotations

from src.storage.skills import load_skills
from src.tools.capability_tools import load_skill_tool


def test_integrated_skills_are_loadable() -> None:
    skills = load_skills(enabled_only=False)
    names = {skill.name for skill in skills}

    assert "agent-rules-books" in names
    assert "goalbuddy" in names
    assert "ian-handdrawn-ppt" in names


def test_load_skill_tool_loads_goalbuddy() -> None:
    result = load_skill_tool.invoke({"skill_name": "goalbuddy"})

    assert "Goal contract skill" in result
    assert "acceptance checks" in result
