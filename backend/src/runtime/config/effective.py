"""Runtime configuration services shared by gateway routers and startup."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.utils.json_atomic import write_json_atomic

logger = logging.getLogger(__name__)

RAG_CONFIG_ENV = "OCTOAGENT_RAG_CONFIG_FILE"
RUNTIME_CONFIG_DIR_ENV = "OCTOAGENT_RUNTIME_CONFIG_DIR"
RAG_CONFIG_FILENAME = "rag_config.json"

RAG_DEFAULTS: dict[str, Any] = {
    "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
    "reranker_enabled": False,
    "reranker_model": "BAAI/bge-reranker-base",
    "top_k_default": 10,
}


class RagConfig(BaseModel):
    embedding_model: str = Field(default=RAG_DEFAULTS["embedding_model"])
    reranker_enabled: bool = Field(default=RAG_DEFAULTS["reranker_enabled"])
    reranker_model: str = Field(default=RAG_DEFAULTS["reranker_model"])
    top_k_default: int = Field(default=RAG_DEFAULTS["top_k_default"], ge=1, le=100)


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


def rag_config_path() -> Path:
    configured = os.getenv(RAG_CONFIG_ENV)
    if configured:
        return Path(configured).expanduser()
    return runtime_config_dir() / RAG_CONFIG_FILENAME


def load_rag_config(path: Path | None = None) -> RagConfig:
    config_path = path or rag_config_path()
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return RagConfig(**{**RAG_DEFAULTS, **data})
        except Exception as exc:
            logger.warning("Failed to load %s: %s; using defaults", config_path, exc)
    return RagConfig(**RAG_DEFAULTS)


def save_rag_config(cfg: RagConfig, path: Path | None = None) -> None:
    write_json_atomic(path or rag_config_path(), cfg.model_dump(), indent=2)


def apply_rag_config(cfg: RagConfig) -> None:
    os.environ["OCTOAGENT_EMBEDDING_MODEL"] = cfg.embedding_model
    os.environ["OCTOAGENT_RERANKER_MODEL"] = cfg.reranker_model
    os.environ["OCTOAGENT_RERANKER_ENABLED"] = "1" if cfg.reranker_enabled else "0"

    try:
        from src.models.embedding_service import reset_embedding_service
        from src.models.reranker_service import reset_reranker_service

        reset_embedding_service()
        reset_reranker_service()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to reset RAG service singletons: %s", exc)


def initialize_runtime_config() -> RagConfig:
    cfg = load_rag_config()
    apply_rag_config(cfg)
    return cfg


def model_cache_status(model_name: str) -> dict[str, Any]:
    """Inspect ``~/.cache/huggingface/hub`` for the given model."""
    hf_home = os.environ.get("HF_HOME")
    hub = Path(hf_home).expanduser() / "hub" if hf_home else Path.home() / ".cache" / "huggingface" / "hub"
    slug = "models--" + model_name.replace("/", "--")
    cache_dir = hub / slug
    snapshots_dir = cache_dir / "snapshots"
    if not snapshots_dir.exists():
        return {"cached": False, "size_bytes": 0, "path": None}
    total = 0
    for item in cache_dir.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    snaps = [path for path in snapshots_dir.iterdir() if path.is_dir()]
    latest = max(snaps, key=lambda path: path.stat().st_mtime) if snaps else None
    return {"cached": bool(snaps), "size_bytes": total, "path": str(latest) if latest else None}
