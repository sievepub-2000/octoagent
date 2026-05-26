"""Configuration for startup self-check and self-repair guard."""

from pydantic import BaseModel, Field


class SystemGuardConfig(BaseModel):
    enabled: bool = Field(
        default=True,
        description="Whether startup/shutdown self-check guard is enabled.",
    )
    auto_repair: bool = Field(
        default=True,
        description="Whether to execute built-in repair actions when issues are detected.",
    )
    invoke_default_agent_on_issue: bool = Field(
        default=True,
        description="Whether to call the default agent for a self-repair plan when issues are detected.",
    )
    startup_agent_timeout_seconds: float = Field(
        default=20.0,
        ge=1.0,
        le=120.0,
        description="Timeout for default-agent self-repair advisory call.",
    )
    startup_agent_async: bool = Field(
        default=True,
        description="Whether startup advisory agent calls should run in the background instead of blocking API startup.",
    )
    vector_store_path: str = Field(
        default="system_guard_vectors.duckdb",
        description="DuckDB path for vectorized system lifecycle persistence.",
    )
    namespace: str = Field(
        default="system_lifecycle",
        description="Namespace used for lifecycle snapshots in the vector store.",
    )
    register_signal_handlers: bool = Field(
        default=True,
        description="Whether to register SIGINT/SIGTERM handlers for crash-safe snapshot persistence.",
    )
    capture_atexit: bool = Field(
        default=True,
        description="Whether to capture best-effort final snapshot via atexit hook.",
    )
    export_signing_secret: str | None = Field(
        default=None,
        description="Optional HMAC secret used to sign exported lifecycle snapshots.",
    )
    require_signed_exports: bool = Field(
        default=False,
        description="Whether unsigned exports should be rejected when no signing secret is configured.",
    )
    max_snapshots_per_namespace: int | None = Field(
        default=200,
        ge=1,
        le=10000,
        description="Maximum number of lifecycle snapshots retained per namespace. Set to null to disable pruning.",
    )
    runtime_embeddings_enabled: bool = Field(
        default=False,
        description=("Whether system guard should call embedded runtime model for vector embeddings. Disabled by default to keep startup/shutdown snapshots robust in environments where llama-cpp runtime may be unstable."),
    )


_system_guard_config = SystemGuardConfig()


def get_system_guard_config() -> SystemGuardConfig:
    return _system_guard_config


def load_system_guard_config_from_dict(config_dict: dict) -> None:
    global _system_guard_config
    _system_guard_config = SystemGuardConfig(**config_dict)
