"""Planner subagent configuration."""

from src.agents.subagents.config import SubagentConfig

PLANNER_AGENT_CONFIG = SubagentConfig(
    name="planner",
    description="""Planning specialist for decomposing repo-level work and risk.""",
    system_prompt="""Own the plan, assumptions, dependencies, and verification strategy. Return concise ordered steps and blockers.

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
