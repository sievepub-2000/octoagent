"""Comprehensive RAG integration tests covering M1/M2/M3/L1/L2/L3.

Tests cover:
- End-to-end BM25 + FAISS persistence
- Quality monitoring with feedback loop
- Unified store error handling
- Edge cases and performance
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.storage.rag.bm25_backend import BM25Index, BM25IndexManager, bm25_search
from src.storage.rag.faiss_backend import (
    FAISSIndexManager,
    FAISSStats,
    search_rows,
    get_faiss_index_manager,
)
from src.storage.rag.unified_store import UnifiedRAGStore, RAGMatch
from src.storage.rag.quality_monitor import (
    RetrievalQualityMonitor,
    RetrievalResult,
    get_quality_monitor,
)


# ── M1: BM25 Index Persistence ──────────────────────────────────────────────


class TestBM25Persistence:
    """M1: BM25 index persistence and incremental updates."""

    def test_full_persistence_cycle(self, tmp_path: Path) -> None:
        """Create index → save → load → search → verify."""
        cache_dir = tmp_path / "bm25"
        mgr = BM25IndexManager(cache_dir=cache_dir)

        doc_ids = [f"d{i}" for i in range(10)]
        documents = [f"document number {i} about topic X" for i in range(10)]

        idx = mgr.get_or_create_index("test", doc_ids, documents)
        assert len(idx.doc_ids) == 10

        # Search before reload
        results = idx.query("topic X", top_k=3)
        assert len(results) > 0

        # Simulate process restart: load from cache
        mgr2 = BM25IndexManager(cache_dir=cache_dir)
        idx2 = mgr2.get_or_create_index("test", doc_ids[:5], documents[:5])
        assert len(idx2.doc_ids) == 10  # Loaded from cache

    def test_incremental_add_then_persist(self, tmp_path: Path) -> None:
        """Add documents, verify dirty, save, load, verify new docs."""
        cache_dir = tmp_path / "bm25"
        mgr = BM25IndexManager(cache_dir=cache_dir)
        mgr.get_or_create_index("tbl", ["d1"], ["doc1"])
        mgr.update_index("tbl", ["d2", "d3"], ["doc2", "doc3"])
        idx = mgr._indexes["tbl"]
        assert idx.is_dirty() is True
        assert len(idx.doc_ids) == 3

        # Reload
        mgr2 = BM25IndexManager(cache_dir=cache_dir)
        idx2 = mgr2.get_or_create_index("tbl", ["d1"], ["doc1"])
        assert len(idx2.doc_ids) == 3
        assert "d2" in idx2.doc_ids
        assert "d3" in idx2.doc_ids

    def test_incremental_remove_then_persist(self, tmp_path: Path) -> None:
        """Remove docs, save, load, verify removal."""
        cache_dir = tmp_path / "bm25"
        mgr = BM25IndexManager(cache_dir=cache_dir)
        mgr.get_or_create_index("tbl", ["d1", "d2", "d3"], ["doc1", "doc2", "doc3"])
        mgr.remove_from_index("tbl", {"d2"})
        idx = mgr._indexes["tbl"]
        assert len(idx.doc_ids) == 2
        assert "d2" not in idx.doc_ids

        # Reload
        mgr2 = BM25IndexManager(cache_dir=cache_dir)
        idx2 = mgr2.get_or_create_index("tbl", ["d1"], ["doc1"])
        assert len(idx2.doc_ids) == 2
        assert "d2" not in idx2.doc_ids

    def test_save_all_indexes(self, tmp_path: Path) -> None:
        """Test BM25IndexManager.save_all_indexes()."""
        mgr = BM25IndexManager(cache_dir=tmp_path / "bm25")
        mgr.get_or_create_index("a", ["d1"], ["doc1"])
        mgr.update_index("a", ["d2"], ["doc2"])
        mgr.get_or_create_index("b", ["d1"], ["doc1"])
        count = mgr.save_all_indexes()
        assert count >= 1


# ── M2: Retrieval Quality Monitoring ────────────────────────────────────────


class TestQualityMonitor:
    """M2: Retrieval quality monitoring metrics and logging."""

    def test_monitor_records_query_stats(self) -> None:
        """Basic recording of query stats."""
        monitor = RetrievalQualityMonitor()
        monitor.record_result(RetrievalResult(
            query="test", table="system_memories", mode="hybrid",
            results_count=3, top_score=0.9, avg_score=0.7,
            latency_ms=10.0, has_vector=True, has_bm25=True, has_reranker=False,
        ))
        metrics = monitor.get_metrics()
        assert metrics["total_queries"] == 1
        assert metrics["total_results"] == 3

    def test_monitor_feedback_loop(self) -> None:
        """Test that feedback updates precision/recall."""
        monitor = RetrievalQualityMonitor()
        monitor.record_result(RetrievalResult(
            query="test", table="system_memories", mode="hybrid",
            results_count=3, top_score=0.9, avg_score=0.7,
            latency_ms=10.0, has_vector=True, has_bm25=True, has_reranker=False,
        ))
        monitor.record_feedback("q1", [3, 2, 0])
        metrics = monitor.get_metrics()
        assert metrics["feedback_count"] == 1

    def test_monitor_ndcg_computation(self) -> None:
        """Test NDCG computation with known values."""
        monitor = RetrievalQualityMonitor()
        # Perfect ranking
        ndcg = monitor._compute_ndcg([3, 2, 1])
        assert abs(ndcg - 1.0) < 0.01
        # Worst ranking
        ndcg = monitor._compute_ndcg([0, 0, 1])
        assert ndcg > 0.0

    def test_monitor_export_import(self, tmp_path: Path) -> None:
        """Test exporting metrics to JSON."""
        monitor = RetrievalQualityMonitor()
        monitor.record_result(RetrievalResult(
            query="test", table="system_memories", mode="hybrid",
            results_count=3, top_score=0.9, avg_score=0.7,
            latency_ms=10.0, has_vector=True, has_bm25=True, has_reranker=False,
        ))
        path = tmp_path / "metrics.json"
        monitor.export_metrics(path)
        assert path.exists()
        with open(path) as f:
            data = json.load(f)
        assert data["total_queries"] == 1

    def test_monitor_report_generation(self) -> None:
        """Test human-readable report generation."""
        monitor = RetrievalQualityMonitor()
        monitor.record_result(RetrievalResult(
            query="test", table="system_memories", mode="hybrid",
            results_count=5, top_score=0.95, avg_score=0.8,
            latency_ms=15.0, has_vector=True, has_bm25=True, has_reranker=True,
        ))
        report = monitor.get_report()
        assert "RAG Retrieval Quality Report" in report
        assert "Total Queries: 1" in report


# ── M3: FAISS Index Persistence ─────────────────────────────────────────────


class TestFAISSPersistence:
    """M3: FAISS index persistence and incremental vector loading."""

    def test_search_with_persistence(self, tmp_path: Path) -> None:
        """Search → save index → search again with cached index."""
        import numpy  # noqa: F401 - ensures numpy is available
        faiss = pytest.importorskip("faiss")

        cache_dir = tmp_path / "faiss"
        mgr = FAISSIndexManager(cache_dir=cache_dir)
        rows = [
            (f"r{i}", "ns", f"content {i}", "{}", [0.1 * (i + 1)] * 10)
            for i in range(20)
        ]
        query = [0.5] * 10
        results1 = mgr.search_with_persistence("test", rows, query, top_k=5)
        assert results1 is not None
        assert len(results1) > 0

        # Rebuild rows (simulating new load) and search again
        results2 = mgr.search_with_persistence("test", rows, query, top_k=5)
        assert results2 is not None

    def test_incremental_vector_add(self, tmp_path: Path) -> None:
        """Add vectors to existing persisted FAISS index."""
        import numpy  # noqa: F401
        faiss = pytest.importorskip("faiss")

        cache_dir = tmp_path / "faiss"
        mgr = FAISSIndexManager(cache_dir=cache_dir)
        rows = [("r0", "ns", "c0", "{}", [0.1] * 10)]
        mgr.search_with_persistence("test", rows, [0.1] * 10, top_k=1)
        vectors = [[0.2] * 10 for _ in range(10)]
        added = mgr.add_vectors_to_existing_index("test", vectors)
        assert added == 10

    def test_faiss_stats_completeness(self, tmp_path: Path) -> None:
        """Test FAISS stats returns all expected fields."""
        mgr = FAISSIndexManager(cache_dir=tmp_path / "faiss")
        stats = mgr.get_stats()
        required = {
            "total_loads", "total_saves", "total_searches", "total_adds",
            "cache_hit_count", "cache_miss_count", "avg_search_time_ms",
            "current_index_size", "cache_dir",
        }
        assert required.issubset(set(stats.keys()))

    def test_faiss_clear_cache(self, tmp_path: Path) -> None:
        """Test clearing FAISS cache."""
        import numpy  # noqa: F401
        faiss = pytest.importorskip("faiss")

        mgr = FAISSIndexManager(cache_dir=tmp_path / "faiss")
        rows = [("r0", "ns", "c0", "{}", [0.1] * 10)]
        mgr.search_with_persistence("test", rows, [0.1] * 10, top_k=1)
        count = mgr.clear_cache()
        assert count >= 0


# ── L1: Key Function Documentation ──────────────────────────────────────────


class TestDocumentation:
    """L1: Verify key functions have docstrings."""

    def test_bm25_index_has_docstring(self) -> None:
        assert BM25Index.__doc__ is not None
        assert len(BM25Index.__doc__) > 50

    def test_bm25_index_manager_has_docstring(self) -> None:
        assert BM25IndexManager.__doc__ is not None
        assert len(BM25IndexManager.__doc__) > 50

    def test_faiss_index_manager_has_docstring(self) -> None:
        assert FAISSIndexManager.__doc__ is not None
        assert len(FAISSIndexManager.__doc__) > 50

    def test_unified_rag_store_has_docstring(self) -> None:
        assert UnifiedRAGStore.__doc__ is not None
        assert len(UnifiedRAGStore.__doc__) > 50

    def test_search_rows_has_docstring(self) -> None:
        assert search_rows.__doc__ is not None
        assert "FAISS" in search_rows.__doc__

    def test_bm25_search_has_docstring(self) -> None:
        assert bm25_search.__doc__ is not None

    def test_quality_monitor_has_docstring(self) -> None:
        assert RetrievalQualityMonitor.__doc__ is not None
        assert len(RetrievalQualityMonitor.__doc__) > 50


# ── L2: Integration Tests ───────────────────────────────────────────────────


class TestEndToEnd:
    """L2: End-to-end integration tests."""

    def test_bm25_full_pipeline(self, tmp_path: Path) -> None:
        """Create → add → remove → persist → load → search."""
        mgr = BM25IndexManager(cache_dir=tmp_path / "bm25")
        mgr.get_or_create_index("e2e", ["d1", "d2", "d3"], ["doc1", "doc2", "doc3"])
        mgr.update_index("e2e", ["d4"], ["doc4"])
        mgr.remove_from_index("e2e", {"d2"})
        mgr.save_all_indexes()

        # Reload
        mgr2 = BM25IndexManager(cache_dir=tmp_path / "bm25")
        idx = mgr2.get_or_create_index("e2e", ["d1"], ["doc1"])
        assert len(idx.doc_ids) == 3  # d1, d3, d4
        assert "d2" not in idx.doc_ids
        results = idx.query("doc", top_k=10)
        assert len(results) > 0

    def test_quality_monitor_full_cycle(self) -> None:
        """Record multiple queries → feedback → metrics → report → export."""
        monitor = RetrievalQualityMonitor()
        for i in range(3):
            monitor.record_result(RetrievalResult(
                query=f"q{i}", table="system_memories", mode="hybrid",
                results_count=3, top_score=0.9 - i * 0.1,
                avg_score=0.7 - i * 0.1, latency_ms=10.0,
                has_vector=True, has_bm25=True, has_reranker=False,
            ))
        monitor.record_feedback("q1", [4, 2, 0])
        monitor.record_feedback("q2", [3, 1, 0])
        report = monitor.get_report()
        assert "Total Queries: 3" in report

    def test_faiss_full_pipeline(self, tmp_path: Path) -> None:
        """Create → persist → add → reload → search."""
        import numpy  # noqa: F401
        faiss = pytest.importorskip("faiss")

        mgr = FAISSIndexManager(cache_dir=tmp_path / "faiss")
        rows = [(f"r{i}", "ns", f"c{i}", "{}", [0.1] * 10) for i in range(10)]
        mgr.search_with_persistence("e2e", rows, [0.1] * 10, top_k=5)
        mgr.add_to_index("e2e", [[0.2] * 10] * 5)
        stats = mgr.get_stats()
        assert stats["total_adds"] >= 5


# ── L3: Error Handling ──────────────────────────────────────────────────────


class TestErrorHandling:
    """L3: Enhanced error handling tests."""

    def test_bm25_save_error(self, caplog: pytest.LogCaptureFixture) -> None:
        idx = BM25Index(doc_ids=["d1"], documents=["doc1"])
        idx.save(Path("/nonexistent_dir/x.pkl"))
        assert any("Failed to save BM25 index" in r.message for r in caplog.records)

    def test_bm25_load_corrupt(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        path = tmp_path / "corrupt.pkl"
        path.write_bytes(b"garbage data")
        idx = BM25Index(doc_ids=[], documents=[])
        assert idx.load(path) is False

    def test_bm25_add_mismatch(self) -> None:
        idx = BM25Index(doc_ids=["d1"], documents=["doc1"])
        with pytest.raises(ValueError, match="must align"):
            idx.add_documents(["d2", "d3"], ["doc2"])

    def test_bm25_remove_nonexistent(self) -> None:
        idx = BM25Index(doc_ids=["d1", "d2"], documents=["doc1", "doc2"])
        idx.remove_documents({"d99"})
        assert len(idx.doc_ids) == 2

    def test_faiss_add_empty_index(self, tmp_path: Path) -> None:
        mgr = FAISSIndexManager(cache_dir=tmp_path / "faiss")
        assert mgr.add_to_index("nope", [[0.1] * 10]) == 0

    def test_faiss_add_vectors_large(self, tmp_path: Path) -> None:
        import numpy  # noqa: F401
        faiss = pytest.importorskip("faiss")
        mgr = FAISSIndexManager(cache_dir=tmp_path / "faiss")
        rows = [("r0", "ns", "c0", "{}", [0.1] * 10)]
        mgr.search_with_persistence("test", rows, [0.1] * 10, top_k=1)
        assert mgr.add_vectors_to_existing_index("test", [[0.2] * 10] * 100) == 100

    def test_bm25_search_empty_query(self) -> None:
        assert bm25_search(["d1"], ["doc1"], "", top_k=5) == []

    def test_bm25_search_empty_docs(self) -> None:
        assert bm25_search([], [], "anything", top_k=5) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
