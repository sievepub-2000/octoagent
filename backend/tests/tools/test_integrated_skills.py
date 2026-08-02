from __future__ import annotations

from src.storage.skills import load_skills
from src.tools.capability_tools import load_skill_tool


def test_integrated_skills_are_loadable() -> None:
    skills = load_skills(enabled_only=False)
    names = {skill.name for skill in skills}

    assert "data-analysis" in names
    assert "deep-research" in names
    assert "office-generation" in names


def test_load_skill_tool_loads_deep_research() -> None:
    result = load_skill_tool.invoke({"skill_name": "deep-research"})

    assert "# Skill: deep-research" in result
    assert "well-informed content" in result
