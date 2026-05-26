"""Cross-Encoder reranker service for second-stage RAG reranking.

Loads `sentence_transformers.CrossEncoder` lazily from the local HF cache.
Configuration via env vars (also overridable from runtime config router):
  - OCTOAGENT_RERANKER_ENABLED: "1" to enable, anything else disabled
  - OCTOAGENT_RERANKER_MODEL:   model name, default ``BAAI/bge-reranker-base``

Disabled by default. If enabled but the model is not cached locally, the
service silently degrades to a no-op (returns input order). This keeps
hybrid retrieval safe even when admins forget to pre-download the model.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_RERANKER_MODEL = os.getenv(
    "OCTOAGENT_RERANKER_MODEL",
    "BAAI/bge-reranker-base",
)


def _is_enabled() -> bool:
    return os.getenv("OCTOAGENT_RERANKER_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _latest_hf_snapshot(model_cache: Path) -> Path | None:
    snapshots = model_cache / "snapshots"
    if not snapshots.exists():
        return None
    cands = [p for p in snapshots.iterdir() if p.is_dir()]
    if not cands:
        return None
    return max(cands, key=lambda x: x.stat().st_mtime)


def _resolve_local_path(model_name: str) -> Path | None:
    hf_home = os.environ.get("HF_HOME")
    hub_cache = Path(hf_home).expanduser() / "hub" if hf_home else Path.home() / ".cache" / "huggingface" / "hub"
    hub_slug = "models--" + model_name.replace("/", "--")
    return _latest_hf_snapshot(hub_cache / hub_slug)


class RerankerService:
    """Lazy-loaded CrossEncoder wrapper with graceful degradation."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or _DEFAULT_RERANKER_MODEL
        self._model = None
        self._load_failed = False

    def _try_load(self) -> bool:
        if self._model is not None:
            return True
        if self._load_failed:
            return False
        local = _resolve_local_path(self.model_name)
        if local is None:
            logger.info(
                "Reranker model %s not in local cache; staying disabled",
                self.model_name,
            )
            self._load_failed = True
            return False
        try:
            from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]

            logger.info("Loading reranker from %s", local)
            self._model = CrossEncoder(str(local))
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Reranker load failed: %s", exc)
            self._load_failed = True
            return False

    @property
    def available(self) -> bool:
        return self._try_load()

    @property
    def status(self) -> dict:
        local = _resolve_local_path(self.model_name)
        return {
            "model": self.model_name,
            "enabled_env": _is_enabled(),
            "cached_locally": local is not None,
            "local_path": str(local) if local else None,
            "loaded": self._model is not None,
        }

    def rerank(
        self,
        query: str,
        candidates: list[tuple[str, str]],
        top_k: int | None = None,
    ) -> list[tuple[str, float]]:
        """Rerank ``[(doc_id, text), ...]``; returns sorted ``[(doc_id, score), ...]``.

        If the model cannot be loaded, returns input order with score=0.0 so the
        caller can still merge with vector/BM25 results unchanged.
        """
        if not candidates:
            return []
        if not self._try_load() or self._model is None:
            return [(doc_id, 0.0) for doc_id, _ in candidates]
        pairs = [(query, text) for _, text in candidates]
        scores = self._model.predict(pairs, show_progress_bar=False)
        ranked = sorted(
            ((doc_id, float(s)) for (doc_id, _), s in zip(candidates, scores, strict=False)),
            key=lambda kv: kv[1],
            reverse=True,
        )
        if top_k is not None:
            ranked = ranked[:top_k]
        return ranked


@lru_cache(maxsize=1)
def get_reranker_service() -> RerankerService:
    """Singleton accessor."""
    return RerankerService()


def reset_reranker_service() -> None:
    """Clear cache so a config change picks up a new model on next call."""
    get_reranker_service.cache_clear()


def reranker_enabled() -> bool:
    """Whether reranking should run for this request."""
    return _is_enabled() and get_reranker_service().available
