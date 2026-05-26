from __future__ import annotations

import importlib
import sys
import types

import pytest

from src.storage.rag.faiss_backend import search_rows
from src.storage.rag.unified_store import UnifiedRAGStore


def _fake_faiss_module(numpy):
    class IndexFlatIP:
        def __init__(self, dim: int) -> None:
            self.dim = dim
            self.matrix = None

        def add(self, matrix) -> None:
            self.matrix = matrix

        def search(self, query, top_k: int):
            scores = query @ self.matrix.T
            order = numpy.argsort(-scores[0])[:top_k]
            return numpy.array([scores[0][order]], dtype="float32"), numpy.array([order], dtype="int64")

    def normalize_l2(matrix) -> None:
        norms = numpy.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix /= norms

    return types.SimpleNamespace(IndexFlatIP=IndexFlatIP, normalize_L2=normalize_l2)


def test_search_rows_uses_faiss_index(monkeypatch: pytest.MonkeyPatch) -> None:
    numpy = pytest.importorskip("numpy")
    monkeypatch.setitem(sys.modules, "faiss", _fake_faiss_module(numpy))

    rows = [
        ("alpha", "docs", "alpha content", "{}", "[1.0, 0.0]", None),
        ("beta", "docs", "beta content", "{}", "[0.0, 1.0]", None),
    ]

    matches = search_rows(rows, query_embedding=[1.0, 0.0], top_k=1)

    assert matches is not None
    assert matches[0][0][0] == "alpha"
    assert matches[0][1] > 0.99


def test_search_rows_returns_none_without_faiss(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None):
        if name == "faiss":
            raise ModuleNotFoundError(name)
        return real_import_module(name, package)

    monkeypatch.setattr("src.storage.rag.faiss_backend.importlib.import_module", fake_import_module)

    matches = search_rows([("alpha", "docs", "alpha", "{}", "[1.0]", None)], query_embedding=[1.0], top_k=1)

    assert matches is None


def test_unified_store_prefers_faiss(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = UnifiedRAGStore(tmp_path / "rag.duckdb")
    store.upsert_bootstrap_documents(
        namespace="docs",
        documents=[{"id": "local", "content": "local alpha", "metadata": {"kind": "test"}, "embedding": [1.0, 0.0]}],
    )
    calls = []

    def fake_search_rows(rows, *, query_embedding, top_k):
        calls.append((rows, query_embedding, top_k))
        return [(rows[0], 0.99)]

    monkeypatch.setattr("src.storage.rag.unified_store.search_faiss_rows", fake_search_rows)

    matches = store.search_table("bootstrap_vectors", query_embedding=[1.0, 0.0], namespace="docs", top_k=1)

    assert calls
    assert matches[0].id == "local"
    assert matches[0].metadata["vector_backend"] == "faiss"
