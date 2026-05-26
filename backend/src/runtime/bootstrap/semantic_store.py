"""Bootstrap semantic adapter backed by the unified OctoAgent RAG store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.storage.rag import get_unified_rag_store


@dataclass
class SemanticMatch:
    id: str
    namespace: str
    content: str
    metadata: dict[str, Any]
    score: float


class BootstrapSemanticStore:
    """Compatibility adapter for bootstrap data in the unified RAG database."""

    def __init__(self, db_path: Path | None = None):
        self._rag = get_unified_rag_store()
        self._db_path = db_path or self._rag.db_path

    def stats(self) -> dict[str, int]:
        return self._rag.bootstrap_stats()

    def upsert_documents(self, namespace: str, documents: list[dict[str, Any]]) -> None:
        self._rag.upsert_bootstrap_documents(namespace=namespace, documents=documents)

    def search(self, *, namespace: str, query_embedding: list[float], top_k: int) -> list[SemanticMatch]:
        matches = self._rag.search_table(
            "bootstrap_vectors",
            namespace=namespace,
            query_embedding=query_embedding,
            top_k=top_k,
        )
        return [
            SemanticMatch(
                id=item.id,
                namespace=item.namespace,
                content=item.content,
                metadata=item.metadata,
                score=item.score,
            )
            for item in matches
        ]
