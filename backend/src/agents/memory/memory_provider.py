"""Memory provider pattern — pluggable storage backends for memory entries.

Provides a structural-typing Protocol so any object exposing the required
methods can serve as a memory backend without explicit inheritance.  Two
reference implementations ship with this module: SQLite-backed (production)
and in-memory (testing/dev).
"""

import json
import logging
import sqlite3
import struct
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemoryEntry:
    """Immutable memory entry stored by any provider."""

    id: str
    content: str
    category: str  # task_result | user_preference | system_state | skill_learned
    timestamp: datetime
    embedding: list[float] | None = field(default=None, repr=False)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        content: str,
        category: str,
        *,
        entry_id: str | None = None,
        embedding: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> "MemoryEntry":
        return cls(
            id=entry_id or uuid.uuid4().hex,
            content=content,
            category=category,
            timestamp=timestamp or datetime.now(UTC),
            embedding=embedding,
            metadata=metadata or {},
        )


# ---------------------------------------------------------------------------
# Protocol (structural typing — no explicit inheritance required)
# ---------------------------------------------------------------------------


class MemoryProvider(Protocol):
    """Interface for memory storage backends."""

    async def store(self, entry: MemoryEntry) -> None: ...

    async def retrieve(self, query: str, top_k: int = 5) -> list[MemoryEntry]: ...

    async def update(self, entry_id: str, updates: dict[str, Any]) -> None: ...

    async def delete(self, entry_id: str) -> None: ...

    async def search_similar(self, embedding: list[float], top_k: int = 5) -> list[MemoryEntry]: ...


# ---------------------------------------------------------------------------
# In-memory provider (testing / dev fallback — no persistence)
# ---------------------------------------------------------------------------


