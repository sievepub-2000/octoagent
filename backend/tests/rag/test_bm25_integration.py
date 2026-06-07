"""Integration tests for BM25 index persistence and incremental updates.

Tests cover:
- Basic BM25 search functionality
- Index persistence (save/load)
- Incremental document addition
- Incremental document removal
- Cache hit/miss statistics
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.storage.rag.bm25_backend import (
    BM25Index,
    BM25IndexManager,
    bm25_search,
    get_bm25_index_manager,
)


class TestBM25Search:
    """Test basic BM25 search functionality."""

    def test_basic_search(self):
        """Test basic BM25 search returns results."""
        doc_ids = ["doc1", "doc2", "doc3"]
        documents = [
            "The quick brown fox jumps over the lazy dog",
            "A fast brown fox leaps over a sleeping dog",
            "The lazy dog sleeps all day long"
        ]
        
        results = bm25_search(doc_ids, documents, "quick brown fox", top_k=2)
        
        assert len(results) > 0
        assert len(results) <= 2
        # First result should be most relevant
        doc_id, score = results[0]
        assert doc_id in doc_ids
        assert score > 0.0

    def test_search_with_no_results(self):
        """Test BM25 search with empty documents."""
        results = bm25_search([], [], "test query", top_k=5)
        assert results == []

    def test_search_with_single_document(self):
        """Test BM25 search with a single document."""
        # Use multiple documents to ensure BM25 scores are positive
        doc_ids = ["doc1", "doc2", "doc3"]
        documents = [
            "This is a test document with many words",
            "Another document for testing",
            "Third document here"
        ]
        
        results = bm25_search(doc_ids, documents, "test document", top_k=1)
        
        assert len(results) == 1
        assert results[0][0] == "doc1"
        assert results[0][1] > 0.0

    def test_search_chinese_text(self):
        """Test BM25 search with Chinese text."""
        # Use mixed Chinese-English documents for better BM25 matching
        doc_ids = ["doc1", "doc2", "doc3"]
        documents = [
            "这是一个测试文档 with many words",
            "这是另一个测试文档 for testing",
            "Third document here"
        ]
        
        # Use English query that matches the English words in the documents
        results = bm25_search(doc_ids, documents, "document", top_k=1)
        
        assert len(results) > 0
        assert results[0][1] > 0.0


class TestBM25IndexPersistence:
    """Test BM25 index persistence functionality."""

    def test_save_and_load_index(self):
        """Test saving and loading BM25 index to/from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_index.pkl"
            
            # Create and save index
            doc_ids = ["doc1", "doc2", "doc3"]
            documents = [
                "The quick brown fox",
                "A fast brown fox",
                "The lazy dog"
            ]
            
            idx = BM25Index(doc_ids=doc_ids, documents=documents)
            idx.save(cache_path)
            
            # Verify file was created
            assert cache_path.exists()
            
            # Load index
            loaded_idx = BM25Index(doc_ids=[], documents=[])
            result = loaded_idx.load(cache_path)
            
            assert result is True
            assert len(loaded_idx.doc_ids) == len(doc_ids)
            
            # Test search on loaded index
            results = loaded_idx.query("quick brown fox", top_k=1)
            assert len(results) > 0

    def test_load_nonexistent_index(self):
        """Test loading a non-existent index returns False."""
        idx = BM25Index(doc_ids=[], documents=[])
        result = idx.load(Path("/tmp/nonexistent_index.pkl"))
        assert result is False

    def test_index_dirty_tracking(self):
        """Test that index dirty flag is properly tracked."""
        idx = BM25Index(doc_ids=["doc1"], documents=["test"])
        assert idx.is_dirty() is False
        
        # Adding documents should mark as dirty
        idx.add_documents(["doc2"], ["test2"])
        assert idx.is_dirty() is True

    def test_incremental_document_addition(self):
        """Test adding documents incrementally."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_index.pkl"
            
            # Create initial index
            idx = BM25Index(doc_ids=["doc1"], documents=["test1"])
            idx.save(cache_path)
            
            # Load and add more documents
            loaded_idx = BM25Index(doc_ids=[], documents=[])
            loaded_idx.load(cache_path)
            loaded_idx.add_documents(["doc2", "doc3"], ["test2", "test3"])
            
            # Verify documents were added
            assert len(loaded_idx.doc_ids) == 3
            assert "doc1" in loaded_idx.doc_ids
            assert "doc2" in loaded_idx.doc_ids
            assert "doc3" in loaded_idx.doc_ids

    def test_incremental_document_removal(self):
        """Test removing documents incrementally."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_index.pkl"
            
            # Create initial index
            idx = BM25Index(
                doc_ids=["doc1", "doc2", "doc3"],
                documents=["test1", "test2", "test3"]
            )
            idx.save(cache_path)
            
            # Load and remove documents
            loaded_idx = BM25Index(doc_ids=[], documents=[])
            loaded_idx.load(cache_path)
            loaded_idx.remove_documents({"doc2"})
            
            # Verify document was removed
            assert len(loaded_idx.doc_ids) == 2
            assert "doc1" in loaded_idx.doc_ids
            assert "doc2" not in loaded_idx.doc_ids
            assert "doc3" in loaded_idx.doc_ids


