"""Unified embedding service — provides neural embeddings for the vector stores.

Supports multiple backends:
  - sentence-transformers (preferred, high-quality)
  - llama.cpp (via bootstrap runtime, lighter memory footprint)
  - SHA-256 fallback (deterministic, zero semantic meaning)

The service auto-detects the best available backend on first call.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from functools import lru_cache

logger = logging.getLogger(__name__)

# Default model for sentence-transformers — compact, multilingual, 384-dim, Apache-2
_DEFAULT_ST_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Dimension produced by each backend
_DIM_MINILM = 384
_DIM_FALLBACK = 64


class EmbeddingBackend(ABC):
    """Abstract embedding provider."""

    @property
    @abstractmethod
    def dim(self) -> int: ...

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class SentenceTransformerBackend(EmbeddingBackend):
    """sentence-transformers library (best quality)."""

    def __init__(self, model_name: str = _DEFAULT_ST_MODEL) -> None:
        import os
        from pathlib import Path

        # Check if model is already cached locally; skip download attempt
        st_home = os.environ.get("SENTENCE_TRANSFORMERS_HOME")
        hf_home = os.environ.get("HF_HOME")
        cache_root = (
            Path(st_home).expanduser()
            if st_home
            else Path.home() / ".cache" / "torch" / "sentence_transformers"
        )
        hub_cache = (
            Path(hf_home).expanduser() / "hub"
            if hf_home
            else Path.home() / ".cache" / "huggingface" / "hub"
        )
        model_slug = model_name.replace("/", "_")
        hub_slug = "models--" + model_name.replace("/", "--")

        local_hit = (
            (cache_root / model_slug).exists()
            or (hub_cache / hub_slug).exists()
        )
        if not local_hit:
            raise RuntimeError(
                f"Model {model_name} not cached locally; "
                "skipping to avoid network download hang"
            )

        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        logger.info("Loading sentence-transformers model: %s", model_name)
        self._model = SentenceTransformer(model_name)
        self._dim = self._model.get_sentence_embedding_dimension() or _DIM_MINILM

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        embeddings = self._model.encode(list(texts), show_progress_bar=False)
        return [e.tolist() for e in embeddings]


class LlamaCppBackend(EmbeddingBackend):
    """llama.cpp via bootstrap runtime (lower memory, slower)."""

    def __init__(self) -> None:
        from src.bootstrap.runtime import BootstrapRuntime

        self._runtime = BootstrapRuntime()
        # Dimension depends on the loaded model; detect lazily
        self._dim: int | None = None

    @property
    def dim(self) -> int:
        if self._dim is None:
            sample = self._runtime.embed_text("test")
            self._dim = len(sample)
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._runtime.embed_text(t) for t in texts]


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

        # Try llama.cpp
        try:
            return LlamaCppBackend()
        except Exception:
            logger.info("llama.cpp not available, using SHA-256 fallback")

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
