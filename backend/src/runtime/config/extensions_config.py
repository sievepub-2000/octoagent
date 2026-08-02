"""Unified extensions configuration for MCP servers, skills, and repo hooks."""

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.runtime.config.tool_config import ToolPermissionScope


class McpOAuthConfig(BaseModel):
    """OAuth configuration for an MCP server (HTTP/SSE transports)."""

    enabled: bool = Field(default=True, description="Whether OAuth token injection is enabled")
    token_url: str = Field(description="OAuth token endpoint URL")
    grant_type: Literal["client_credentials", "refresh_token"] = Field(
        default="client_credentials",
        description="OAuth grant type",
    )
    client_id: str | None = Field(default=None, description="OAuth client ID")
    client_secret: str | None = Field(default=None, description="OAuth client secret")
    refresh_token: str | None = Field(default=None, description="OAuth refresh token (for refresh_token grant)")
    scope: str | None = Field(default=None, description="OAuth scope")
    audience: str | None = Field(default=None, description="OAuth audience (provider-specific)")
    token_field: str = Field(default="access_token", description="Field name containing access token in token response")
    token_type_field: str = Field(default="token_type", description="Field name containing token type in token response")
    expires_in_field: str = Field(default="expires_in", description="Field name containing expiry (seconds) in token response")
    default_token_type: str = Field(default="Bearer", description="Default token type when missing in token response")
    refresh_skew_seconds: int = Field(default=60, description="Refresh token this many seconds before expiry")
    extra_token_params: dict[str, str] = Field(default_factory=dict, description="Additional form params sent to token endpoint")
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class McpSmokeTestConfig(BaseModel):
    """Minimal MCP smoke invocation used for readiness checks."""

    enabled: bool = Field(default=True, description="Whether this server should run a minimal invocation smoke test")
    tool: str = Field(default="", description="Tool name or suffix to invoke after list_tools succeeds")
    args: dict[str, Any] = Field(default_factory=dict, description="Arguments for the minimal smoke tool invocation")
    expected: dict[str, Any] = Field(default_factory=dict, description="Optional expected output hints for operators")
    model_config = ConfigDict(extra="allow")


class McpServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    enabled: bool = Field(default=True, description="Whether this MCP server is enabled")
    type: str = Field(default="stdio", description="Transport type: 'stdio', 'sse', or 'http'")
    command: str | None = Field(default=None, description="Command to execute to start the MCP server (for stdio type)")
    args: list[str] = Field(default_factory=list, description="Arguments to pass to the command (for stdio type)")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables for the MCP server")
    url: str | None = Field(default=None, description="URL of the MCP server (for sse or http type)")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers to send (for sse or http type)")
    oauth: McpOAuthConfig | None = Field(default=None, description="OAuth configuration (for sse or http type)")
    description: str = Field(default="", description="Human-readable description of what this MCP server provides")
    permission_scope: ToolPermissionScope = Field(
        default="sandbox",
        alias="permissionScope",
        description="Default permission scope for tools loaded from this MCP server.",
    )
    smoke_test: McpSmokeTestConfig | None = Field(
        default=None,
        alias="smokeTest",
        description="Minimal startup/list_tools/invocation smoke check for this MCP server.",
    )
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class SkillStateConfig(BaseModel):
    """Configuration for a single skill's state."""

    enabled: bool = Field(default=True, description="Whether this skill is enabled")


class HookStateConfig(BaseModel):
    """Configuration for a single repository hook's state."""

    enabled: bool = Field(default=True, description="Whether this hook is enabled")


