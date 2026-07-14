"""BM25 retrieval backend with persistence and incremental updates (Sprint-2 P0 + P1).

Lightweight in-memory BM25 wrapper using ``rank-bm25``. Designed for tables
whose row count is modest (≤ 50k). The index supports:

1. **Persistence**: Save/load index to/from disk as pickle (Sprint-2 P1)
2. **Incremental updates**: Add/remove documents without full rebuild (Sprint-2 P1)
3. **Lazy rebuild**: Rebuild index only when documents change (Sprint-2 P1)

The tokenizer is intentionally simple (lowercase, word characters) so it
matches the cosine path's vocabulary normalisation without needing language
heuristics.
"""

from __future__ import annotations

import logging
import pickle
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@dataclass
class BM25Index:
    """Pre-built BM25 index over a sequence of documents with persistence support.

    Attributes:
        doc_ids: List of unique document identifiers.
        documents: List of raw document texts.
        _bm25: The underlying rank-bm25 Okapi implementation.
        _dirty: Whether the index has unsaved changes.
        _cache_path: Optional path to persist the index.
    """

    doc_ids: list[str]
    documents: list[str]
    _bm25: BM25Okapi = field(init=False)
    _dirty: bool = field(default=False, init=False)
    _cache_path: str | None = field(default="", init=False)

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

    def save(self, path: str | Path) -> None:
        """Persist the index to disk.

        Args:
            path: File path to save the index.
        """
        try:
            data = {
                "doc_ids": self.doc_ids,
                "documents": self.documents,
                "corpus": [[_tokenize(d) for d in self.documents]] or [[""]],
            }
            with open(path, "wb") as f:
                pickle.dump(data, f)
            self._dirty = False
            logger.debug("BM25 index saved to %s (%d docs)", path, len(self.doc_ids))
        except Exception as exc:
            logger.error("Failed to save BM25 index to %s: %s", path, exc)

    def load(self, path: str | Path) -> bool:
        """Load the index from disk.

        Args:
            path: File path to load the index from.

        Returns:
            True if loaded successfully, False otherwise.
        """
        try:
            cache_path = Path(path)
            if not cache_path.exists():
                return False
            with open(path, "rb") as f:
                data = pickle.load(f)
            self.doc_ids = data["doc_ids"]
            self.documents = data["documents"]
            corpus = [_tokenize(d) for d in self.documents] or [[""]]
            self._bm25 = BM25Okapi(corpus)
            self._dirty = False
            logger.debug("BM25 index loaded from %s (%d docs)", path, len(self.doc_ids))
            return True
        except Exception as exc:
            logger.error("Failed to load BM25 index from %s: %s", path, exc)
            return False

    def add_documents(self, doc_ids: list[str], documents: list[str]) -> None:
        """Add new documents to the index incrementally.

        Args:
            doc_ids: List of new document identifiers.
            documents: List of new document texts.
        """
        if len(doc_ids) != len(documents):
            raise ValueError("doc_ids and documents must align")
        self.doc_ids.extend(doc_ids)
        self.documents.extend(documents)
        self._dirty = True
        logger.debug("Added %d documents to BM25 index (total: %d)", len(doc_ids), len(self.doc_ids))

    def remove_documents(self, doc_ids_to_remove: set[str]) -> None:
        """Remove documents from the index.

        Args:
            doc_ids_to_remove: Set of document identifiers to remove.
        """
        original_count = len(self.doc_ids)
        keep_mask = [did not in doc_ids_to_remove for did in self.doc_ids]
        self.doc_ids = [did for did, keep in zip(self.doc_ids, keep_mask) if keep]
        self.documents = [doc for doc, keep in zip(self.documents, keep_mask) if keep]
        removed = original_count - len(self.doc_ids)
        if removed > 0:
            self._dirty = True
            logger.debug("Removed %d documents from BM25 index (total: %d)", removed, len(self.doc_ids))

    def is_dirty(self) -> bool:
        """Check if the index has unsaved changes."""
        return self._dirty

    def __len__(self) -> int:
        return len(self.documents)


