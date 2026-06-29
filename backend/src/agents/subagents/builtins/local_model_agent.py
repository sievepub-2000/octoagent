"""Local model (ornith on port 8000) sub-agent configuration."""

from src.agents.subagents.config import SubagentConfig

LOCAL_MODEL_AGENT_CONFIG = SubagentConfig(
    name="local-model",
    description="""A sub-agent powered by the local model (ornith-1.0-35b-nvfp4 on port 8000).

Use this subagent when:
- The task is self-contained and does not require the full capabilities of the primary model
- You want to offload work to the local GPU-powered model to save API costs
- The task involves coding, analysis, or generation that the local model handles well
- Running on local hardware with zero latency and no rate limits

Do NOT use for:
- Tasks requiring very long context (>100K tokens)
- Complex multi-step reasoning that benefits from a frontier model
- Vision/image processing (local model has limited vision support)
""",
    system_prompt="""You are a local-model-powered subagent.

<guidelines>
- Complete the delegated task efficiently using the available tools
- You have the same sandbox environment as the parent agent
- Return a clear summary of what you accomplished
- If you encounter limitations, state them clearly
</guidelines>
""",
    tools=None,
    disallowed_tools=["task", "ask_clarification", "present_files"],
    model="ornith-1.0-35b-nvfp4",
    max_turns=25,
    timeout_seconds=600,
)
