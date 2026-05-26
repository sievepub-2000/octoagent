"""BM25 retrieval backend over text rows (Sprint-2 P0).

Lightweight in-memory BM25 wrapper using ``rank-bm25``. Designed for tables
whose row count is modest (≤ 50k) — the index is rebuilt lazily per query
call. For heavy use, the caller can cache a ``BM25Index`` and call ``query()``
many times.

The tokenizer is intentionally simple (lowercase, word characters) so it
matches the cosine path's vocabulary normalisation without needing language
heuristics.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@dataclass
class BM25Index:
    """Pre-built BM25 index over a sequence of documents."""

    doc_ids: list[str]
    documents: list[str]
    _bm25: BM25Okapi = field(init=False)

    def __post_init__(self) -> None:
        corpus = [_tokenize(d) for d in self.documents] or [[""]]
        self._bm25 = BM25Okapi(corpus)

    def query(self, q: str, top_k: int = 20) -> list[tuple[str, float]]:
        """Return ``[(doc_id, score), ...]`` sorted descending."""
        if not self.documents:
            return []
        tokens = _tokenize(q)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(zip(self.doc_ids, scores), key=lambda kv: kv[1], reverse=True)
        return [(d, float(s)) for d, s in ranked[:top_k] if s > 0.0]


def bm25_search(doc_ids: Sequence[str], documents: Sequence[str], query: str, *, top_k: int = 20) -> list[tuple[str, float]]:
    """Convenience wrapper: build an index and query it once."""
    if len(doc_ids) != len(documents):
        raise ValueError("doc_ids and documents must align")
    idx = BM25Index(doc_ids=list(doc_ids), documents=list(documents))
    return idx.query(query, top_k=top_k)


__all__ = ["BM25Index", "bm25_search", "_tokenize"]
