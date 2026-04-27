"""Configuration for memory mechanism."""

from typing import Literal

from pydantic import BaseModel, Field


class MemoryConfig(BaseModel):
    """Configuration for global memory mechanism."""

    enabled: bool = Field(
        default=True,
        description="Whether to enable memory mechanism",
    )
    storage_path: str = Field(
        default="",
        description=(
            "Path to store memory data. "
            "If empty, defaults to `{base_dir}/default/memory.json` (see Paths.memory_file). "
            "Absolute paths are used as-is. "
            "Relative paths are resolved against `Paths.base_dir` "
            "(not the backend working directory). "
            "Use `default/memory.json` for workspace-local memory."
        ),
    )
    debounce_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Seconds to wait before processing queued updates (debounce)",
    )
    model_name: str | None = Field(
        default=None,
        description="Model name to use for memory updates (None = use default model)",
    )
    max_facts: int = Field(
        default=100,
        ge=10,
        le=500,
        description="Maximum number of facts to store",
    )
    fact_confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold for storing facts",
    )
    injection_enabled: bool = Field(
        default=True,
        description="Whether to inject memory into system prompt",
    )
    max_injection_tokens: int = Field(
        default=2000,
        ge=100,
        le=8000,
        description="Maximum tokens to use for memory injection",
    )
    write_governance_enabled: bool = Field(
        default=True,
        description="Whether long-term and permanent memory writes are evaluated through governance rules",
    )
    write_governance_mode: Literal["audit", "enforce"] = Field(
        default="enforce",
        description="Whether write governance should annotate or actively block writes",
    )
    long_term_retention_days: int = Field(
        default=180,
        ge=1,
        le=3650,
        description="Default retention window for long-term memory namespaces",
    )
    permanent_retention_days: int = Field(
        default=3650,
        ge=1,
        le=36500,
        description="Fallback retention window when permanent memory is configured with an explicit TTL",
    )
    permanent_memory_immutable: bool = Field(
        default=True,
        description="Whether permanent memory namespaces should be marked immutable in governance metadata",
    )


# Global configuration instance
_memory_config: MemoryConfig = MemoryConfig()


def get_memory_config() -> MemoryConfig:
    """Get the current memory configuration."""
    return _memory_config


def set_memory_config(config: MemoryConfig) -> None:
    """Set the memory configuration."""
    global _memory_config
    _memory_config = config


def load_memory_config_from_dict(config_dict: dict) -> None:
    """Load memory configuration from a dictionary."""
    global _memory_config
    _memory_config = MemoryConfig(**config_dict)
