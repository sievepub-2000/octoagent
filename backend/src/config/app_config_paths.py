from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_project_dotenv() -> None:
    search_paths = [
        Path.cwd() / ".env",
        Path.cwd().parent / ".env",
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[3] / ".env",
    ]

    for dotenv_path in search_paths:
        if dotenv_path.exists():
            load_dotenv(dotenv_path=dotenv_path, override=False)
            break


def resolve_app_config_path(config_path: str | None = None) -> Path:
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Config file specified by param `config_path` not found at {path}"
            )
        return path

    env_path = os.getenv("OCTO_AGENT_CONFIG_PATH")
    if env_path:
        path = Path(env_path)
        if not path.exists():
            raise FileNotFoundError(
                "Config file specified by environment variable "
                f"`OCTO_AGENT_CONFIG_PATH` not found at {path}"
            )
        return path

    cwd_path = Path.cwd() / "config.yaml"
    if cwd_path.exists():
        return cwd_path

    parent_path = Path.cwd().parent / "config.yaml"
    if parent_path.exists():
        return parent_path

    raise FileNotFoundError(
        "`config.yaml` file not found at the current directory nor its parent directory"
    )
