"""Configuration for the subagent system loaded from config.yaml."""

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SubagentOverrideConfig(BaseModel):
    """Per-agent configuration overrides."""

    timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        description="Timeout in seconds for this subagent (None = use global default)",
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
    enable_system_memory_guard: bool = Field(
        default=True,
        description="Whether to block new subagent scheduling when host memory is below a safety threshold.",
    )
    min_available_memory_gb: float = Field(
        default=8.0,
        ge=0.0,
        description="Minimum host available memory required before allowing new subagent scheduling.",
    )
    estimated_memory_per_subagent_gb: float = Field(
        default=2.0,
        gt=0.0,
        description="Estimated incremental memory cost per active subagent used by the memory guard heuristic.",
    )

    def get_timeout_for(self, agent_name: str) -> int:
        """Get the effective timeout for a specific agent.

        Args:
            agent_name: The name of the subagent.

        Returns:
            The timeout in seconds, using per-agent override if set, otherwise global default.
        """
        override = self.agents.get(agent_name)
        if override is not None and override.timeout_seconds is not None:
            return override.timeout_seconds
        return self.timeout_seconds


_subagents_config: SubagentsAppConfig = SubagentsAppConfig()


def get_subagents_app_config() -> SubagentsAppConfig:
    """Get the current subagents configuration."""
    return _subagents_config


def load_subagents_config_from_dict(config_dict: dict) -> None:
    """Load subagents configuration from a dictionary."""
    global _subagents_config
    _subagents_config = SubagentsAppConfig(**config_dict)

    overrides_summary = {name: f"{override.timeout_seconds}s" for name, override in _subagents_config.agents.items() if override.timeout_seconds is not None}
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