class InMemoryMemoryProvider:
    """Non-persistent in-memory store. Useful for tests and development."""

    def __init__(self) -> None:
        self._store: dict[str, MemoryEntry] = {}

    async def store(self, entry: MemoryEntry) -> None:
        self._store[entry.id] = entry

    async def retrieve(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        results: list[MemoryEntry] = []
        q_lower = query.lower()
        for entry in self._store.values():
            if q_lower in entry.content.lower():
                results.append(entry)
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[:top_k]

    async def update(self, entry_id: str, updates: dict[str, Any]) -> None:
        existing = self._store.get(entry_id)
        if existing is None:
            raise KeyError(f"MemoryEntry {entry_id} not found")
        mutable = _as_mutable(existing)
        for key, value in updates.items():
            setattr(mutable, key, value)
        self._store[entry_id] = MemoryEntry(
            id=mutable.id,
            content=mutable.content,
            category=mutable.category,
            timestamp=mutable.timestamp,
            embedding=mutable.embedding,
            metadata=mutable.metadata,
        )

    async def delete(self, entry_id: str) -> None:
        self._store.pop(entry_id, None)

    async def search_similar(self, embedding: list[float], top_k: int = 5) -> list[MemoryEntry]:
        # Without a real vector index we fall back to keyword overlap.
        return await self.retrieve(" ".join(str(t) for t in embedding[:10]), top_k)

    async def all(self) -> list[MemoryEntry]:
        return list(self._store.values())


# ---------------------------------------------------------------------------
# SQLite provider (production — FTS5 + optional vector column)
# ---------------------------------------------------------------------------


class SQLiteMemoryProvider:
    """SQLite-backed memory provider with FTS5 full-text search.

    Embeddings are stored as a BLOB (packed float32 array).  Cosine similarity
    is computed in Python after an initial keyword pre-filter via FTS5 so the
    database stays lightweight even without a vector extension.
    """

    def __init__(self, db_path: str = "octoagent_memory.db") -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._setup()

    # ------------------------------------------------------------------ init

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            with self._lock:
                if self._conn is None:
                    conn = sqlite3.connect(self._db_path)
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA foreign_keys=ON")
                    self._conn = conn
        return self._conn

    def _setup(self) -> None:
        conn = self._get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_entries (
                id          TEXT PRIMARY KEY,
                content     TEXT NOT NULL,
                category    TEXT NOT NULL,
                timestamp   TEXT NOT NULL,
                embedding   BLOB,
                metadata    TEXT NOT NULL DEFAULT '{}'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                content,
                category,
                tokenize='unicode61'
            );

            CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory_entries BEGIN
                INSERT INTO memory_fts(rowid, content, category) VALUES (new.rowid, new.content, new.category);
            END;

            CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory_entries BEGIN
                DELETE FROM memory_fts WHERE rowid = old.rowid;
            END;

            CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory_entries BEGIN
                INSERT INTO memory_fts(memory_fts, rowid, content, category) VALUES('delete', old.rowid, old.content, old.category);
                INSERT INTO memory_fts(memory_fts, rowid, content, category) VALUES('insert', new.rowid, new.content, new.category);
            END;
            """
        )

    # ------------------------------------------------------------------ helpers

    def _entry_from_row(self, row: tuple) -> MemoryEntry:
        rid, content, category, ts_str, emb_blob, meta_str = row
        embedding: list[float] | None = None
        if emb_blob is not None:
            try:
                embedding = list(struct.unpack(f"<{len(emb_blob) // 4}f", emb_blob))
            except Exception:
                logger.warning("Failed to unpack embedding blob for %s", rid, exc_info=True)
        metadata: dict[str, Any] = {}
        if meta_str:
            try:
                metadata = json.loads(meta_str)
            except Exception:
                pass
        return MemoryEntry(
            id=rid,
            content=content,
            category=category,
            timestamp=datetime.fromisoformat(ts_str),
            embedding=embedding,
            metadata=metadata,
        )

    def _pack_embedding(self, embedding: list[float]) -> bytes | None:
        if embedding is None:
            return None
        return struct.pack(f"<{len(embedding)}f", *embedding)

    # ------------------------------------------------------------------ API

    async def store(self, entry: MemoryEntry) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO memory_entries
                (id, content, category, timestamp, embedding, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                entry.content,
                entry.category,
                entry.timestamp.isoformat(),
                self._pack_embedding(entry.embedding),
                json.dumps(entry.metadata),
            ),
        )
        conn.commit()

    async def retrieve(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        conn = self._get_conn()
        cursor = conn.execute(
            """
            SELECT e.id, e.content, e.category, e.timestamp, e.embedding, e.metadata
            FROM memory_entries e
            JOIN memory_fts f ON f.rowid = e.rowid
            WHERE memory_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, top_k),
        )
        return [self._entry_from_row(r) for r in cursor.fetchall()]

    async def update(self, entry_id: str, updates: dict[str, Any]) -> None:
        conn = self._get_conn()
        allowed = {"content", "category", "embedding", "metadata"}
        sets: list[str] = []
        values: list[Any] = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key == "embedding":
                sets.append("embedding = ?")
                values.append(self._pack_embedding(value))
            elif key == "metadata":
                sets.append("metadata = ?")
                values.append(json.dumps(value))
            else:
                sets.append(f"{key} = ?")
                values.append(value)
        if not sets:
            return
        values.append(entry_id)
        conn.execute(
            f"UPDATE memory_entries SET {', '.join(sets)} WHERE id = ?",
            values,
        )
        conn.commit()

    async def delete(self, entry_id: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM memory_entries WHERE id = ?", (entry_id,))
        conn.commit()

    async def search_similar(self, embedding: list[float], top_k: int = 5) -> list[MemoryEntry]:
        conn = self._get_conn()
        cursor = conn.execute(
            """
            SELECT id, content, category, timestamp, embedding, metadata
            FROM memory_entries
            WHERE embedding IS NOT NULL
            LIMIT 200
            """
        )
        rows = cursor.fetchall()
        if not rows:
            return []

        target = _normalize(embedding)
        scored: list[tuple[float, MemoryEntry]] = []
        for row in rows:
            _, _, _, _, emb_blob, _ = row
            if emb_blob is None:
                continue
            try:
                stored = list(struct.unpack(f"<{len(emb_blob) // 4}f", emb_blob))
                stored_norm = _normalize(stored)
                cosine = sum(a * b for a, b in zip(target, stored_norm))
                scored.append((cosine, self._entry_from_row(row)))
            except Exception:
                continue

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]

    async def all(self) -> list[MemoryEntry]:
        conn = self._get_conn()
        cursor = conn.execute("SELECT id, content, category, timestamp, embedding, metadata FROM memory_entries")
        return [self._entry_from_row(r) for r in cursor.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize(vec: list[float]) -> list[float]:
    """L2-normalise a vector for cosine similarity."""
    magnitude = sum(v * v for v in vec) ** 0.5
    if magnitude == 0:
        return [0.0] * len(vec)
    return [v / magnitude for v in vec]


def _as_mutable(entry: MemoryEntry):
    """Return a mutable copy of an immutable MemoryEntry for update()."""

    @dataclass
    class MutableMemoryEntry:
        id: str = ""
        content: str = ""
        category: str = ""
        timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
        embedding: list[float] | None = None
        metadata: dict[str, Any] = field(default_factory=dict)

    return MutableMemoryEntry(
        id=entry.id,
        content=entry.content,
        category=entry.category,
        timestamp=entry.timestamp,
        embedding=entry.embedding,
        metadata=entry.metadata.copy(),
    )


__all__ = [
    "MemoryEntry",
    "MemoryProvider",
    "SQLiteMemoryProvider",
    "InMemoryMemoryProvider",
]