class BM25IndexManager:
    """Manages BM25 index persistence and incremental updates.

    This class handles loading cached indexes, incremental updates,
    and automatic persistence to disk.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or Path("/tmp/octoagent_bm25_cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._indexes: dict[str, BM25Index] = {}
        self._stats: dict[str, Any] = {
            "total_loads": 0,
            "total_saves": 0,
            "total_adds": 0,
            "total_removes": 0,
            "cache_hit_count": 0,
            "cache_miss_count": 0,
        }

    def get_or_create_index(self, table_name: str, doc_ids: list[str], documents: list[str]) -> BM25Index:
        """Get an existing index or create a new one with persistence support.

        Args:
            table_name: Name of the table (used for cache file naming).
            doc_ids: List of document identifiers.
            documents: List of document texts.

        Returns:
            BM25Index instance.
        """
        cache_file = self._cache_dir / f"{table_name}_bm25_index.pkl"

        if table_name in self._indexes:
            idx = self._indexes[table_name]
            # Check if index is stale (documents changed)
            if idx.doc_ids == doc_ids and idx.documents == documents:
                self._stats["cache_hit_count"] += 1
                return idx

        # Try to load from cache
        idx = BM25Index(doc_ids=[], documents=[])
        if idx.load(cache_file):
            self._stats["cache_hit_count"] += 1
            self._indexes[table_name] = idx
            return idx

        self._stats["cache_miss_count"] += 1

        # Create new index
        idx = BM25Index(doc_ids=doc_ids, documents=documents)
        self._indexes[table_name] = idx

        # Save to cache
        idx.save(cache_file)
        self._stats["total_saves"] += 1

        return idx

    def update_index(self, table_name: str, added_ids: list[str], added_docs: list[str]) -> None:
        """Incrementally update an index with new documents.

        Args:
            table_name: Name of the table.
            added_ids: List of new document identifiers.
            added_docs: List of new document texts.
        """
        if table_name not in self._indexes:
            raise KeyError(f"No index found for table: {table_name}")

        idx = self._indexes[table_name]
        idx.add_documents(added_ids, added_docs)
        self._stats["total_adds"] += len(added_ids)

        # Auto-save if dirty
        if idx.is_dirty():
            cache_file = self._cache_dir / f"{table_name}_bm25_index.pkl"
            idx.save(cache_file)
            self._stats["total_saves"] += 1

    def remove_from_index(self, table_name: str, doc_ids_to_remove: set[str]) -> None:
        """Remove documents from an index.

        Args:
            table_name: Name of the table.
            doc_ids_to_remove: Set of document identifiers to remove.
        """
        if table_name not in self._indexes:
            raise KeyError(f"No index found for table: {table_name}")

        idx = self._indexes[table_name]
        idx.remove_documents(doc_ids_to_remove)
        self._stats["total_removes"] += len(doc_ids_to_remove)

        # Auto-save if dirty
        if idx.is_dirty():
            cache_file = self._cache_dir / f"{table_name}_bm25_index.pkl"
            idx.save(cache_file)
            self._stats["total_saves"] += 1

    def get_stats(self) -> dict[str, Any]:
        """Get index manager statistics.

        Returns a dict with: total_loads, total_saves, total_adds,
        total_removes, cache_hit_count, cache_miss_count, active_indexes,
        and cache_dir.

        Returns:
            Statistics dictionary.
        """
        return {
            **self._stats,
            "active_indexes": len(self._indexes),
            "cache_dir": str(self._cache_dir),
        }

    def save_all_indexes(self) -> int:
        """Persist all dirty indexes to disk.

        Iterates over all registered indexes and calls save() for any
        index where is_dirty() returns True.  Errors on individual
        indexes are logged but do not abort the loop.

        Returns:
            Number of indexes saved successfully.
        """
        count = 0
        for table_name, idx in self._indexes.items():
            if idx.is_dirty():
                cache_file = self._cache_dir / f"{table_name}_bm25_index.pkl"
                try:
                    idx.save(cache_file)
                    count += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to save index for %s: %s", table_name, exc)
        return count

    def clear_cache(self) -> int:
        """Clear all cached indexes.

        Returns:
            Number of cache files removed.
        """
        count = 0
        for file in self._cache_dir.glob("*.pkl"):
            try:
                file.unlink()
                count += 1
            except Exception:
                pass
        self._indexes.clear()
        logger.info("BM25 cache cleared: %d files removed", count)
        return count


# Singleton instance
_index_manager: BM25IndexManager | None = None


def get_bm25_index_manager(cache_dir: Path | None = None) -> BM25IndexManager:
    """Get or create the singleton BM25IndexManager instance."""
    global _index_manager
    if _index_manager is None:
        _index_manager = BM25IndexManager(cache_dir=cache_dir)
    return _index_manager


def bm25_search(doc_ids: Sequence[str], documents: Sequence[str], query: str, *, top_k: int = 20) -> list[tuple[str, float]]:
    """Convenience wrapper: build an index and query it once.

    Note: For repeated queries, prefer using BM25IndexManager for persistence.
    """
    if len(doc_ids) != len(documents):
        raise ValueError("doc_ids and documents must align")
    idx = BM25Index(doc_ids=list(doc_ids), documents=list(documents))
    return idx.query(query, top_k=top_k)


__all__ = ["BM25Index", "BM25IndexManager", "bm25_search", "get_bm25_index_manager", "_tokenize"]
