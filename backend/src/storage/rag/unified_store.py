"""Unified DuckDB-backed RAG store for OctoAgent runtime data."""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
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


_DUCKDB_SERIALIZE_ENV = "OCTOAGENT_DUCKDB_SERIALIZE"
_SERIALIZE_ACQUIRE_ATTEMPTS = 80
_SERIALIZE_ACQUIRE_DELAY = 0.1


def _duckdb_serialize_enabled() -> bool:
    """Single-writer convergence. Default ON; set OCTOAGENT_DUCKDB_SERIALIZE=0 to opt out (retry-only)."""
    return os.getenv(_DUCKDB_SERIALIZE_ENV, "1").strip().lower() in {"1", "true", "yes", "on"}


class _GuardedDuckDBConnection:
    """Wrap a DuckDB connection so the process-level advisory lock is released
    exactly once when the connection is closed (via ``with`` or ``.close()``).

    Transparent proxy: every other attribute (``execute``, ``executemany`` ...)
    is delegated to the underlying connection.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection, release) -> None:
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_release", release)
        object.__setattr__(self, "_released", False)

    def _do_release(self) -> None:
        if not object.__getattribute__(self, "_released"):
            object.__setattr__(self, "_released", True)
            object.__getattribute__(self, "_release")()

    def __enter__(self) -> _GuardedDuckDBConnection:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            object.__getattribute__(self, "_conn").close()
        finally:
            self._do_release()
        return False

    def close(self) -> None:
        try:
            object.__getattribute__(self, "_conn").close()
        finally:
            self._do_release()

    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, "_conn"), name)


def _open_duckdb_with_retry(
    db_path: str | Path,
    *,
    read_only: bool,
    attempts: int,
    base_delay: float,
    max_delay: float,
) -> duckdb.DuckDBPyConnection:
    import time as _time

    delay = base_delay
    last_exc: Exception | None = None
    for _ in range(attempts):
        try:
            return duckdb.connect(str(db_path), read_only=read_only)
        except Exception as exc:  # noqa: BLE001 - inspect message for lock contention
            msg = str(exc).lower()
            if "lock" not in msg and "conflicting" not in msg:
                raise
            last_exc = exc
            _time.sleep(delay)
            delay = min(delay * 2, max_delay)
    assert last_exc is not None
    logger.warning("duckdb lock contention persisted after retries: %s", last_exc)
    raise last_exc


def connect_duckdb_with_retry(
    db_path: str | Path,
    *,
    read_only: bool = False,
    attempts: int = 6,
    base_delay: float = 0.25,
    max_delay: float = 2.0,
):
    """Open a DuckDB connection on the shared RAG database.

    Default: retry with exponential backoff on cross-process file-lock contention
    (was: silent data loss on SimpleMemBridge store.add / system-memory writes).

    When ``OCTOAGENT_DUCKDB_SERIALIZE`` is enabled, additionally serialize access
    across processes with an advisory readers-writer file lock (shared for
    ``read_only``, exclusive otherwise): a true single-writer-at-a-time
    convergence that removes the contention entirely. Deadlock-proof: lock
    acquisition is non-blocking with a bounded retry budget, then falls through
    to a plain (retrying) connect so it can never hang the agent loop.
    """
    if not _duckdb_serialize_enabled():
        return _open_duckdb_with_retry(db_path, read_only=read_only, attempts=attempts, base_delay=base_delay, max_delay=max_delay)

    try:
        import fcntl
    except ImportError:  # non-POSIX: fall back to retry-only
        return _open_duckdb_with_retry(db_path, read_only=read_only, attempts=attempts, base_delay=base_delay, max_delay=max_delay)

    import time as _time

    lock_path = str(db_path) + ".rwlock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    except OSError:
        return _open_duckdb_with_retry(db_path, read_only=read_only, attempts=attempts, base_delay=base_delay, max_delay=max_delay)

    lock_type = fcntl.LOCK_SH if read_only else fcntl.LOCK_EX
    acquired = False
    for _ in range(_SERIALIZE_ACQUIRE_ATTEMPTS):
        try:
            fcntl.flock(fd, lock_type | fcntl.LOCK_NB)
            acquired = True
            break
        except OSError:
            _time.sleep(_SERIALIZE_ACQUIRE_DELAY)
    if not acquired:
        logger.warning("duckdb serialize: could not acquire %s lock, proceeding with retry-only", "read" if read_only else "write")

    try:
        conn = _open_duckdb_with_retry(db_path, read_only=read_only, attempts=attempts, base_delay=base_delay, max_delay=max_delay)
    except Exception:
        with contextlib.suppress(Exception):
            if acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
        with contextlib.suppress(Exception):
            os.close(fd)
        raise

    def _release() -> None:
        with contextlib.suppress(Exception):
            if acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
        with contextlib.suppress(Exception):
            os.close(fd)

    return _GuardedDuckDBConnection(conn, _release)


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
        return connect_duckdb_with_retry(self._db_path)

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
