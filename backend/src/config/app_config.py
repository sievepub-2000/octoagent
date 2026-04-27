import logging
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

from src.config.app_config_loader import AppConfigLoader
from src.config.app_config_paths import load_project_dotenv, resolve_app_config_path
from src.config.app_config_service import AppConfigService
from src.config.checkpointer_config import CheckpointerConfig
from src.config.extensions_config import ExtensionsConfig
from src.config.model_config import ModelConfig
from src.config.sandbox_config import SandboxConfig
from src.config.skills_config import SkillsConfig
from src.config.tool_config import ToolConfig, ToolGroupConfig

logger = logging.getLogger(__name__)
load_project_dotenv()


class AppConfig(BaseModel):
    """Config for the OctoAgent application"""

    models: list[ModelConfig] = Field(default_factory=list, description="Available models")
    sandbox: SandboxConfig = Field(description="Sandbox configuration")
    tools: list[ToolConfig] = Field(default_factory=list, description="Available tools")
    tool_groups: list[ToolGroupConfig] = Field(default_factory=list, description="Available tool groups")
    skills: SkillsConfig = Field(default_factory=SkillsConfig, description="Skills configuration")
    extensions: ExtensionsConfig = Field(default_factory=ExtensionsConfig, description="Extensions configuration (MCP servers and skills state)")
    model_config = ConfigDict(extra="allow", frozen=False)
    checkpointer: CheckpointerConfig | None = Field(default=None, description="Checkpointer configuration")

    @classmethod
    def resolve_config_path(cls, config_path: str | None = None) -> Path:
        return resolve_app_config_path(config_path)

    @classmethod
    def from_file(cls, config_path: str | None = None) -> Self:
        """Load config from YAML file.

        See `resolve_config_path` for more details.

        Args:
            config_path: Path to the config file.

        Returns:
            AppConfig: The loaded config.
        """
        service = AppConfigService(
            app_config_cls=cls,
            path_resolver=resolve_app_config_path,
            loader=AppConfigLoader(),
        )
        return service.load(config_path)

    @classmethod
    def resolve_env_variables(cls, config: Any) -> Any:
        return AppConfigLoader().resolve_env_variables(config)

    def get_model_config(self, name: str) -> ModelConfig | None:
        """Get the model config by name.

        Args:
            name: The name of the model to get the config for.

        Returns:
            The model config if found, otherwise None.
        """
        return next((model for model in self.models if model.name == name), None)

    def get_tool_config(self, name: str) -> ToolConfig | None:
        """Get the tool config by name.

        Args:
            name: The name of the tool to get the config for.

        Returns:
            The tool config if found, otherwise None.
        """
        return next((tool for tool in self.tools if tool.name == name), None)

    def get_tool_group_config(self, name: str) -> ToolGroupConfig | None:
        """Get the tool group config by name.

        Args:
            name: The name of the tool group to get the config for.

        Returns:
            The tool group config if found, otherwise None.
        """
        return next((group for group in self.tool_groups if group.name == name), None)


_app_config: AppConfig | None = None
_app_config_service = AppConfigService(
    app_config_cls=AppConfig,
    path_resolver=resolve_app_config_path,
)


def get_app_config() -> AppConfig:
    """Get the OctoAgent config instance.

    Returns a cached singleton instance. Use `reload_app_config()` to reload
    from file, or `reset_app_config()` to clear the cache.
    """
    global _app_config
    config = _app_config_service.get()
    _app_config = config
    return config


def reload_app_config(config_path: str | None = None) -> AppConfig:
    """Reload the config from file and update the cached instance.

    This is useful when the config file has been modified and you want
    to pick up the changes without restarting the application.

    Args:
        config_path: Optional path to config file. If not provided,
                     uses the default resolution strategy.

    Returns:
        The newly loaded AppConfig instance.
    """
    global _app_config
    _app_config = _app_config_service.reload(config_path)
    return _app_config


def reset_app_config() -> None:
    """Reset the cached config instance.

    This clears the singleton cache, causing the next call to
    `get_app_config()` to reload from file. Useful for testing
    or when switching between different configurations.
    """
    global _app_config
    _app_config_service.reset()
    _app_config = None


def set_app_config(config: AppConfig) -> None:
    """Set a custom config instance.

    This allows injecting a custom or mock config for testing purposes.

    Args:
        config: The AppConfig instance to use.
    """
    global _app_config
    _app_config_service.set(config)
    _app_config = config
