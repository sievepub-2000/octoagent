"""Coder subagent configuration."""

from src.agents.subagents.config import SubagentConfig

CODER_AGENT_CONFIG = SubagentConfig(
    name="coder",
    description="""Focused implementation specialist for code patches.""",
    system_prompt="""Make minimal, style-consistent changes. Prefer existing helpers and keep unrelated files untouched.

<workflow>
- Stay within the delegated role.
- Return actionable findings, not broad narration.
- Surface blockers and verification evidence.
</workflow>
""",
    tools=None,
    disallowed_tools=["task", "ask_clarification", "present_files"],
    model="inherit",
    max_turns=None,
)
