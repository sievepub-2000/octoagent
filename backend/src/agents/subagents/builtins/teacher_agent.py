"""Teacher subagent configuration."""

from src.agents.subagents.config import SubagentConfig

TEACHER_AGENT_CONFIG = SubagentConfig(
    name="teacher",
    description="""Explanation specialist for user-facing reports and learning-oriented summaries.""",
    system_prompt="""Explain decisions warmly and clearly, preserving technical accuracy without overwhelming the user.

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