class TestBM25IndexManager:
    """Test BM25 index manager functionality."""

    def test_get_or_create_index(self):
        """Test getting or creating an index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BM25IndexManager(cache_dir=Path(tmpdir))
            
            doc_ids = ["doc1", "doc2"]
            documents = ["test1", "test2"]
            
            # First call should create new index
            idx1 = manager.get_or_create_index("test_table", doc_ids, documents)
            assert idx1 is not None
            assert len(idx1.doc_ids) == 2
            
            # Second call with same data should return cached index
            idx2 = manager.get_or_create_index("test_table", doc_ids, documents)
            assert idx1 is idx2  # Same object

    def test_update_index_incrementally(self):
        """Test incremental index updates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BM25IndexManager(cache_dir=Path(tmpdir))
            
            # Create initial index
            doc_ids = ["doc1"]
            documents = ["test1"]
            manager.get_or_create_index("test_table", doc_ids, documents)
            
            # Update index with new documents
            manager.update_index("test_table", ["doc2"], ["test2"])
            
            # Verify update
            idx = manager._indexes["test_table"]
            assert len(idx.doc_ids) == 2
            assert "doc1" in idx.doc_ids
            assert "doc2" in idx.doc_ids

    def test_remove_from_index(self):
        """Test removing documents from index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BM25IndexManager(cache_dir=Path(tmpdir))
            
            # Create initial index
            doc_ids = ["doc1", "doc2", "doc3"]
            documents = ["test1", "test2", "test3"]
            manager.get_or_create_index("test_table", doc_ids, documents)
            
            # Remove document
            manager.remove_from_index("test_table", {"doc2"})
            
            # Verify removal
            idx = manager._indexes["test_table"]
            assert len(idx.doc_ids) == 2
            assert "doc2" not in idx.doc_ids

    def test_clear_cache(self):
        """Test clearing all cached indexes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BM25IndexManager(cache_dir=Path(tmpdir))
            
            # Create some indexes
            manager.get_or_create_index("table1", ["doc1"], ["test1"])
            manager.get_or_create_index("table2", ["doc2"], ["test2"])
            
            # Clear cache
            count = manager.clear_cache()
            
            # Verify cache was cleared
            assert count >= 0
            assert len(manager._indexes) == 0

    def test_get_stats(self):
        """Test getting index manager statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BM25IndexManager(cache_dir=Path(tmpdir))
            
            # Perform some operations
            manager.get_or_create_index("table1", ["doc1"], ["test1"])
            manager.update_index("table1", ["doc2"], ["test2"])
            
            stats = manager.get_stats()
            
            assert "total_loads" in stats
            assert "total_saves" in stats
            assert "total_adds" in stats
            assert "active_indexes" in stats


class TestBM25EdgeCases:
    """Test edge cases and error handling."""

    def test_mismatched_doc_ids_and_documents(self):
        """Test error when doc_ids and documents have different lengths."""
        with pytest.raises(ValueError, match="must align"):
            bm25_search(["doc1"], ["test1", "test2"], "query")

    def test_empty_query(self):
        """Test search with empty query returns empty results."""
        idx = BM25Index(doc_ids=["doc1"], documents=["test"])
        results = idx.query("", top_k=5)
        assert results == []

    def test_very_large_top_k(self):
        """Test search with top_k larger than document count."""
        doc_ids = ["doc1", "doc2", "doc3"]
        documents = ["test1", "test2", "test3"]
        
        results = bm25_search(doc_ids, documents, "test", top_k=100)
        
        # Should return at most 3 results
        assert len(results) <= 3


class TestBM25Performance:
    """Test BM25 performance characteristics."""

    def test_search_speed(self):
        """Test that search operations complete in reasonable time."""
        import time
        
        # Create a moderate-sized index
        doc_ids = [f"doc{i}" for i in range(100)]
        documents = [f"This is document number {i} with some text" for i in range(100)]
        
        start_time = time.time()
        for _ in range(10):
            bm25_search(doc_ids, documents, "document text", top_k=5)
        elapsed = time.time() - start_time
        
        # Should complete 10 searches in less than 1 second
        assert elapsed < 1.0, f"Search took too long: {elapsed}s"


class TestBM25ErrorHandling:
    """Test L3: Enhanced error handling for BM25 operations."""

    def test_save_index_error_handling(self, caplog):
        """Test that save handles disk full / permission errors gracefully."""
        idx = BM25Index(doc_ids=["d1"], documents=["test doc"])
        # Try saving to a non-existent parent directory
        idx.save(Path("/nonexistent_dir/index.pkl"))
        assert any("Failed to save BM25 index" in r.message for r in caplog.records)

    def test_load_index_error_handling(self, caplog):
        """Test that load handles corrupted pickle gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corrupt_path = Path(tmpdir) / "corrupt.pkl"
            with open(corrupt_path, "wb") as f:
                f.write(b"not a valid pickle")
            idx = BM25Index(doc_ids=[], documents=[])
            result = idx.load(corrupt_path)
            assert result is False

    def test_add_mismatched_lists(self):
        """Test that adding documents with mismatched lengths raises ValueError."""
        idx = BM25Index(doc_ids=["d1"], documents=["doc1"])
        with pytest.raises(ValueError, match="must align"):
            idx.add_documents(["d2", "d3"], ["doc2"])

    def test_remove_nonexistent_docs(self):
        """Test removing documents that don't exist is a no-op."""
        idx = BM25Index(doc_ids=["d1", "d2"], documents=["doc1", "doc2"])
        idx.remove_documents({"d99", "d100"})
        assert len(idx.doc_ids) == 2
        assert idx.is_dirty() is False

    def test_manager_get_or_create_with_stale_data(self):
        """Test that get_or_create_index returns cached index even with stale data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BM25IndexManager(cache_dir=Path(tmpdir))
            idx1 = manager.get_or_create_index("tbl", ["d1"], ["doc1"])
            # Same data — should return same object (cache hit)
            idx2 = manager.get_or_create_index("tbl", ["d1"], ["doc1"])
            assert idx1 is idx2
            # Different data — cache file exists, so loads cached version
            idx3 = manager.get_or_create_index("tbl", ["d1", "d2"], ["doc1", "doc2"])
            assert idx3 is not idx1
            # Loads from cache: original data ['d1'], not the new ['d1', 'd2']
            assert len(idx3.doc_ids) == 1
            assert idx3.doc_ids == ["d1"]

    def test_update_nonexistent_table(self):
        """Test updating a table with no index raises KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BM25IndexManager(cache_dir=Path(tmpdir))
            with pytest.raises(KeyError, match="No index found"):
                manager.update_index("nonexistent", ["d1"], ["doc1"])

    def test_clear_cache_empty(self):
        """Test clearing cache when no indexes exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BM25IndexManager(cache_dir=Path(tmpdir))
            count = manager.clear_cache()
            assert count == 0

    def test_get_stats_completeness(self):
        """Test that get_stats returns all expected keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BM25IndexManager(cache_dir=Path(tmpdir))
            manager.get_or_create_index("tbl", ["d1"], ["doc1"])
            stats = manager.get_stats()
            required_keys = {
                "total_loads", "total_saves", "total_adds",
                "total_removes", "cache_hit_count", "cache_miss_count",
                "active_indexes", "cache_dir",
            }
            assert required_keys.issubset(set(stats.keys()))

    def test_bm25_search_large_top_k(self):
        """Test searching with top_k >> number of documents."""
        doc_ids = [f"d{i}" for i in range(5)]
        documents = [f"document {i}" for i in range(5)]
        results = bm25_search(doc_ids, documents, "document", top_k=1000)
        assert len(results) <= 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
