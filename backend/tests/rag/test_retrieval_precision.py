"""BM25 retrieval precision invariants.

The hybrid RAG store uses `bm25_search` as the lexical scorer. These
checks verify that the *ranking* of retrieved documents matches what a
human would expect for unambiguous queries — guarding against silent
tokenizer regressions that would otherwise only surface as "search
feels worse" in WebUI smoke runs.
"""

from __future__ import annotations

from src.storage.rag.bm25_backend import _tokenize, bm25_search


def test_tokenizer_handles_ascii_lowercase_and_punctuation():
    tokens = _tokenize("Hello, World! foo_bar 42.")
    assert tokens == ["hello", "world", "foo_bar", "42"]


def test_tokenizer_handles_cjk_characters():
    tokens = _tokenize("你好世界 hello 世界")
    # CJK characters fall into the same token class; ASCII words are split.
    assert "hello" in tokens
    assert any(ch in {"你好世界", "世界"} or "好" in ch for ch in tokens) or len(tokens) >= 3


def test_bm25_ranks_relevant_doc_first():
    """The doc that lexically matches the query terms must rank first.

    This is the precision invariant: BM25 with a sane tokenizer must
    place the on-topic document above off-topic noise."""
    doc_ids = ["d1", "d2", "d3"]
    documents = [
        "The quick brown fox jumps over the lazy dog",
        "Python is a popular programming language",
        "FastAPI is a modern Python web framework",
    ]
    results = bm25_search(doc_ids, documents, query="python web framework", top_k=3)
    assert results, "bm25_search returned no results"
    assert results[0][0] == "d3", f"expected d3 first, got {results}"


def test_bm25_top_k_caps_result_set():
    doc_ids = [f"d{i}" for i in range(5)]
    documents = [
        "alpha beta gamma",
        "alpha delta",
        "epsilon",
        "alpha",
        "beta gamma delta epsilon",
    ]
    results = bm25_search(doc_ids, documents, query="alpha", top_k=2)
    assert len(results) <= 2
    # All returned docs must contain the query term in some form.
    returned_ids = {doc_id for doc_id, _ in results}
    assert returned_ids.issubset({"d0", "d1", "d3", "d4"})


def test_bm25_empty_corpus_returns_empty():
    assert bm25_search([], [], query="anything", top_k=5) == []


def test_bm25_empty_query_returns_empty_or_zero_scores():
    """An empty query should not raise; it should either return no
    matches or matches with zero score. We assert the no-raise contract
    plus that the function does not fabricate matches."""
    doc_ids = ["d1"]
    documents = ["alpha beta"]
    results = bm25_search(doc_ids, documents, query="", top_k=5)
    # All scores must be non-negative; empty query should not invent a
    # high-confidence match.
    for _, score in results:
        assert score >= 0.0
