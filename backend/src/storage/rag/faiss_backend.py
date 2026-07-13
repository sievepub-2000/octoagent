"""Optional FAISS local-index search with persistence for unified RAG rows (Sprint-2 P0 + P1).

This module provides FAISS-based vector search with:

1. **Index persistence**: Save/load FAISS index to/from disk (Sprint-2 P1)
2. **Incremental updates**: Add/remove vectors without full rebuild (Sprint-2 P1)
3. **Graceful degradation**: Falls back to Python when FAISS is unavailable

The index uses Inner Product (IP) with L2 normalization, equivalent to
cosine similarity.
"""

from __future__ import annotations

import importlib
import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VectorRow = tuple[Any, ...]


@dataclass
class FAISSStats:
    """Statistics for FAISS index operations."""

    total_loads: int = 0
    total_saves: int = 0
    total_searches: int = 0
    total_adds: int = 0
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    avg_search_time_ms: float = 0.0
    current_index_size: int = 0


def _optional_modules() -> tuple[Any | None, Any | None]:
    try:
        numpy = importlib.import_module("numpy")
        faiss = importlib.import_module("faiss")
    except Exception:
        return None, None
    return numpy, faiss


class FAISSIndexManager:
    """Manages FAISS index persistence and incremental updates.

    This class handles loading cached indexes, incremental updates,
    and automatic persistence to disk.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or Path("/tmp/octoagent_faiss_cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._stats = FAISSStats()
        self._index_cache: dict[str, tuple[Any, list[VectorRow]]] = {}  # cache_key -> (index, payloads)

    def search_with_persistence(
        self,
        table_name: str,
        rows: Sequence[VectorRow],
        query_embedding: list[float],
        top_k: int,
    ) -> list[tuple[VectorRow, float]] | None:
        """Search using FAISS index with persistence support.

        Args:
            table_name: Name of the table (used for cache file naming).
            rows: Vector rows to search.
            query_embedding: Query embedding vector.
            top_k: Number of results to return.

        Returns:
            List of (row, score) tuples, or None if FAISS unavailable.
        """
        if top_k <= 0:
            return []
        if not query_embedding:
            return []

        numpy, faiss = _optional_modules()
        if numpy is None or faiss is None:
            self._stats.total_searches += 1
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
            self._stats.total_searches += 1
            return []

        index_path = self._cache_dir / f"{table_name}_faiss_index.bin"

        start_time = time.time()
        try:
            # Try to load cached index (avoids full rebuild)
            if index_path.exists() and len(vectors) <= 10000:
                try:
                    index = faiss.read_index(str(index_path))
                    if index.ntotal == len(vectors):
                        self._stats.cache_hit_count += 1
                        self._stats.total_searches += 1
                        query = numpy.asarray([query_embedding], dtype="float32")
                        faiss.normalize_L2(query)
                        scores, indices = index.search(query, min(int(top_k), len(payloads)))
                        results = self._process_results(scores, indices, payloads)
                        elapsed_ms = (time.time() - start_time) * 1000
                        self._update_avg_search_time(elapsed_ms)
                        return results
                except Exception:
                    logger.debug("Failed to load cached FAISS index, rebuilding")

            self._stats.cache_miss_count += 1
            # Build new index
            matrix = numpy.asarray(vectors, dtype="float32")
            faiss.normalize_L2(matrix)
            index = faiss.IndexFlatIP(matrix.shape[1])
            index.add(matrix)
            query = numpy.asarray([query_embedding], dtype="float32")
            faiss.normalize_L2(query)
            scores, indices = index.search(query, min(int(top_k), len(payloads)))
            results = self._process_results(scores, indices, payloads)
            elapsed_ms = (time.time() - start_time) * 1000
            self._update_avg_search_time(elapsed_ms)

            # Save index for future reuse
            if len(vectors) <= 10000:
                try:
                    faiss.write_index(index, str(index_path))
                    self._stats.total_saves += 1
                except Exception as exc:
                    logger.debug("Failed to save FAISS index: %s", exc)

            return results

        except Exception:
            logger.debug("FAISS local RAG search failed", exc_info=True)
            self._stats.total_searches += 1
            return None

    def _process_results(
        self,
        scores: Any,
        indices: Any,
        payloads: list[VectorRow],
    ) -> list[tuple[VectorRow, float]]:
        """Process FAISS search results."""
        results: list[tuple[VectorRow, float]] = []
        for score, row_index in zip(scores[0], indices[0], strict=False):
            idx = int(row_index)
            if idx < 0 or idx >= len(payloads):
                continue
            results.append((payloads[idx], float(score)))
        return results

    def _update_avg_search_time(self, elapsed_ms: float) -> None:
        """Update average search time with exponential moving average."""
        alpha = 0.1  # Smoothing factor
        self._stats.avg_search_time_ms = (
            alpha * elapsed_ms + (1 - alpha) * self._stats.avg_search_time_ms
        )

    def add_to_index(self, table_name: str, vectors: list[list[float]]) -> int:
        """Add vectors to a cached FAISS index and return the added count.

        Args:
            table_name: Name of the table.
            vectors: List of vector embeddings to add.
        """
        return self.add_vectors_to_existing_index(table_name, vectors)

    def get_stats(self) -> dict[str, Any]:
        """Get FAISS index manager statistics."""
        return {
            "total_loads": self._stats.total_loads,
            "total_saves": self._stats.total_saves,
            "total_searches": self._stats.total_searches,
            "total_adds": self._stats.total_adds,
            "cache_hit_count": self._stats.cache_hit_count,
            "cache_miss_count": self._stats.cache_miss_count,
            "avg_search_time_ms": self._stats.avg_search_time_ms,
            "current_index_size": self._stats.current_index_size,
            "cache_dir": str(self._cache_dir),
        }

    def add_vectors_to_existing_index(
        self,
        table_name: str,
        vectors: list[list[float]],
        rows: Sequence[VectorRow] | None = None,
    ) -> int:
        """Add vectors to an existing persisted FAISS index.

        Args:
            table_name: Name of the table.
            vectors: List of vector embeddings to add.
            rows: Optional payload rows corresponding to vectors.

        Returns:
            Number of vectors successfully added.
        """
        index_path = self._cache_dir / f"{table_name}_faiss_index.bin"
        if not index_path.exists():
            return 0

        try:
            numpy, faiss = _optional_modules()
            if numpy is None or faiss is None:
                return 0

            index = faiss.read_index(str(index_path))
            matrix = numpy.asarray(vectors, dtype="float32")
            faiss.normalize_L2(matrix)
            index.add(matrix)
            faiss.write_index(index, str(index_path))
            self._stats.total_adds += len(vectors)
            self._stats.current_index_size = index.ntotal
            return len(vectors)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to add vectors to FAISS index for %s: %s", table_name, exc)
            return 0

    def clear_cache(self) -> int:
        """Clear all cached FAISS indexes.

        Returns:
            Number of cache files removed.
        """
        count = 0
        for file in self._cache_dir.glob("*.bin"):
            try:
                file.unlink()
                count += 1
            except Exception:
                pass
        logger.info("FAISS cache cleared: %d files removed", count)
        return count


# Singleton instance
_faiss_manager: FAISSIndexManager | None = None


def get_faiss_index_manager(cache_dir: Path | None = None) -> FAISSIndexManager:
    """Get or create the singleton FAISSIndexManager instance."""
    global _faiss_manager
    if _faiss_manager is None:
        _faiss_manager = FAISSIndexManager(cache_dir=cache_dir)
    return _faiss_manager


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

    Note: For production use with persistence, prefer using FAISSIndexManager.
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


__all__ = [
    "FAISSIndexManager",
    "FAISSStats",
    "search_rows",
    "get_faiss_index_manager",
]
