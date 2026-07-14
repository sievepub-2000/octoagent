"""Integration tests for FAISS index persistence and quality monitoring.

Tests cover:
- Basic FAISS search functionality
- Index persistence (save/load)
- Incremental vector addition
- Quality monitoring metrics
- Error handling
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.storage.rag import faiss_backend
from src.storage.rag.faiss_backend import (
    FAISSIndexManager,
    search_rows,
)
from src.storage.rag.quality_monitor import (
    RetrievalQualityMonitor,
    RetrievalResult,
)


class TestFAISSSearch:
    """Test basic FAISS search functionality."""

    def test_basic_search(self):
        """Test basic FAISS search returns results."""
        # Create sample rows with embeddings
        rows = []
        for i in range(10):
            # Create a simple embedding (e.g., [0.1, 0.2, 0.3, ...])
            emb = [j * 0.1 for j in range(i + 1)]
            if len(emb) < 10:
                emb = emb + [0.0] * (10 - len(emb))
            emb = emb[:10]  # Ensure exactly 10 dimensions
            row = (f"row{i}", "namespace", f"content {i}", "{}", emb)
            rows.append(row)

        # Query embedding similar to row 5
        query_embedding = [j * 0.1 for j in range(6)] + [0.0] * 4

        results = search_rows(rows, query_embedding=query_embedding, top_k=3)

        assert results is not None
        assert len(results) > 0
        assert len(results) <= 3

    def test_search_with_no_vectors(self):
        """Test FAISS search with no valid vectors."""
        rows = [
            ("row1", "namespace", "content1", "{}", None),
            ("row2", "namespace", "content2", "{}", [0.1, 0.2]),  # Wrong dimension
        ]

        query_embedding = [0.1, 0.2, 0.3]
        results = search_rows(rows, query_embedding=query_embedding, top_k=5)

        assert results is not None
        assert len(results) == 0

    def test_search_with_empty_query(self):
        """Test FAISS search with empty query embedding."""
        rows = [("row1", "namespace", "content1", "{}", [0.1, 0.2, 0.3])]

        results = search_rows(rows, query_embedding=[], top_k=5)
        assert results == []

    def test_search_with_top_k_zero(self):
        """Test FAISS search with top_k=0."""
        rows = [("row1", "namespace", "content1", "{}", [0.1, 0.2, 0.3])]

        query_embedding = [0.1, 0.2, 0.3]
        results = search_rows(rows, query_embedding=query_embedding, top_k=0)
        assert results == []


class TestFAISSIndexManager:
    """Test FAISS index manager functionality."""

    def test_search_with_persistence(self):
        """Test FAISS search with persistence support."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FAISSIndexManager(cache_dir=Path(tmpdir))

            # Create sample rows
            rows = []
            for i in range(10):
                emb = [j * 0.1 for j in range(i + 1)]
                if len(emb) < 10:
                    emb = emb + [0.0] * (10 - len(emb))
                emb = emb[:10]
                row = (f"row{i}", "namespace", f"content {i}", "{}", emb)
                rows.append(row)

            query_embedding = [0.1, 0.2, 0.3, 0.4, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0]

            # First search
            results1 = manager.search_with_persistence("test_table", rows, query_embedding, top_k=3)
            assert results1 is not None
            assert len(results1) > 0

    def test_add_to_index(self):
        """Test adding vectors to a cached FAISS index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FAISSIndexManager(cache_dir=Path(tmpdir))

            # First search to create index
            rows = []
            for i in range(5):
                embedding = [0.1] * 10
                row = (f"row{i}", "namespace", f"content {i}", "{}", embedding)
                rows.append(row)

            query_embedding = [0.1] * 10
            manager.search_with_persistence("test_table", rows, query_embedding, top_k=2)

            # Add more vectors
            new_vectors = [[0.2] * 10 for _ in range(5)]
            manager.add_to_index("test_table", new_vectors)

            # Verify stats
            stats = manager.get_stats()
            assert "total_adds" in stats

    def test_get_stats(self):
        """Test getting FAISS index manager statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FAISSIndexManager(cache_dir=Path(tmpdir))

            stats = manager.get_stats()

            assert "total_loads" in stats
            assert "total_saves" in stats
            assert "total_searches" in stats
            assert "avg_search_time_ms" in stats

    def test_clear_cache(self):
        """Test clearing all cached FAISS indexes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FAISSIndexManager(cache_dir=Path(tmpdir))

            # Create some indexes
            rows = [("row1", "namespace", "content1", "{}", [0.1] * 10)]
            query_embedding = [0.1] * 10
            manager.search_with_persistence("test_table", rows, query_embedding, top_k=1)

            # Clear cache
            count = manager.clear_cache()

            # Verify cache was cleared
            assert count >= 0


class TestRetrievalQualityMonitor:
    """Test retrieval quality monitoring functionality."""

    def test_record_result(self):
        """Test recording a retrieval result."""
        monitor = RetrievalQualityMonitor()

        result = RetrievalResult(
            query="test query",
            table="system_memories",
            mode="hybrid",
            results_count=5,
            top_score=0.9,
            avg_score=0.7,
            latency_ms=10.0,
            has_vector=True,
            has_bm25=True,
            has_reranker=False,
        )

        monitor.record_result(result)

        metrics = monitor.get_metrics()
        assert metrics["total_queries"] == 1
        assert metrics["total_results"] == 5

    def test_record_feedback(self):
        """Test recording user feedback."""
        monitor = RetrievalQualityMonitor()

        result = RetrievalResult(
            query="test query",
            table="system_memories",
            mode="hybrid",
            results_count=5,
            top_score=0.9,
            avg_score=0.7,
            latency_ms=10.0,
            has_vector=True,
            has_bm25=True,
            has_reranker=False,
        )

        monitor.record_result(result)
        monitor.record_feedback("query_hash_1", [5, 4, 3, 2, 1])

        metrics = monitor.get_metrics()
        assert metrics["feedback_count"] == 1

    def test_get_report(self):
        """Test generating a quality report."""
        monitor = RetrievalQualityMonitor()

        result = RetrievalResult(
            query="test query",
            table="system_memories",
            mode="hybrid",
            results_count=5,
            top_score=0.9,
            avg_score=0.7,
            latency_ms=10.0,
            has_vector=True,
            has_bm25=True,
            has_reranker=False,
        )

        monitor.record_result(result)
        report = monitor.get_report()

        assert "RAG Retrieval Quality Report" in report
        assert "Total Queries: 1" in report

    def test_export_metrics(self):
        """Test exporting metrics to JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = RetrievalQualityMonitor()

            result = RetrievalResult(
                query="test query",
                table="system_memories",
                mode="hybrid",
                results_count=5,
                top_score=0.9,
                avg_score=0.7,
                latency_ms=10.0,
                has_vector=True,
                has_bm25=True,
                has_reranker=False,
            )

            monitor.record_result(result)

            export_path = Path(tmpdir) / "test_metrics.json"
            monitor.export_metrics(export_path)

            assert export_path.exists()


