"""Configuration for the subagent system loaded from config.yaml."""

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SubagentOverrideConfig(BaseModel):
    """Per-agent configuration overrides."""

    model: str | None = Field(
        default=None,
        description="Model name for this subagent (None = inherit the subagent default)",
    )
    max_turns: int | None = Field(
        default=None,
        ge=1,
        description="Soft maximum turns for this subagent (None = use the subagent default; no fixed upper clamp)",
    )
    timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        description="Timeout in seconds for this subagent (None = use global default)",
    )
    tools: list[str] | None = Field(
        default=None,
        description="Explicit tool allowlist for this subagent (None = use subagent default)",
    )
    disallowed_tools: list[str] | None = Field(
        default=None,
        description="Explicit tool denylist for this subagent (None = use subagent default)",
    )


class SubagentsAppConfig(BaseModel):
    """Configuration for the subagent system."""

    timeout_seconds: int = Field(
        default=900,
        ge=1,
        description="Default timeout in seconds for all subagents (default: 900 = 15 minutes)",
    )
    agents: dict[str, SubagentOverrideConfig] = Field(
        default_factory=dict,
        description="Per-agent configuration overrides keyed by agent name",
    )
    max_concurrent_subagents: int = Field(
        default=3,
        ge=1,
        description="Global concurrency cap for all running subagents.",
    )
    max_active_subagents_per_thread: int = Field(
        default=2,
        ge=1,
        description="Maximum active subagents allowed for a single thread at one time.",
    )
    max_total_subagents_per_thread: int = Field(
        default=8,
        ge=1,
        description="Maximum total delegated subagent tasks that may coexist for one thread.",
    )
    max_total_subagent_jobs: int = Field(
        default=64,
        ge=1,
        description="Global ceiling for retained delegated subagent jobs, including terminal history.",
    )
    max_events_per_subagent: int = Field(
        default=200,
        ge=1,
        description="Maximum retained runtime events per delegated subagent job.",
    )
    max_ai_messages_per_subagent: int = Field(
        default=12,
        ge=0,
        description="Maximum retained AI message snapshots per delegated subagent job; 0 disables retention.",
    )
    terminal_job_retention_seconds: int = Field(
        default=3600,
        ge=0,
        description="How long terminal subagent job records are retained before history pruning may remove them.",
    )
    enable_system_memory_guard: bool = Field(
        default=True,
        description="Whether to block new subagent scheduling when host memory is below a safety threshold.",
    )
    min_available_memory_gb: float = Field(
        default=8.0,
        ge=0.0,
        description="Soft host-memory target shown in runtime health; does not block local execution by itself.",
    )
    oom_critical_available_memory_gb: float = Field(
        default=1.0,
        ge=0.0,
        description="Hard OOM-risk threshold. Memory guards may block or truncate only below this available-memory value.",
    )
    estimated_memory_per_subagent_gb: float = Field(
        default=2.0,
        gt=0.0,
        description="Estimated incremental memory cost per active subagent used by the memory guard heuristic.",
    )

    def get_override_for(self, agent_name: str) -> SubagentOverrideConfig | None:
        """Get a per-agent override, accepting exact or normalized names."""
        override = self.agents.get(agent_name)
        if override is not None:
            return override
        normalized_name = _normalize_agent_name(agent_name)
        for configured_name, configured_override in self.agents.items():
            if _normalize_agent_name(configured_name) == normalized_name:
                return configured_override
        return None

    def get_timeout_for(self, agent_name: str) -> int:
        """Get the effective timeout for a specific agent.

        Args:
            agent_name: The name of the subagent.

        Returns:
            The timeout in seconds, using per-agent override if set, otherwise global default.
        """
        override = self.get_override_for(agent_name)
        if override is not None and override.timeout_seconds is not None:
            return override.timeout_seconds
        return self.timeout_seconds


def _normalize_agent_name(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


_subagents_config: SubagentsAppConfig = SubagentsAppConfig()


def get_subagents_app_config() -> SubagentsAppConfig:
    """Get the current subagents configuration."""
    return _subagents_config


def load_subagents_config_from_dict(config_dict: dict) -> None:
    """Load subagents configuration from a dictionary."""
    global _subagents_config
    _subagents_config = SubagentsAppConfig(**config_dict)

    overrides_summary = {name: override.model_dump(exclude_none=True) for name, override in _subagents_config.agents.items() if override.model_dump(exclude_none=True)}
    if overrides_summary:
        logger.info(
            "Subagents config loaded: default timeout=%ss, max_concurrent=%s, per_thread_active=%s, memory_guard=%s, per-agent overrides=%s",
            _subagents_config.timeout_seconds,
            _subagents_config.max_concurrent_subagents,
            _subagents_config.max_active_subagents_per_thread,
            _subagents_config.enable_system_memory_guard,
            overrides_summary,
        )
    else:
        logger.info(
            "Subagents config loaded: default timeout=%ss, max_concurrent=%s, per_thread_active=%s, memory_guard=%s, no per-agent overrides",
            _subagents_config.timeout_seconds,
            _subagents_config.max_concurrent_subagents,
            _subagents_config.max_active_subagents_per_thread,
            _subagents_config.enable_system_memory_guard,
        )
