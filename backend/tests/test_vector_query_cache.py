"""Tests for vector query cache - edge cases and performance."""

import time

from src.runtime.cache.vector_query_cache import VectorQueryCache, clear_vector_cache, get_vector_cache


class TestVectorQueryCache:
    """Test VectorQueryCache class."""

    def test_basic_set_get(self) -> None:
        cache = VectorQueryCache(max_size=100)
        embedding = [0.1, 0.2, 0.3]

        cache.set("test query", embedding)
        result = cache.get("test query")

        assert result == embedding

    def test_get_missing_query(self) -> None:
        cache = VectorQueryCache(max_size=100)
        result = cache.get("nonexistent query")
        assert result is None

    def test_case_insensitive_key(self) -> None:
        cache = VectorQueryCache(max_size=100)
        embedding = [0.5, 0.6]

        cache.set("Test Query", embedding)
        result = cache.get("test query")

        assert result == embedding

    def test_ttl_expiration(self) -> None:
        cache = VectorQueryCache(max_size=100, ttl_seconds=0)  # Immediate expiry
        embedding = [0.1]

        cache.set("expiring query", embedding)
        time.sleep(0.01)
        result = cache.get("expiring query")

        assert result is None

    def test_lru_eviction(self) -> None:
        cache = VectorQueryCache(max_size=3, ttl_seconds=3600)

        # Fill cache to capacity
        for i in range(3):
            cache.set(f"query {i}", [float(i)])

        # Add one more, should evict oldest
        cache.set("new query", [9.9])

        # Oldest should be gone
        assert cache.get("query 0") is None
        # Newest should exist
        assert cache.get("new query") == [9.9]

    def test_cache_size(self) -> None:
        cache = VectorQueryCache(max_size=100)

        assert cache.size == 0

        cache.set("q1", [0.1])
        cache.set("q2", [0.2])

        assert cache.size == 2

    def test_clear(self) -> None:
        cache = VectorQueryCache(max_size=100)
        cache.set("q1", [0.1])
        cache.set("q2", [0.2])

        cache.clear()

        assert cache.size == 0
        assert cache.get("q1") is None

    def test_update_existing_entry(self) -> None:
        cache = VectorQueryCache(max_size=100)

        cache.set("query", [0.1])
        cache.set("query", [0.2])  # Update

        result = cache.get("query")
        assert result == [0.2]
        assert cache.size == 1


class TestGlobalCache:
    """Test global cache instance functions."""

    def test_get_vector_cache_singleton(self) -> None:
        cache1 = get_vector_cache()
        cache2 = get_vector_cache()

        assert cache1 is cache2

    def test_clear_vector_cache(self) -> None:
        clear_vector_cache()  # Should not crash even if not initialized

        cache = get_vector_cache()
        cache.set("test", [0.1])

        clear_vector_cache()

        # After clearing, new instance should be empty
        new_cache = get_vector_cache()
        assert new_cache.size == 0
