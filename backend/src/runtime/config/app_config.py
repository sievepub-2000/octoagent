# Merged: app_config.py = app_config + app_config_loader + app_config_paths + app_config_service.
# Previously split into 4 files; consolidated 2026-05-13. Stub files retained as
# thin re-export shims for backward compatibility (no known external importers).
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Self

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from src.runtime.config.checkpointer_config import CheckpointerConfig, load_checkpointer_config_from_dict
from src.runtime.config.embedded_model_config import load_embedded_model_config_from_dict
from src.runtime.config.extensions_config import ExtensionsConfig
from src.runtime.config.integrations_config import load_integrations_config_from_dict
from src.runtime.config.memory_config import load_memory_config_from_dict
from src.runtime.config.model_config import ModelConfig
from src.runtime.config.sandbox_config import SandboxConfig
from src.runtime.config.skills_config import SkillsConfig
from src.runtime.config.subagents_config import load_subagents_config_from_dict
from src.runtime.config.summarization_config import load_summarization_config_from_dict
from src.runtime.config.system_guard_config import load_system_guard_config_from_dict
from src.runtime.config.title_config import load_title_config_from_dict
from src.runtime.config.tool_config import ToolConfig, ToolGroupConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths & dotenv (previously app_config_paths.py)
# ---------------------------------------------------------------------------


def load_project_dotenv() -> None:
    module_path = Path(__file__).resolve()
    search_paths = [
        module_path.parents[3] / ".env",
        Path.cwd() / ".env",
        Path.cwd().parent / ".env",
        module_path.parents[4] / ".env",
    ]
    loaded: set[Path] = set()
    for dotenv_path in search_paths:
        resolved_path = dotenv_path.resolve()
        if resolved_path not in loaded and resolved_path.exists():
            load_dotenv(dotenv_path=dotenv_path, override=True)
            loaded.add(resolved_path)


