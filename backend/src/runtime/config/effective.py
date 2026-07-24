"""Runtime configuration services shared by gateway routers and startup."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from src.utils.json_atomic import write_json_atomic

logger = logging.getLogger(__name__)

RUNTIME_CONFIG_DIR_ENV = "OCTOAGENT_RUNTIME_CONFIG_DIR"


def runtime_config_dir() -> Path:
    configured = os.getenv(RUNTIME_CONFIG_DIR_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path("runtime")


def runtime_state_path(*parts: str, env_var: str | None = None) -> Path:
    """Resolve a runtime-owned path under the configured runtime directory."""
    if env_var:
        configured = os.getenv(env_var)
        if configured:
            return Path(configured).expanduser()
    return runtime_config_dir().joinpath(*parts)


class RuntimeJsonStore:
    """Small JSON store for runtime state files.

    The interface is intentionally tiny: callers provide a default payload and
    keep their domain validation local, while path resolution, corruption
    quarantine, and atomic writes are centralized here.
    """

    def __init__(self, path: Path, default_payload: dict[str, Any]) -> None:
        self.path = path
        self.default_payload = default_payload

    def read(self) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            return dict(self.default_payload)
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
            if not raw:
                return dict(self.default_payload)
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            backup = self.path.with_suffix(self.path.suffix + ".corrupted")
            self.path.replace(backup)
            logger.warning("Quarantined corrupt runtime JSON %s -> %s", self.path, backup)
        except OSError as exc:
            logger.warning("Failed to read runtime JSON %s: %s", self.path, exc)
        return dict(self.default_payload)

    def write(self, payload: dict[str, Any]) -> None:
        write_json_atomic(self.path, payload, indent=2)
