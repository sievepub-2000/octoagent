"""Lazy-loaded text embedding service for memory and intent recognition.

Loads sentence-transformers only when first used.  Falls back to a TF-IDF
based similarity approach when the model is unavailable so downstream code
does not need to know whether embeddings are real or approximate.

This module lives under ``src.agents.memory`` to avoid colliding with the
existing ``src.models.embedding_service`` (the main backend embedding
service used by RAG, goal middleware, etc.).
"""

from __future__ import annotations

import logging
import math
import re
import threading
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Singleton guard
# ---------------------------------------------------------------------------

_instance: TextEmbeddingService | None = None
_instance_lock = threading.Lock()


def get_text_embedding_service() -> TextEmbeddingService:
    """Return the singleton TextEmbeddingService (lazy-created)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = TextEmbeddingService()
    return _instance


# ---------------------------------------------------------------------------
# TF-IDF fallback
# ---------------------------------------------------------------------------


class _TfidfVectorizer:
    """Minimal TF-IDF implementation for when sentence-transformers is absent."""

    def __init__(self) -> None:
        self._idf: dict[str, float] = {}
        self._doc_count = 0
        self._token_pattern = re.compile(r"[a-zA-Z]\w+")

    def _tokenize(self, text: str) -> list[str]:
        return [t.lower() for t in self._token_pattern.findall(text)]

    def fit(self, texts: list[str]) -> _TfidfVectorizer:
        doc_freq: Counter = Counter()
        for text in texts:
            tokens = set(self._tokenize(text))
            for token in tokens:
                doc_freq[token] += 1
        n_docs = len(texts)
        self._idf = {token: math.log((n_docs + 1) / (freq + 1)) + 1 for token, freq in doc_freq.items()}
        self._doc_count = n_docs
        return self

    def transform(self, texts: list[str]) -> list[list[float]]:
        if not self._idf:
            return [[0.0] * 64 for _ in texts]
        max_dim = max(len(self._idf), 64)
        results: list[list[float]] = []
        for text in texts:
            tokens = Counter(self._tokenize(text))
            total = sum(tokens.values()) or 1
            vec = [0.0] * max_dim
            for token, count in tokens.items():
                idx = hash(token) % max_dim
                vec[idx] += (count / total) * self._idf.get(token, 1.0)
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            results.append([v / norm for v in vec])
        return results

    def transform_single(self, text: str) -> list[float]:
        return self.transform([text])[0]


# ---------------------------------------------------------------------------
# EmbeddingService
# ---------------------------------------------------------------------------


class TextEmbeddingService:
    """Lazy-loaded text embedding service.

    On first call to encode/encode_batch the sentence-transformers model is
    loaded (cached in-process).  If sentence-transformers is not installed
    or the load fails, a TF-IDF fallback produces approximate vectors of
    fixed dimension so downstream similarity code keeps working.
    """

    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    FALLBACK_DIM = 64
    COSINE_THRESHOLD = 0.7

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or self.DEFAULT_MODEL
        self._model: Any = None
        self._tokenizer: Any = None
        self._loaded = False
        self._lock = threading.Lock()
        self._tfidf: _TfidfVectorizer | None = None

    # ------------------------------------------------------------------ load

    def _ensure_loaded(self) -> bool:
        """Load the model if not already loaded. Returns True on success."""
        if self._loaded:
            return True
        with self._lock:
            if self._loaded:
                return True
            try:
                import torch  # noqa: F401
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self._model_name)
                self._tokenizer = self._model.tokenizer
                self._loaded = True
                logger.info("EmbeddingService loaded model '%s'", self._model_name)
                return True
            except ImportError:
                logger.debug("sentence-transformers not available; using TF-IDF fallback")
                self._tfidf = _TfidfVectorizer()
                self._loaded = True
                return False
            except Exception as exc:
                logger.warning(
                    "Failed to load embedding model '%s': %s — using TF-IDF fallback",
                    self._model_name,
                    exc,
                )
                self._tfidf = _TfidfVectorizer()
                self._loaded = True
                return False

    # ------------------------------------------------------------------ encode

    def encode(self, text: str) -> list[float]:
        """Encode a single string into an embedding vector."""
        if self._ensure_loaded():
            try:
                import torch

                with torch.no_grad():
                    embedding = self._model.encode(text, convert_to_numpy=True).tolist()
                return embedding
            except Exception as exc:
                logger.warning("Model encode failed: %s — falling back to TF-IDF", exc)

        if self._tfidf is not None:
            return self._tfidf.transform_single(text)

        # Last-resort deterministic hash vector (fixed dim, no fitting needed).
        tokens = re.findall(r"\w+", text.lower())
        vec = [0.0] * self.FALLBACK_DIM
        for i, token in enumerate(tokens):
            idx = hash(token) % self.FALLBACK_DIM
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def batch_encode(self, texts: list[str]) -> list[list[float]]:
        """Encode multiple strings into embedding vectors."""
        if not texts:
            return []

        if self._ensure_loaded():
            try:
                import torch

                with torch.no_grad():
                    embeddings = self._model.encode(texts, convert_to_numpy=True).tolist()
                return embeddings
            except Exception as exc:
                logger.warning("Model batch encode failed: %s — falling back", exc)

        if self._tfidf is not None:
            if self._tfidf._doc_count == 0 and len(texts) > 1:
                self._tfidf.fit(texts)
            return self._tfidf.transform(texts)

        results: list[list[float]] = []
        for text in texts:
            results.append(self.encode(text))
        return results

    # ------------------------------------------------------------------ similarity

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b):
            min_len = min(len(a), len(b))
            a, b = a[:min_len], b[:min_len]
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
        norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (norm_a * norm_b)

    def find_best_match(self, query: str, candidates: list[str], threshold: float | None = None) -> tuple[str, float] | tuple[None, float]:
        """Find the best-matching candidate for a query string.

        Returns (best_candidate, similarity) or (None, worst_score).
        If no candidate exceeds *threshold* the first candidate is returned
        with its raw score so callers can decide.
        """
        if not candidates:
            return None, 0.0

        query_vec = self.encode(query)
        threshold = threshold if threshold is not None else self.COSINE_THRESHOLD

        best_candidate: str | None = None
        best_score = -1.0
        worst_score = 2.0

        for candidate in candidates:
            score = self.cosine_similarity(query_vec, self.encode(candidate))
            if score > best_score:
                best_score = score
                best_candidate = candidate
            if score < worst_score:
                worst_score = score

        if best_score >= threshold:
            return best_candidate, best_score
        return None, worst_score


__all__ = ["TextEmbeddingService", "get_text_embedding_service"]
