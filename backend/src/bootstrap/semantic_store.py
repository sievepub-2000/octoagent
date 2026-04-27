"""DuckDB-backed lightweight semantic store for bootstrap retrieval.

Uses DuckDB's native array_cosine_similarity for efficient vector search
and the unified EmbeddingService for real neural embeddings.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


@dataclass
class SemanticMatch:
    id: str
    namespace: str
    content: str
    metadata: dict[str, Any]
    score: float


class BootstrapSemanticStore:
    """A tiny persistent semantic store optimized for bootstrap/onboarding data."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        return duckdb.connect(str(self._db_path))

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bootstrap_vectors (
                    id VARCHAR PRIMARY KEY,
                    namespace VARCHAR,
                    content TEXT,
                    metadata_json TEXT,
                    embedding_json TEXT
                )
                """
            )

    def stats(self) -> dict[str, int]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total, COUNT(DISTINCT namespace) AS namespaces FROM bootstrap_vectors"
            ).fetchone()
        total = int(row[0]) if row else 0
        namespaces = int(row[1]) if row else 0
        return {"documents": total, "namespaces": namespaces}

    def upsert_documents(
        self,
        namespace: str,
        documents: list[dict[str, Any]],
    ) -> None:
        with self._connect() as conn:
            for item in documents:
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
                        json.dumps(item["embedding"]),
                    ],
                )

    def search(
        self,
        *,
        namespace: str,
        query_embedding: list[float],
        top_k: int,
    ) -> list[SemanticMatch]:
        """Search for similar documents using DuckDB array_cosine_similarity.

        Falls back to Python-level cosine similarity if the DuckDB function
        is unavailable (e.g. older DuckDB version or dimension mismatch).
        """
        try:
            return self._search_native(
                namespace=namespace, query_embedding=query_embedding, top_k=top_k,
            )
        except Exception:
            logger.debug("Native vector search unavailable, using Python fallback", exc_info=True)
            return self._search_python(
                namespace=namespace, query_embedding=query_embedding, top_k=top_k,
            )

    def _search_native(
        self,
        *,
        namespace: str,
        query_embedding: list[float],
        top_k: int,
    ) -> list[SemanticMatch]:
        """Use DuckDB's built-in array_cosine_similarity (DuckDB ≥ 1.1)."""
        query_json = json.dumps(query_embedding)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, namespace, content, metadata_json,
                       array_cosine_similarity(
                           CAST(embedding_json::JSON AS FLOAT[]),
                           CAST(?::JSON AS FLOAT[])
                       ) AS score
                FROM bootstrap_vectors
                WHERE namespace = ?
                ORDER BY score DESC
                LIMIT ?
                """,
                [query_json, namespace, top_k],
            ).fetchall()

        return [
            SemanticMatch(
                id=row[0],
                namespace=row[1],
                content=row[2],
                metadata=json.loads(row[3]) if row[3] else {},
                score=float(row[4]),
            )
            for row in rows
        ]

    def _search_python(
        self,
        *,
        namespace: str,
        query_embedding: list[float],
        top_k: int,
    ) -> list[SemanticMatch]:
        """Fallback: Python-level cosine similarity comparison."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, namespace, content, metadata_json, embedding_json
                FROM bootstrap_vectors
                WHERE namespace = ?
                """,
                [namespace],
            ).fetchall()

        results: list[SemanticMatch] = []
        for row in rows:
            embedding = json.loads(row[4])
            score = _cosine_similarity(query_embedding, embedding)
            results.append(
                SemanticMatch(
                    id=row[0],
                    namespace=row[1],
                    content=row[2],
                    metadata=json.loads(row[3]) if row[3] else {},
                    score=score,
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    numerator = sum(x * y for x, y in zip(a, b, strict=False))
    denominator_a = math.sqrt(sum(x * x for x in a))
    denominator_b = math.sqrt(sum(y * y for y in b))
    if denominator_a == 0 or denominator_b == 0:
        return 0.0
    return numerator / (denominator_a * denominator_b)
