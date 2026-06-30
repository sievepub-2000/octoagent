"""Unified embedding service."""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_ST_MODEL = os.getenv(
    "OCTOAGENT_EMBEDDING_MODEL",
    "Qwen/Qwen3-Embedding-0.6B",
)

_DIM_MINILM = 384
_DIM_FALLBACK = 64


class EmbeddingBackend(ABC):
    @property
    @abstractmethod
    def dim(self) -> int: ...

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class SentenceTransformerBackend(EmbeddingBackend):
    def __init__(self, model_name: str = _DEFAULT_ST_MODEL) -> None:
        st_home = os.environ.get("SENTENCE_TRANSFORMERS_HOME")
        hf_home = os.environ.get("HF_HOME")

        # Use HF_HOME if set, otherwise use project-local cache
        if hf_home:
            hub_cache = Path(hf_home).expanduser()
        else:
            # Fallback to project cache
            candidate_paths = [
                Path("/home/sieve-pub/public-workspace/octoagent/runtime/cache/huggingface/hub"),
                Path.home() / ".cache" / "huggingface" / "hub",
            ]
            hub_cache = next((p for p in candidate_paths if p.exists()), candidate_paths[-1])

        cache_root = Path(st_home).expanduser() if st_home else Path.home() / ".cache" / "torch" / "sentence_transformers"

        model_slug = model_name.replace("/", "_")
        hub_slug = "models--" + model_name.replace("/", "--")

        local_model_path = cache_root / model_slug
        if not local_model_path.exists():
            hub_model_path = _latest_hf_snapshot(hub_cache / hub_slug)
            if hub_model_path is not None:
                local_model_path = hub_model_path

        if not local_model_path.exists():
            raise RuntimeError(f"Model {model_name} not cached locally; skipping to avoid network download hang")

        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        logger.info("Loading sentence-transformers model from local cache: %s", local_model_path)
        trust_remote_code = model_name.startswith(("Qwen/", "jinaai/"))
        try:
            self._model = SentenceTransformer(str(local_model_path), trust_remote_code=trust_remote_code)
        except TypeError:
            self._model = SentenceTransformer(str(local_model_path))
        self._dim = self._model.get_sentence_embedding_dimension() or _DIM_MINILM

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        embeddings = self._model.encode(list(texts), show_progress_bar=False)
        return [e.tolist() for e in embeddings]


class FallbackBackend(EmbeddingBackend):
    """SHA-256 deterministic pseudo-embeddings (always available)."""

    @property
    def dim(self) -> int:
        return _DIM_FALLBACK

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_sha256_vector(t) for t in texts]


def _sha256_vector(text: str, dim: int = _DIM_FALLBACK) -> list[float]:
    """Deterministic pseudo-embedding from SHA-256 digest."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [(float(digest[i % len(digest)]) / 255.0) * 2 - 1 for i in range(dim)]


def _latest_hf_snapshot(model_cache: Path) -> Path | None:
    snapshots = model_cache / "snapshots"
    if not snapshots.exists():
        return None
    candidates = [path for path in snapshots.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


# ---------------------------------------------------------------------------
# Service singleton
# ---------------------------------------------------------------------------


class EmbeddingService:
    """Auto-detecting embedding service with graceful fallback."""

    def __init__(self) -> None:
        self._backend: EmbeddingBackend | None = None

    def _detect(self) -> EmbeddingBackend:
        # Try sentence-transformers first — but only if the package is installed
        if importlib.util.find_spec("sentence_transformers") is not None:
            try:
                return SentenceTransformerBackend()
            except Exception as exc:
                logger.warning("sentence-transformers failed to load: %s", exc)
        else:
            logger.info("sentence-transformers not installed, skipping")

        logger.info("sentence-transformers unavailable; using SHA-256 fallback")
        return FallbackBackend()

    @property
    def backend(self) -> EmbeddingBackend:
        if self._backend is None:
            self._backend = self._detect()
            logger.info(
                "EmbeddingService initialized: backend=%s, dim=%d",
                type(self._backend).__name__,
                self._backend.dim,
            )
        return self._backend

    @property
    def dim(self) -> int:
        return self.backend.dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self.backend.embed(texts)

    def embed_one(self, text: str) -> list[float]:
        return self.backend.embed_one(text)

    @property
    def backend_name(self) -> str:
        return type(self.backend).__name__


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """Get the global EmbeddingService singleton."""
    return EmbeddingService()


def reset_embedding_service() -> None:
    """Clear the cached singleton — used when runtime config changes."""
    get_embedding_service.cache_clear()
