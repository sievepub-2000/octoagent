"""Provider resolution for system execution backends."""

from __future__ import annotations

from src.runtime.config.integrations_config import get_integrations_config

from .providers import (
    LocalDesktopSystemExecutionProvider,
    NoneSystemExecutionProvider,
)


def get_system_execution_provider():
    cfg = get_integrations_config().system_execution
    if cfg.engine == "desktop_agent":
        return LocalDesktopSystemExecutionProvider()
    return NoneSystemExecutionProvider()