def resolve_app_config_path(config_path: str | None = None) -> Path:
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file specified by param `config_path` not found at {path}")
        return path

    env_path = os.getenv("OCTO_AGENT_CONFIG_PATH")
    if env_path:
        path = Path(env_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file specified by environment variable `OCTO_AGENT_CONFIG_PATH` not found at {path}")
        return path

    # Preferred location (since 2026-05-27): runtime/config/config.yaml
    runtime_config_path = Path("runtime/config/config.yaml")
    if runtime_config_path.exists():
        return runtime_config_path

    parent_runtime_config_path = Path.cwd().parent / "runtime" / "config" / "config.yaml"
    if parent_runtime_config_path.exists():
        return parent_runtime_config_path

    # Back-compat fallbacks (deprecated but kept for in-flight clones).
    cwd_path = Path.cwd() / "config.yaml"
    if cwd_path.exists():
        return cwd_path

    parent_path = Path.cwd().parent / "config.yaml"
    if parent_path.exists():
        return parent_path

    raise FileNotFoundError("`config.yaml` file not found at runtime/config/config.yaml, the current directory, nor its parent directory")


load_project_dotenv()


# ---------------------------------------------------------------------------
# Loader (previously app_config_loader.py)
# ---------------------------------------------------------------------------


SUBCONFIG_LOADERS = {
    "title": load_title_config_from_dict,
    "summarization": load_summarization_config_from_dict,
    "memory": load_memory_config_from_dict,
    "integrations": load_integrations_config_from_dict,
    "embedded_model": load_embedded_model_config_from_dict,
    "subagents": load_subagents_config_from_dict,
    "system_guard": load_system_guard_config_from_dict,
    "checkpointer": load_checkpointer_config_from_dict,
}


class AppConfigLoader:
    def __init__(self, *, extensions_loader=ExtensionsConfig.from_file):
        self._extensions_loader = extensions_loader

    def read_yaml(self, path) -> dict[str, Any]:
        with open(path, encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, dict):
            raise ValueError("App config root must be a mapping")
        return loaded

    def resolve_env_variables(self, config: Any) -> Any:
        if isinstance(config, str):
            if config.startswith("$"):
                env_value = os.getenv(config[1:])
                if env_value is None:
                    raise ValueError(f"Environment variable {config[1:]} not found for config value {config}")
                return env_value
            return config
        if isinstance(config, dict):
            return {key: self.resolve_env_variables(value) for key, value in config.items()}
        if isinstance(config, list):
            return [self.resolve_env_variables(item) for item in config]
        return config

    def resolve_config_data(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        from src.runtime.config.model_auto_inference import auto_infer_model_fields

        raw_models = list(raw_config.get("models") or [])
        config_without_models = {key: value for key, value in raw_config.items() if key != "models"}
        config_data = self.resolve_env_variables(config_without_models)

        resolved_models: list[dict[str, Any]] = []
        for raw_model in raw_models:
            try:
                resolved = self.resolve_env_variables(raw_model)
                auto_infer_model_fields(resolved)
                resolved_models.append(resolved)
            except ValueError as exc:
                model_name = raw_model.get("name", "<unknown>") if isinstance(raw_model, dict) else "<unknown>"
                logger.warning(
                    "Skipping model '%s' due to unresolved environment variable: %s",
                    model_name,
                    exc,
                )
        config_data["models"] = resolved_models
        return config_data

    def load_subconfigs(self, config_data: dict[str, Any]) -> None:
        for section, loader in SUBCONFIG_LOADERS.items():
            if section in config_data:
                loader(config_data[section])

    def load_extensions(self) -> dict[str, Any]:
        return self._extensions_loader().model_dump()


# ---------------------------------------------------------------------------
# Service (previously app_config_service.py)
# ---------------------------------------------------------------------------


class AppConfigService:
    def __init__(self, *, app_config_cls, path_resolver, loader: AppConfigLoader | None = None):
        self._app_config_cls = app_config_cls
        self._path_resolver = path_resolver
        self._loader = loader or AppConfigLoader()
        self._cached = None

    def load(self, config_path: str | None = None):
        resolved_path = self._path_resolver(config_path)
        raw_config = self._loader.read_yaml(resolved_path)
        config_data = self._loader.resolve_config_data(raw_config)
        self._loader.load_subconfigs(config_data)
        config_data["extensions"] = self._loader.load_extensions()
        return self._app_config_cls.model_validate(config_data)

    def get(self):
        if self._cached is None:
            self._cached = self.load()
        return self._cached

    def reload(self, config_path: str | None = None):
        self._cached = self.load(config_path)
        return self._cached

    def reset(self) -> None:
        self._cached = None

    def set(self, config) -> None:
        self._cached = config


# ---------------------------------------------------------------------------
# AppConfig (previously app_config.py)
# ---------------------------------------------------------------------------


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
        """Load config from YAML file."""
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
        return next((model for model in self.models if model.name == name), None)

    def get_tool_config(self, name: str) -> ToolConfig | None:
        return next((tool for tool in self.tools if tool.name == name), None)

    def get_tool_group_config(self, name: str) -> ToolGroupConfig | None:
        return next((group for group in self.tool_groups if group.name == name), None)


_app_config: AppConfig | None = None
_app_config_service = AppConfigService(
    app_config_cls=AppConfig,
    path_resolver=resolve_app_config_path,
)


def get_app_config() -> AppConfig:
    """Get the OctoAgent config instance (cached singleton)."""
    global _app_config
    config = _app_config_service.get()
    _app_config = config
    return config


def reload_app_config(config_path: str | None = None) -> AppConfig:
    """Reload the config from file and update the cached instance."""
    global _app_config
    _app_config = _app_config_service.reload(config_path)
    return _app_config


def reset_app_config() -> None:
    """Reset the cached config instance."""
    global _app_config
    _app_config_service.reset()
    _app_config = None


def set_app_config(config: AppConfig) -> None:
    """Set a custom config instance (for testing)."""
    global _app_config
    _app_config_service.set(config)
    _app_config = config