class ExtensionsConfig(BaseModel):
    """Unified configuration for MCP servers, skills, and repository hooks."""

    mcp_servers: dict[str, McpServerConfig] = Field(
        default_factory=dict,
        description="Map of MCP server name to configuration",
        alias="mcpServers",
    )
    skills: dict[str, SkillStateConfig] = Field(
        default_factory=dict,
        description="Map of skill name to state configuration",
    )
    hooks: dict[str, HookStateConfig] = Field(
        default_factory=dict,
        description="Map of repository hook name to state configuration",
    )
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @classmethod
    def resolve_config_path(cls, config_path: str | None = None) -> Path:
        """Resolve the extensions config file path.

        Explicit arguments and the environment override must exist. Local
        development otherwise uses the same runtime/config path as Docker.

        Args:
            config_path: Optional path to extensions config file.

        Returns:
            The single authoritative extensions config path.
        """
        if config_path:
            path = Path(config_path)
            if not path.exists():
                raise FileNotFoundError(f"Extensions config file specified by param `config_path` not found at {path}")
            return path
        env_path = os.getenv("OCTO_AGENT_EXTENSIONS_CONFIG_PATH")
        if env_path:
            path = Path(env_path)
            if not path.exists():
                raise FileNotFoundError(f"Extensions config file specified by environment variable `OCTO_AGENT_EXTENSIONS_CONFIG_PATH` not found at {path}")
            return path
        return Path(__file__).resolve().parents[4] / "runtime" / "config" / "extensions_config.json"

    @classmethod
    def from_file(cls, config_path: str | None = None) -> "ExtensionsConfig":
        """Load extensions config from JSON file.

        See `resolve_config_path` for more details.

        Args:
            config_path: Path to the extensions config file.

        Returns:
            ExtensionsConfig: The loaded config, or empty config if file not found.
        """
        resolved_path = cls.resolve_config_path(config_path)
        if not resolved_path.exists():
            return cls(mcp_servers={}, skills={}, hooks={})

        try:
            with open(resolved_path, encoding="utf-8") as f:
                config_data = json.load(f)
            cls.resolve_env_variables(config_data)
            return cls.model_validate(config_data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Extensions config file at {resolved_path} is not valid JSON: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to load extensions config from {resolved_path}: {e}") from e

    @classmethod
    def resolve_env_variables(cls, config: dict[str, Any]) -> dict[str, Any]:
        """Recursively resolve environment variables in the config.

        Environment variables are resolved using the `os.getenv` function. Example: $OPENAI_API_KEY

        Args:
            config: The config to resolve environment variables in.

        Returns:
            The config with environment variables resolved.
        """
        for key, value in config.items():
            if isinstance(value, str):
                if value.startswith("$"):
                    env_value = os.getenv(value[1:])
                    if env_value is None:
                        # Unresolved placeholder — store empty string so downstream
                        # consumers (e.g. MCP servers) don't receive the literal "$VAR"
                        # token as an actual environment value.
                        config[key] = ""
                    else:
                        config[key] = env_value
                else:
                    config[key] = value
            elif isinstance(value, dict):
                config[key] = cls.resolve_env_variables(value)
            elif isinstance(value, list):
                resolved_items: list[Any] = []
                for item in value:
                    if isinstance(item, dict):
                        resolved_items.append(cls.resolve_env_variables(item))
                    elif isinstance(item, str) and item.startswith("$"):
                        resolved_items.append(os.getenv(item[1:], ""))
                    else:
                        resolved_items.append(item)
                config[key] = resolved_items
        return config

    def get_enabled_mcp_servers(self) -> dict[str, McpServerConfig]:
        """Get only the enabled MCP servers.

        Returns:
            Dictionary of enabled MCP servers.
        """
        return {name: config for name, config in self.mcp_servers.items() if config.enabled}

    def is_skill_enabled(self, skill_name: str, skill_category: str) -> bool:
        """Check if a skill is enabled.

        Args:
            skill_name: Name of the skill
            skill_category: Category of the skill

        Returns:
            True if enabled, False otherwise
        """
        skill_config = self.skills.get(skill_name)
        if skill_config is None:
            # Default to enable for public & custom skill
            return skill_category in ("public", "custom")
        return skill_config.enabled

    def is_hook_enabled(self, hook_name: str) -> bool:
        """Check if a repository hook is enabled.

        Installed hooks default to enabled until explicitly disabled.
        """
        hook_config = self.hooks.get(hook_name)
        if hook_config is None:
            return True
        return hook_config.enabled

    def to_serializable_dict(self) -> dict[str, Any]:
        """Convert config to the persisted JSON structure."""
        return {
            "mcpServers": {name: server.model_dump(exclude_none=True) for name, server in self.mcp_servers.items()},
            "skills": {name: {"enabled": skill.enabled} for name, skill in self.skills.items()},
            "hooks": {name: {"enabled": hook.enabled} for name, hook in self.hooks.items()},
        }


_extensions_config: ExtensionsConfig | None = None


def get_extensions_config() -> ExtensionsConfig:
    """Get the extensions config instance.

    Returns a cached singleton instance. Use `reload_extensions_config()` to reload
    from file, or `reset_extensions_config()` to clear the cache.

    Returns:
        The cached ExtensionsConfig instance.
    """
    global _extensions_config
    if _extensions_config is None:
        _extensions_config = ExtensionsConfig.from_file()
    return _extensions_config


def reload_extensions_config(config_path: str | None = None) -> ExtensionsConfig:
    """Reload the extensions config from file and update the cached instance.

    This is useful when the config file has been modified and you want
    to pick up the changes without restarting the application.

    Args:
        config_path: Optional path to extensions config file. If not provided,
                     uses the default resolution strategy.

    Returns:
        The newly loaded ExtensionsConfig instance.
    """
    global _extensions_config
    _extensions_config = ExtensionsConfig.from_file(config_path)
    return _extensions_config


def reset_extensions_config() -> None:
    """Reset the cached extensions config instance.

    This clears the singleton cache, causing the next call to
    `get_extensions_config()` to reload from file. Useful for testing
    or when switching between different configurations.
    """
    global _extensions_config
    _extensions_config = None


def set_extensions_config(config: ExtensionsConfig) -> None:
    """Set a custom extensions config instance.

    This allows injecting a custom or mock config for testing purposes.

    Args:
        config: The ExtensionsConfig instance to use.
    """
    global _extensions_config
    _extensions_config = config
