"""Vector retrieval batch query cache for octoagent.

This module provides caching for vector embeddings to avoid redundant
computation when the same or similar queries are executed repeatedly.
"""

import hashlib
import logging
from collections import OrderedDict

logger = logging.getLogger(__name__)


class VectorQueryCache:
    """LRU cache for vector query embeddings with TTL support.

    Attributes:
        max_size: Maximum number of entries in the cache.
        ttl_seconds: Time-to-live for cache entries in seconds.
    """

    def __init__(self, max_size: int = 10000, ttl_seconds: int = 3600) -> None:
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple[list[float], float]] = OrderedDict()

    def _make_key(self, query: str) -> str:
        """Generate a cache key from the query string.

        Args:
            query: The query text to embed.

        Returns:
            A hash-based cache key.
        """
        normalized = query.lower().strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, query: str) -> list[float] | None:
        """Retrieve an embedding from the cache.

        Args:
            query: The query text to look up.

        Returns:
            The cached embedding vector, or None if not found/expired.
        """
        key = self._make_key(query)

        if key not in self._cache:
            return None

        embedding, timestamp = self._cache[key]

        # Check TTL
        import time

        if time.time() - timestamp > self.ttl_seconds:
            del self._cache[key]
            logger.debug("Cache entry expired for query: %s", query[:50])
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return embedding

    def set(self, query: str, embedding: list[float]) -> None:
        """Store an embedding in the cache.

        Args:
            query: The query text.
            embedding: The embedding vector to cache.
        """
        key = self._make_key(query)

        # Remove old entry if exists
        if key in self._cache:
            del self._cache[key]

        # Evict oldest entries if at capacity
        while len(self._cache) >= self.max_size:
            oldest_key, _ = self._cache.popitem(last=False)
            logger.debug("Cache eviction: removed key %s", oldest_key[:8])

        import time

        self._cache[key] = (embedding, time.time())

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        logger.info("Vector query cache cleared")

    @property
    def size(self) -> int:
        """Return the current number of cached entries."""
        return len(self._cache)


# Global cache instance
_vector_cache: VectorQueryCache | None = None


def get_vector_cache() -> VectorQueryCache:
    """Get or create the global vector query cache instance.

    Returns:
        The singleton VectorQueryCache instance.
    """
    global _vector_cache
    if _vector_cache is None:
        _vector_cache = VectorQueryCache()
    return _vector_cache


def clear_vector_cache() -> None:
    """Clear the global vector query cache."""
    global _vector_cache
    if _vector_cache is not None:
        _vector_cache.clear()
        _vector_cache = None
