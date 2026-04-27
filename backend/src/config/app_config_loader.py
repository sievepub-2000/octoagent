from __future__ import annotations

import logging
import os
from typing import Any

import yaml

from src.config.checkpointer_config import load_checkpointer_config_from_dict
from src.config.embedded_model_config import load_embedded_model_config_from_dict
from src.config.extensions_config import ExtensionsConfig
from src.config.integrations_config import load_integrations_config_from_dict
from src.config.memory_config import load_memory_config_from_dict
from src.config.subagents_config import load_subagents_config_from_dict
from src.config.summarization_config import load_summarization_config_from_dict
from src.config.system_guard_config import load_system_guard_config_from_dict
from src.config.title_config import load_title_config_from_dict

logger = logging.getLogger(__name__)


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
                    raise ValueError(
                        f"Environment variable {config[1:]} not found for config value {config}"
                    )
                return env_value
            return config
        if isinstance(config, dict):
            return {key: self.resolve_env_variables(value) for key, value in config.items()}
        if isinstance(config, list):
            return [self.resolve_env_variables(item) for item in config]
        return config

    def resolve_config_data(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        from src.config.free_claude_code_fallback import auto_inject_free_fallback_models
        from src.config.model_auto_inference import auto_infer_model_fields

        raw_models = list(raw_config.get("models") or [])
        raw_models = auto_inject_free_fallback_models(raw_models)
        config_without_models = {
            key: value for key, value in raw_config.items() if key != "models"
        }
        config_data = self.resolve_env_variables(config_without_models)

        resolved_models: list[dict[str, Any]] = []
        for raw_model in raw_models:
            try:
                resolved = self.resolve_env_variables(raw_model)
                auto_infer_model_fields(resolved)
                resolved_models.append(resolved)
            except ValueError as exc:
                model_name = (
                    raw_model.get("name", "<unknown>")
                    if isinstance(raw_model, dict)
                    else "<unknown>"
                )
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
