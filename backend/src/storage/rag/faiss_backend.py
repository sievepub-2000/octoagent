"""Optional FAISS local-index search for unified RAG rows."""

from __future__ import annotations

import importlib
import json
import logging
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

VectorRow = tuple[Any, ...]


def _optional_modules() -> tuple[Any | None, Any | None]:
    try:
        numpy = importlib.import_module("numpy")
        faiss = importlib.import_module("faiss")
    except Exception:
        return None, None
    return numpy, faiss


def search_rows(
    rows: Sequence[VectorRow],
    *,
    query_embedding: list[float],
    top_k: int,
) -> list[tuple[VectorRow, float]] | None:
    """Search DuckDB vector rows through an in-process FAISS index.

    Returns ``None`` when FAISS/numpy is unavailable or FAISS fails, allowing
    callers to keep the existing DuckDB/Python fallback chain. An empty list is
    a valid search result when FAISS is available but no row is searchable.
    """
    if top_k <= 0:
        return []
    if not query_embedding:
        return []

    numpy, faiss = _optional_modules()
    if numpy is None or faiss is None:
        return None

    expected_dim = len(query_embedding)
    vectors: list[list[float]] = []
    payloads: list[VectorRow] = []

    for row in rows:
        try:
            raw_embedding = row[4]
            embedding = json.loads(raw_embedding) if isinstance(raw_embedding, str) else raw_embedding
            if not isinstance(embedding, list) or len(embedding) != expected_dim:
                continue
            vectors.append([float(value) for value in embedding])
            payloads.append(row)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    if not vectors:
        return []

    try:
        matrix = numpy.asarray(vectors, dtype="float32")
        query = numpy.asarray([query_embedding], dtype="float32")
        faiss.normalize_L2(matrix)
        faiss.normalize_L2(query)
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        scores, indices = index.search(query, min(int(top_k), len(payloads)))
    except Exception:
        logger.debug("FAISS local RAG search failed", exc_info=True)
        return None

    results: list[tuple[VectorRow, float]] = []
    for score, row_index in zip(scores[0], indices[0], strict=False):
        idx = int(row_index)
        if idx < 0 or idx >= len(payloads):
            continue
        results.append((payloads[idx], float(score)))
    return results