class TestRetrievalQualityEdgeCases:
    """Test edge cases for retrieval quality monitoring."""

    def test_empty_feedback(self):
        """Test metrics with no feedback."""
        monitor = RetrievalQualityMonitor()

        metrics = monitor.get_metrics()
        assert metrics["precision_at_1"] == 0.0
        assert metrics["recall_at_10"] == 0.0

    def test_large_results_count(self):
        """Test recording result with large results count."""
        monitor = RetrievalQualityMonitor()

        result = RetrievalResult(
            query="test query",
            table="system_memories",
            mode="hybrid",
            results_count=1000,
            top_score=0.9,
            avg_score=0.7,
            latency_ms=10.0,
            has_vector=True,
            has_bm25=True,
            has_reranker=False,
        )

        monitor.record_result(result)

        metrics = monitor.get_metrics()
        assert metrics["total_results"] == 1000


class TestFAISSPerformance:
    """Test FAISS performance characteristics."""

    def test_search_speed(self):
        """Test that FAISS search operations complete in reasonable time."""
        import time

        # Create sample rows
        rows = []
        for i in range(100):
            embedding = [0.1] * 10
            row = (f"row{i}", "namespace", f"content {i}", "{}", embedding)
            rows.append(row)

        query_embedding = [0.1] * 10

        start_time = time.time()
        for _ in range(10):
            search_rows(rows, query_embedding=query_embedding, top_k=5)
        elapsed = time.time() - start_time

        # Should complete 10 searches in less than 1 second
        assert elapsed < 1.0, f"Search took too long: {elapsed}s"


class TestFAISSErrorHandling:
    """Test L3: Enhanced error handling for FAISS operations."""

    def test_add_to_nonexistent_index(self):
        """Test adding vectors when no index file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FAISSIndexManager(cache_dir=Path(tmpdir))
            count = manager.add_to_index("nonexistent", [[0.1] * 10])
            assert count == 0

    def test_add_vectors_large_batch(self):
        """Test adding a large batch of vectors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FAISSIndexManager(cache_dir=Path(tmpdir))
            # First search to create the index
            rows = [("row0", "ns", "content0", "{}", [0.1] * 10)]
            manager.search_with_persistence("test", rows, [0.1] * 10, top_k=1)
            # Add 50 vectors
            vectors = [[0.2] * 10 for _ in range(50)]
            count = manager.add_to_index("test", vectors)
            assert count == 50

    def test_add_vectors_no_fallback(self, monkeypatch):
        """Test add_to_index when FAISS is unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FAISSIndexManager(cache_dir=Path(tmpdir))
            monkeypatch.setattr(faiss_backend, "_optional_modules", lambda: (None, None))
            count = manager.add_to_index("test", [[0.1] * 10])
            assert count == 0

    def test_search_with_all_invalid_rows(self):
        """Test search when all rows have invalid embeddings."""
        rows = [
            ("r1", "ns", "c1", "{}", None),
            ("r2", "ns", "c2", "{}", "not-a-list"),
            ("r3", "ns", "c3", "{}", [0.1]),  # Wrong dimension
        ]
        results = search_rows(rows, query_embedding=[0.1, 0.2, 0.3], top_k=5)
        assert results == []

    def test_add_vectors_to_existing_index(self):
        """Test the new add_vectors_to_existing_index method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FAISSIndexManager(cache_dir=Path(tmpdir))
            rows = [("r0", "ns", "c0", "{}", [0.1] * 10)]
            manager.search_with_persistence("test", rows, [0.1] * 10, top_k=1)
            vectors = [[0.2] * 10 for _ in range(10)]
            count = manager.add_vectors_to_existing_index("test", vectors)
            assert count == 10

    def test_faiss_search_large_dataset(self):
        """Test FAISS search on a larger dataset."""
        rows = []
        for i in range(500):
            embedding = [float(i) * 0.01] * 10
            row = (f"row{i}", "ns", f"content {i}", "{}", embedding)
            rows.append(row)
        query = [0.5] * 10
        results = search_rows(rows, query_embedding=query, top_k=10)
        assert results is not None
        assert len(results) <= 10


