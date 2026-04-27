from __future__ import annotations

from .app_config_loader import AppConfigLoader


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
