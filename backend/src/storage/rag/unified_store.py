"""Unified DuckDB-backed RAG store for OctoAgent runtime data."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from src.gateway.observability import record_exception_trace
from src.models.embedding_service import get_embedding_service
from src.runtime.config.paths import get_paths
from src.storage.rag.faiss_backend import search_rows as search_faiss_rows

logger = logging.getLogger(__name__)

_DEFAULT_DB_NAME = "octoagent_rag.duckdb"


@dataclass
class RAGMatch:
    id: str
    namespace: str
    content: str
    metadata: dict[str, Any]
    score: float = 0.0
    agent_name: str | None = None


class UnifiedRAGStore:
    """Single vector database and embedding entry point for RAG."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or get_paths().runtime_root / "memory" / _DEFAULT_DB_NAME
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._embedding = get_embedding_service()
        self._initialize()

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def embedding_dim(self) -> int:
        return self._embedding.dim

    @property
    def embedding_backend(self) -> str:
        return self._embedding.backend_name

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self._db_path))

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_memories (
                    id VARCHAR PRIMARY KEY,
                    namespace VARCHAR NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    embedding_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    agent_name VARCHAR
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sm_namespace ON system_memories(namespace)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bootstrap_vectors (
                    id VARCHAR PRIMARY KEY,
                    namespace VARCHAR NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    embedding_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bv_namespace ON bootstrap_vectors(namespace)")

    def embed_one(self, text: str) -> list[float]:
        return self._embedding.embed_one(text)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._embedding.embed(texts)

    async def aembed_one(self, text: str) -> list[float]:
        """Async wrapper: offloads sentence-transformers to a worker thread
        so callers in the LangGraph event loop do not stall."""
        import asyncio

        return await asyncio.to_thread(self._embedding.embed_one, text)

    async def aembed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        return await asyncio.to_thread(self._embedding.embed, texts)

    def list_rows(
        self,
        table: str,
        *,
        namespace: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """Return raw rows for BM25/text-only ranking.

        Best-effort; returns at most ``limit`` rows ordered by recency for
        the caller to feed into BM25. Supported tables: ``system_memories``
        and ``bootstrap_vectors``.
        """
        if table not in {"system_memories", "bootstrap_vectors"}:
            return []
        conn = self._connect()
        try:
            try:
                if table == "system_memories":
                    if namespace:
                        rows = conn.execute(
                            "SELECT id, namespace, content FROM system_memories WHERE namespace = ? ORDER BY rowid DESC LIMIT ?",
                            [namespace, int(limit)],
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            "SELECT id, namespace, content FROM system_memories ORDER BY rowid DESC LIMIT ?",
                            [int(limit)],
                        ).fetchall()
                elif namespace:
                    rows = conn.execute(
                        "SELECT id, namespace, content FROM bootstrap_vectors WHERE namespace = ? ORDER BY rowid DESC LIMIT ?",
                        [namespace, int(limit)],
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, namespace, content FROM bootstrap_vectors ORDER BY rowid DESC LIMIT ?",
                        [int(limit)],
                    ).fetchall()
            except Exception as exc:
                logger.warning("RAG fallback list_rows failed for table=%s namespace=%s", table, namespace, exc_info=True)
                record_exception_trace("rag.unified_store.list_rows.query", exc, table=table, namespace=namespace)
                return []
            out: list[dict] = []
            for row in rows:
                try:
                    out.append(
                        {
                            "id": str(row[0]),
                            "namespace": str(row[1] or ""),
                            "content": str(row[2] or ""),
                            "metadata": {},
                        }
                    )
                except Exception as exc:
                    logger.debug("RAG row conversion failed for table=%s", table, exc_info=True)
                    record_exception_trace("rag.unified_store.list_rows.row", exc, table=table)
                    continue
            return out
        finally:
            try:
                conn.close()
            except Exception as exc:
                logger.debug("Failed to close RAG DuckDB connection", exc_info=True)
                record_exception_trace("rag.unified_store.close", exc)

    def add_system_memory(
        self,
        *,
        entry_id: str,
        namespace: str,
        content: str,
        metadata: dict[str, Any],
        agent_name: str | None,
    ) -> None:
        embedding = self.embed_one(content)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO system_memories
                    (id, namespace, content, metadata_json, embedding_json, agent_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [entry_id, namespace, content, json.dumps(metadata, ensure_ascii=False), json.dumps(embedding), agent_name],
            )

    def add_system_memories(self, *, items: list[dict[str, Any]], agent_name: str | None) -> None:
        embeddings = self.embed([str(item["content"]) for item in items])
        with self._connect() as conn:
            for item, embedding in zip(items, embeddings, strict=False):
                conn.execute(
                    """
                    INSERT INTO system_memories
                        (id, namespace, content, metadata_json, embedding_json, agent_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        item["id"],
                        item["namespace"],
                        item["content"],
                        json.dumps(item.get("metadata", {}), ensure_ascii=False),
                        json.dumps(embedding),
                        agent_name,
                    ],
                )

    def upsert_bootstrap_documents(self, *, namespace: str, documents: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            for item in documents:
                embedding = item.get("embedding") or self.embed_one(str(item["content"]))
                conn.execute(
                    """
                    INSERT OR REPLACE INTO bootstrap_vectors
                        (id, namespace, content, metadata_json, embedding_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        item["id"],
                        namespace,
                        item["content"],
                        json.dumps(item.get("metadata", {}), ensure_ascii=False),
                        json.dumps(embedding),
                    ],
                )

    def _vector_rows(self, table: str, *, namespace: str | None) -> list[tuple[Any, ...]]:
        with self._connect() as conn:
            if table == "system_memories":
                if namespace:
                    return conn.execute(
                        "SELECT id, namespace, content, metadata_json, embedding_json, agent_name FROM system_memories WHERE namespace = ?",
                        [namespace],
                    ).fetchall()
                return conn.execute(
                    "SELECT id, namespace, content, metadata_json, embedding_json, agent_name FROM system_memories",
                ).fetchall()
            if namespace:
                return conn.execute(
                    "SELECT id, namespace, content, metadata_json, embedding_json, NULL AS agent_name FROM bootstrap_vectors WHERE namespace = ?",
                    [namespace],
                ).fetchall()
            return conn.execute(
                "SELECT id, namespace, content, metadata_json, embedding_json, NULL AS agent_name FROM bootstrap_vectors",
            ).fetchall()

    def _search_faiss(self, table: str, *, query_embedding: list[float], namespace: str | None, top_k: int) -> list[RAGMatch] | None:
        rows = self._vector_rows(table, namespace=namespace)
        hits = search_faiss_rows(rows, query_embedding=query_embedding, top_k=top_k)
        if hits is None:
            return None
        matches = [_row_to_match((row[0], row[1], row[2], row[3], score, row[5])) for row, score in hits]
        for match in matches:
            match.metadata = {**match.metadata, "vector_backend": "faiss"}
        return matches

    def search_table(
        self,
        table: str,
        *,
        query_embedding: list[float],
        namespace: str | None,
        top_k: int,
    ) -> list[RAGMatch]:
        if table not in {"system_memories", "bootstrap_vectors"}:
            raise ValueError(f"Unsupported RAG table: {table}")
        try:
            faiss_matches = self._search_faiss(table, query_embedding=query_embedding, namespace=namespace, top_k=top_k)
            if faiss_matches is not None:
                return faiss_matches
        except Exception as exc:
            logger.debug("FAISS local RAG path failed for table=%s namespace=%s", table, namespace, exc_info=True)
            record_exception_trace("rag.unified_store.search_faiss", exc, table=table, namespace=namespace)

        try:
            return self._search_native(table, query_embedding=query_embedding, namespace=namespace, top_k=top_k)
        except Exception:
            return self._search_python(table, query_embedding=query_embedding, namespace=namespace, top_k=top_k)

    def _search_native(
        self,
        table: str,
        *,
        query_embedding: list[float],
        namespace: str | None,
        top_k: int,
    ) -> list[RAGMatch]:
        query_json = json.dumps(query_embedding)
        with self._connect() as conn:
            if table == "system_memories":
                if namespace:
                    rows = conn.execute(
                        """
                        SELECT id, namespace, content, metadata_json,
                               array_cosine_similarity(
                                   CAST(embedding_json::JSON AS FLOAT[]),
                                   CAST(?::JSON AS FLOAT[])
                               ) AS score,
                               agent_name
                        FROM system_memories
                        WHERE embedding_json IS NOT NULL AND namespace = ?
                        ORDER BY score DESC
                        LIMIT ?
                        """,
                        [query_json, namespace, top_k],
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT id, namespace, content, metadata_json,
                               array_cosine_similarity(
                                   CAST(embedding_json::JSON AS FLOAT[]),
                                   CAST(?::JSON AS FLOAT[])
                               ) AS score,
                               agent_name
                        FROM system_memories
                        WHERE embedding_json IS NOT NULL
                        ORDER BY score DESC
                        LIMIT ?
                        """,
                        [query_json, top_k],
                    ).fetchall()
            elif namespace:
                rows = conn.execute(
                    """
                    SELECT id, namespace, content, metadata_json,
                           array_cosine_similarity(
                               CAST(embedding_json::JSON AS FLOAT[]),
                               CAST(?::JSON AS FLOAT[])
                           ) AS score,
                           NULL AS agent_name
                    FROM bootstrap_vectors
                    WHERE embedding_json IS NOT NULL AND namespace = ?
                    ORDER BY score DESC
                    LIMIT ?
                    """,
                    [query_json, namespace, top_k],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, namespace, content, metadata_json,
                           array_cosine_similarity(
                               CAST(embedding_json::JSON AS FLOAT[]),
                               CAST(?::JSON AS FLOAT[])
                           ) AS score,
                           NULL AS agent_name
                    FROM bootstrap_vectors
                    WHERE embedding_json IS NOT NULL
                    ORDER BY score DESC
                    LIMIT ?
                    """,
                    [query_json, top_k],
                ).fetchall()
        return [_row_to_match(row) for row in rows]

    def _search_python(
        self,
        table: str,
        *,
        query_embedding: list[float],
        namespace: str | None,
        top_k: int,
    ) -> list[RAGMatch]:
        rows = self._vector_rows(table, namespace=namespace)
        results: list[RAGMatch] = []
        for row in rows:
            if not row[4]:
                continue
            score = _cosine_similarity(query_embedding, json.loads(row[4]))
            results.append(_row_to_match((row[0], row[1], row[2], row[3], score, row[5])))
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]

    def bootstrap_stats(self) -> dict[str, int]:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS total, COUNT(DISTINCT namespace) AS namespaces FROM bootstrap_vectors").fetchone()
        return {"documents": int(row[0]) if row else 0, "namespaces": int(row[1]) if row else 0}


def _row_to_match(row: tuple[Any, ...]) -> RAGMatch:
    metadata = {}
    if row[3]:
        try:
            loaded = json.loads(row[3])
            metadata = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            metadata = {}
    return RAGMatch(
        id=str(row[0]),
        namespace=str(row[1]),
        content=str(row[2]),
        metadata=metadata,
        score=float(row[4] or 0.0),
        agent_name=str(row[5]) if len(row) > 5 and row[5] else None,
    )


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


_store: UnifiedRAGStore | None = None


def get_unified_rag_store() -> UnifiedRAGStore:
    global _store
    if _store is None:
        _store = UnifiedRAGStore()
    return _store
