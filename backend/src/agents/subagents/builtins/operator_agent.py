"""Operator subagent configuration."""

from src.agents.subagents.config import SubagentConfig

OPERATOR_AGENT_CONFIG = SubagentConfig(
    name="operator",
    description="""Runtime and DevOps specialist for services, Docker, SSH, DB, and smoke checks.""",
    system_prompt="""Run operational checks carefully, capture exact outcomes, and avoid destructive actions without approval.

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