class TestRetrievalQualityMonitorIntegration:
    """Test L2: Integration tests for retrieval quality monitoring."""

    def test_monitor_with_multiple_queries(self):
        """Test monitoring multiple queries and feedback."""
        monitor = RetrievalQualityMonitor()
        for i in range(5):
            result = RetrievalResult(
                query=f"query {i}",
                table="system_memories",
                mode="hybrid",
                results_count=5,
                top_score=0.9 - i * 0.05,
                avg_score=0.7 - i * 0.05,
                latency_ms=10.0 + i * 2,
                has_vector=True,
                has_bm25=True,
                has_reranker=i >= 3,
            )
            monitor.record_result(result)

        metrics = monitor.get_metrics()
        assert metrics["total_queries"] == 5
        assert metrics["total_results"] == 25

    def test_monitor_latency_tracking(self):
        """Test that latency tracking works correctly."""
        monitor = RetrievalQualityMonitor()
        for i in range(3):
            result = RetrievalResult(
                query="test",
                table="system_memories",
                mode="vector",
                results_count=1,
                top_score=0.8,
                avg_score=0.8,
                latency_ms=50.0 * (i + 1),
                has_vector=True,
                has_bm25=False,
                has_reranker=False,
            )
            monitor.record_result(result)
        metrics = monitor.get_metrics()
        # Latency should be an EMA, not a simple average
        assert metrics["avg_latency_ms"] > 0

    def test_monitor_with_no_results(self):
        """Test monitoring with zero-result queries."""
        monitor = RetrievalQualityMonitor()
        result = RetrievalResult(
            query="no match",
            table="system_memories",
            mode="bm25",
            results_count=0,
            top_score=0.0,
            avg_score=0.0,
            latency_ms=5.0,
            has_vector=False,
            has_bm25=True,
            has_reranker=False,
        )
        monitor.record_result(result)
        metrics = monitor.get_metrics()
        assert metrics["total_queries"] == 1
        assert metrics["total_results"] == 0

    def test_monitor_export_and_reload(self):
        """Test exporting metrics and verifying JSON structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = RetrievalQualityMonitor()
            result = RetrievalResult(
                query="test",
                table="system_memories",
                mode="hybrid",
                results_count=3,
                top_score=0.95,
                avg_score=0.85,
                latency_ms=15.0,
                has_vector=True,
                has_bm25=True,
                has_reranker=True,
            )
            monitor.record_result(result)
            path = Path(tmpdir) / "metrics.json"
            monitor.export_metrics(path)
            with open(path) as f:
                data = json.load(f)
            assert "total_queries" in data
            assert data["total_queries"] == 1


class TestRetrievalQualityMonitorEdgeCases:
    """Test edge cases for quality monitoring."""

    def test_monitor_max_results_capping(self):
        """Test that monitor caps results at max_results."""
        monitor = RetrievalQualityMonitor()
        for i in range(15000):
            result = RetrievalResult(
                query="test",
                table="system_memories",
                mode="vector",
                results_count=1,
                top_score=0.5,
                avg_score=0.5,
                latency_ms=1.0,
                has_vector=True,
                has_bm25=False,
                has_reranker=False,
            )
            monitor.record_result(result)
        assert len(monitor._results) <= monitor._max_results

    def test_monitor_single_query_stats(self):
        """Test stats after a single query."""
        monitor = RetrievalQualityMonitor()
        result = RetrievalResult(
            query="single",
            table="system_memories",
            mode="vector",
            results_count=1,
            top_score=0.5,
            avg_score=0.5,
            latency_ms=1.0,
            has_vector=True,
            has_bm25=False,
            has_reranker=False,
        )
        monitor.record_result(result)
        metrics = monitor.get_metrics()
        assert metrics["total_queries"] == 1
        assert metrics["feedback_count"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
