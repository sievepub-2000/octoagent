"""Reviewer subagent configuration."""

from src.agents.subagents.config import SubagentConfig

REVIEWER_AGENT_CONFIG = SubagentConfig(
    name="reviewer",
    description="""Review specialist for regressions, tests, security, and maintainability.""",
    system_prompt="""Lead with findings, rank severity, cite files, and call out missing tests or residual risk.

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
