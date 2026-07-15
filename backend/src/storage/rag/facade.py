"""Unified RAG facade — single entry point, dispatched by table name.

Sprint-2 P0: all RAG callers should go through ``unified_search(table=..., ...)``.

Built-in tables (registered on import):
  - ``system_memories``  : UnifiedRAGStore (DuckDB, vector cosine)
  - ``bootstrap_vectors``: UnifiedRAGStore (DuckDB, vector cosine)
  - ``lessons``          : LessonsStore (SQLite, BM25 over recent window)
  - ``skills``           : SkillCatalog (BM25 over description+body)
  - ``tools``            : ToolCatalog (BM25 over name+description)

Async-friendly: every handler is blocking I/O (sqlite/duckdb/BM25 +
sentence-transformers embedding) so ``aunified_search`` offloads to a thread
via ``asyncio.to_thread``. This is the canonical way to avoid stalling the
LangGraph event loop without enabling its unsafe blocking-I/O escape hatch.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from src.models.reranker_service import get_reranker_service, reranker_enabled
from src.storage.rag.bm25_backend import bm25_search
from src.storage.rag.unified_store import RAGMatch, get_unified_rag_store

logger = logging.getLogger(__name__)

SearchMode = Literal["vector", "bm25", "hybrid"]


@dataclass
class RAGEntry:
    id: str
    table: str
    content: str
    score: float
    namespace: str | None = None
    metadata: dict[str, Any] | None = None


TableHandler = Callable[[str, str | None, int, SearchMode], list[RAGEntry]]

_TABLES: dict[str, TableHandler] = {}
_TABLES_LOCK = threading.Lock()


def register_table(name: str, handler: TableHandler) -> None:
    with _TABLES_LOCK:
        _TABLES[name] = handler
    logger.debug("RAG: registered table handler '%s'", name)


def registered_tables() -> list[str]:
    with _TABLES_LOCK:
        return sorted(_TABLES.keys())


def unified_search(
    *,
    table: str,
    query: str,
    namespace: str | None = None,
    top_k: int = 10,
    mode: SearchMode = "hybrid",
) -> list[RAGEntry]:
    """Synchronous unified search entry point.

    Prefer ``aunified_search`` from async contexts (LangGraph / FastAPI) so the
    embedding + DB calls do not block the event loop.
    """
    handler = _TABLES.get(table)
    if handler is None:
        raise KeyError(f"RAG table '{table}' is not registered; known tables: {registered_tables()}")
    if top_k <= 0:
        return []
    try:
        return handler(query, namespace, int(top_k), mode)
    except Exception as exc:
        logger.warning("unified_search failed for table=%s: %s", table, exc)
        return []


async def aunified_search(
    *,
    table: str,
    query: str,
    namespace: str | None = None,
    top_k: int = 10,
    mode: SearchMode = "hybrid",
) -> list[RAGEntry]:
    """Async wrapper: offloads the blocking handler to a worker thread.

    Critical: never call ``unified_search`` directly from an event-loop
    coroutine — sentence-transformers ``encode()`` holds the GIL for tens of
    milliseconds and DuckDB's ``execute()`` is fully synchronous. Both would
    stall the LangGraph queue if they were not moved to a worker thread.
    """
    return await asyncio.to_thread(unified_search, table=table, query=query, namespace=namespace, top_k=top_k, mode=mode)


# ── Default handlers ────────────────────────────────────────────────────────


def _vector_match_to_entry(table: str, match: RAGMatch) -> RAGEntry:
    return RAGEntry(
        id=match.id,
        table=table,
        content=match.content,
        score=float(match.score),
        namespace=match.namespace,
        metadata=match.metadata or {},
    )


def _vector_search(table: str, query: str, namespace: str | None, top_k: int) -> list[RAGEntry]:
    store = get_unified_rag_store()
    q_emb = store.embed_one(query)
    matches = store.search_table(table, query_embedding=q_emb, namespace=namespace, top_k=top_k)
    return [_vector_match_to_entry(table, m) for m in matches]


def _list_rows_for_bm25(table: str, namespace: str | None, limit: int) -> list[dict[str, Any]]:
    """Pull rows from the unified store for BM25 ranking. Best-effort: only
    runs when the store exposes a ``list_rows`` helper; otherwise returns
    an empty list and the hybrid mode degrades to pure vector.
    """
    store = get_unified_rag_store()
    fn = getattr(store, "list_rows", None)
    if not callable(fn):
        return []
    try:
        return list(fn(table, namespace=namespace, limit=limit)) or []
    except Exception as exc:  # pragma: no cover
        logger.debug("list_rows(%s) failed: %s", table, exc)
        return []


def _rrf_merge(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal-rank fusion: each ranking contributes 1/(k + rank)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def _hybrid_vector_table(table: str, query: str, namespace: str | None, top_k: int) -> list[RAGEntry]:
    """Vector search ∪ BM25 over recent rows, fused with RRF."""
    over_fetch = max(top_k * 4, 20)
    vec_entries = _vector_search(table, query, namespace, over_fetch)
    rows = _list_rows_for_bm25(table, namespace, over_fetch * 2)
    if not rows:
        # No BM25 corpus available — return vector results trimmed to top_k.
        return vec_entries[:top_k]
    doc_ids = [str(r.get("id")) for r in rows]
    documents = [str(r.get("content", "")) for r in rows]
    bm25_hits = bm25_search(query=query, doc_ids=doc_ids, documents=documents, top_k=over_fetch)
    bm25_ids = [d for d, _ in bm25_hits]
    vec_ids = [e.id for e in vec_entries]
    fused = _rrf_merge([vec_ids, bm25_ids])
    # Stitch full entry payloads (prefer vector entry; fall back to BM25 row).
    by_id_vec: dict[str, RAGEntry] = {e.id: e for e in vec_entries}
    by_id_row: dict[str, dict[str, Any]] = {str(r.get("id")): r for r in rows}
    # Optional second-stage cross-encoder rerank.
    if reranker_enabled():
        # Build candidate pool from over-fetched results (~over_fetch deep).
        cand_pool: dict[str, str] = {}
        for e in vec_entries:
            cand_pool[e.id] = e.content
        for doc_id, _ in bm25_hits:
            if doc_id not in cand_pool:
                r = by_id_row.get(doc_id)
                if r is not None:
                    cand_pool[doc_id] = str(r.get("content", ""))
        ranked = get_reranker_service().rerank(
            query=query,
            candidates=[(did, txt) for did, txt in cand_pool.items()],
            top_k=top_k,
        )
        out: list[RAGEntry] = []
        for doc_id, rerank_score in ranked:
            if doc_id in by_id_vec:
                e = by_id_vec[doc_id]
                out.append(
                    RAGEntry(
                        id=e.id,
                        table=e.table,
                        content=e.content,
                        score=rerank_score,
                        namespace=e.namespace,
                        metadata={**e.metadata, "fused_score": fused.get(doc_id, 0.0), "vector_score": e.score, "rerank_score": rerank_score},
                    )
                )
            else:
                r = by_id_row.get(doc_id, {})
                out.append(
                    RAGEntry(
                        id=doc_id,
                        table=table,
                        content=str(r.get("content", "")),
                        score=rerank_score,
                        namespace=str(r.get("namespace", namespace or "")),
                        metadata={**(r.get("metadata") or {}), "fused_score": fused.get(doc_id, 0.0), "rerank_score": rerank_score, "source": "bm25_only"},
                    )
                )
        return out

    out: list[RAGEntry] = []
    for doc_id, fused_score in sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]:
        if doc_id in by_id_vec:
            entry = by_id_vec[doc_id]
            out.append(
                RAGEntry(
                    id=entry.id,
                    table=entry.table,
                    content=entry.content,
                    score=fused_score,
                    namespace=entry.namespace,
                    metadata={**entry.metadata, "fused_score": fused_score, "vector_score": entry.score},
                )
            )
        elif doc_id in by_id_row:
            r = by_id_row[doc_id]
            out.append(
                RAGEntry(
                    id=doc_id,
                    table=table,
                    content=str(r.get("content", "")),
                    score=fused_score,
                    namespace=str(r.get("namespace", namespace or "")),
                    metadata={**(r.get("metadata") or {}), "fused_score": fused_score, "source": "bm25_only"},
                )
            )
    return out


def _bm25_only_vector_table(table: str, query: str, namespace: str | None, top_k: int) -> list[RAGEntry]:
    rows = _list_rows_for_bm25(table, namespace, max(top_k * 8, 80))
    if not rows:
        return []
    doc_ids = [str(r.get("id")) for r in rows]
    documents = [str(r.get("content", "")) for r in rows]
    hits = bm25_search(query=query, doc_ids=doc_ids, documents=documents, top_k=top_k)
    by_id = {str(r.get("id")): r for r in rows}
    out: list[RAGEntry] = []
    for doc_id, score in hits:
        r = by_id.get(doc_id)
        if r is None:
            continue
        out.append(
            RAGEntry(
                id=doc_id,
                table=table,
                content=str(r.get("content", "")),
                score=score,
                namespace=str(r.get("namespace", namespace or "")),
                metadata=r.get("metadata") or {},
            )
        )
    return out


def _system_memories_handler(query: str, namespace: str | None, top_k: int, mode: SearchMode) -> list[RAGEntry]:
    if mode == "bm25":
        result = _bm25_only_vector_table("system_memories", query, namespace, top_k)
        if result:
            return result
        # Empty BM25 corpus → fall back to vector so callers always get something.
    if mode == "hybrid":
        return _hybrid_vector_table("system_memories", query, namespace, top_k)
    return _vector_search("system_memories", query, namespace, top_k)


def _bootstrap_vectors_handler(query: str, namespace: str | None, top_k: int, mode: SearchMode) -> list[RAGEntry]:
    if mode == "bm25":
        result = _bm25_only_vector_table("bootstrap_vectors", query, namespace, top_k)
        if result:
            return result
    if mode == "hybrid":
        return _hybrid_vector_table("bootstrap_vectors", query, namespace, top_k)
    return _vector_search("bootstrap_vectors", query, namespace, top_k)


def _lessons_handler(query: str, namespace: str | None, top_k: int, mode: SearchMode) -> list[RAGEntry]:
    from src.storage.self_evolution.lessons import LessonsStore

    store = LessonsStore.default()
    rows = store.recent(limit=max(top_k * 4, 50))
    if not rows:
        return []
    doc_ids = [str(r.get("id")) for r in rows]
    documents = [" ".join(str(r.get(field) or "") for field in ("pattern", "root_cause", "fix")) for r in rows]
    ranked = bm25_search(doc_ids, documents, query, top_k=top_k)
    by_id = {str(r.get("id")): r for r in rows}
    return [
        RAGEntry(
            id=str(rid),
            table="lessons",
            content=by_id[rid].get("pattern", ""),
            score=score,
            namespace=by_id[rid].get("category"),
            metadata={
                "root_cause": by_id[rid].get("root_cause"),
                "fix": by_id[rid].get("fix"),
                "severity": by_id[rid].get("severity"),
                "ts": by_id[rid].get("ts"),
            },
        )
        for rid, score in ranked
    ]


def _skills_handler(query: str, namespace: str | None, top_k: int, mode: SearchMode) -> list[RAGEntry]:
    try:
        from src.storage.skills import load_skills
    except Exception:
        return []
    try:
        skills = load_skills() or []
    except Exception:
        return []
    if not skills:
        return []
    doc_ids: list[str] = []
    documents: list[str] = []
    by_id: dict[str, Any] = {}
    for s in skills:
        sid = getattr(s, "name", None) or getattr(s, "id", None) or str(id(s))
        desc = getattr(s, "description", "") or getattr(s, "summary", "") or ""
        content_attr = getattr(s, "content", None) or getattr(s, "body", None) or ""
        body = str(content_attr)[:1500]
        doc_ids.append(str(sid))
        documents.append(f"{desc}\n{body}")
        by_id[str(sid)] = s
    ranked = bm25_search(doc_ids, documents, query, top_k=top_k)
    return [
        RAGEntry(
            id=str(rid),
            table="skills",
            content=(getattr(by_id[rid], "description", "") or str(rid)),
            score=score,
            metadata={"name": rid},
        )
        for rid, score in ranked
    ]


def _tools_handler(query: str, namespace: str | None, top_k: int, mode: SearchMode) -> list[RAGEntry]:
    from src.tools.catalog import BUILTIN_TOOLS_CORE

    if not BUILTIN_TOOLS_CORE:
        return []
    doc_ids = [t.name for t in BUILTIN_TOOLS_CORE]
    documents = [(t.description or "") for t in BUILTIN_TOOLS_CORE]
    ranked = bm25_search(doc_ids, documents, query, top_k=top_k)
    by_id = {t.name: t for t in BUILTIN_TOOLS_CORE}
    return [
        RAGEntry(
            id=name,
            table="tools",
            content=by_id[name].description or "",
            score=score,
            metadata={"tool_name": name},
        )
        for name, score in ranked
    ]


# Auto-register at import.
register_table("system_memories", _system_memories_handler)
register_table("bootstrap_vectors", _bootstrap_vectors_handler)
register_table("lessons", _lessons_handler)
register_table("skills", _skills_handler)
register_table("tools", _tools_handler)


__all__ = [
    "RAGEntry",
    "SearchMode",
    "register_table",
    "registered_tables",
    "unified_search",
    "aunified_search",
]
