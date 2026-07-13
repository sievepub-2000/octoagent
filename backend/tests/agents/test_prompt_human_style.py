from __future__ import annotations

from src.agents.lead_agent.prompt import apply_prompt_template


def test_full_prompt_includes_human_collaboration_style() -> None:
    prompt = apply_prompt_template(agent_name="OctoAgent")

    assert "<collaboration>" in prompt
    assert "Be concise" in prompt
    assert "Report progress briefly" in prompt


def test_compact_prompt_keeps_dialogue_and_completion_rules() -> None:
    prompt = apply_prompt_template(agent_name="OctoAgent", compact_prompt=True)

    assert "<fast_dialogue_rules>" in prompt
    assert "capable teammate" in prompt
    assert "do not restart it" in prompt
