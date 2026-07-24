"""Harness-owned durable Markdown memory with a rebuildable pgvector index.

Markdown is the source of truth.  PostgreSQL only contains a derived search
index, so a cold start can always rebuild missing rows without losing memory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_VECTOR_DIM = 384
_EMBEDDING_VERSION = "feature-hash-v1"
_DURABLE_SIGNAL = re.compile(
    r"remember|preference|always|never|must|do not|decision|constraint|result|fixed|"
    r"记住|偏好|必须|不要|决定|约束|结果|修复|以后|始终",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MemoryHit:
    content: str
    score: float
    source_path: str


class HarnessMemory:
    """One durable memory Implementation behind the Harness Interface."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(os.getenv("OCTOAGENT_MEMORY_ROOT", "/app/runtime/memory"))
        self._lock = threading.RLock()
        self._schema_ready = False

    def initialize(self) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        indexed = 0
        failed = 0
        recovered = 0
        for raw in self.root.glob("*/*.raw.md"):
            memory_source = raw.with_name(raw.name.removesuffix(".raw.md") + ".memory.md")
            if memory_source.exists():
                continue
            try:
                transcript = raw.read_text(encoding="utf-8")
                self._atomic_write(
                    memory_source,
                    "# Extracted memory\n\n- Recovered transcript: " + transcript[-6000:] + "\n",
                )
                recovered += 1
            except Exception:
                failed += 1
                logger.exception("Memory extraction recovery failed for %s", raw)
        sources = list(self.root.glob("*/*.memory.md"))
        try:
            indexed = self._index_sources(sources)
        except Exception:
            failed += len(sources)
            logger.exception("Memory batch reindex failed")
        return {
            "root": str(self.root),
            "recovered": recovered,
            "indexed_on_startup": indexed,
            "failed": failed,
            **self.stats(),
        }

    def capture(
        self,
        *,
        thread_id: str,
        messages: list[Any],
        agent_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist the completed Run before attempting derived indexing."""
        now = datetime.now(UTC)
        run_id = f"{now:%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex[:8]}"
        safe_thread = re.sub(r"[^a-zA-Z0-9_.-]+", "-", thread_id).strip("-.")[:120] or "thread"
        directory = self.root / safe_thread
        directory.mkdir(parents=True, exist_ok=True)
        turns = self._turns(messages)
        raw_path = directory / f"{run_id}.raw.md"
        memory_path = directory / f"{run_id}.memory.md"
        raw_body = self._raw_markdown(thread_id, run_id, now, agent_name, metadata or {}, turns)
        summary = self._compact(turns)
        memory_body = self._memory_markdown(thread_id, run_id, now, raw_path.name, summary)

        with self._lock:
            self._atomic_write(raw_path, raw_body)
            self._atomic_write(memory_path, memory_body)

        indexed = False
        error = None
        try:
            indexed = self._index_source(memory_path)
        except Exception as exc:  # Markdown remains a durable pending item.
            error = str(exc)[:300]
            logger.warning("Memory saved but vector indexing is pending: %s", exc)
        return {
            "status": "indexed" if indexed else "pending_index",
            "run_id": run_id,
            "raw_path": str(raw_path),
            "memory_path": str(memory_path),
            "error": error,
        }

    def search(self, query: str, *, top_k: int = 6) -> list[MemoryHit]:
        if not query.strip():
            return []
        self._ensure_schema()
        vector = self._vector_literal(self._embed(query))
        sql = """
            SELECT content, 1 - (embedding <=> %s::vector) AS score, source_path
            FROM harness_memories
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (vector, vector, max(1, min(top_k, 20))))
            return [MemoryHit(str(row[0]), float(row[1]), str(row[2])) for row in cur.fetchall()]

    def stats(self) -> dict[str, Any]:
        markdown_sources = len(list(self.root.glob("*/*.memory.md"))) if self.root.exists() else 0
        indexed = 0
        try:
            self._ensure_schema()
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM harness_memories")
                indexed = int(cur.fetchone()[0])
        except Exception as exc:
            return {
                "source": "markdown",
                "index": "pgvector",
                "markdown_sources": markdown_sources,
                "indexed": indexed,
                "pending": markdown_sources,
                "healthy": False,
                "error": str(exc)[:200],
            }
        return {
            "source": "markdown",
            "index": "pgvector",
            "markdown_sources": markdown_sources,
            "indexed": indexed,
            "pending": max(0, markdown_sources - indexed),
            "healthy": True,
        }

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._lock:
            if self._schema_ready:
                return
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS harness_memories (
                        memory_id text PRIMARY KEY,
                        thread_id text NOT NULL,
                        source_path text NOT NULL UNIQUE,
                        content text NOT NULL,
                        content_hash text NOT NULL,
                        embedding vector({_VECTOR_DIM}) NOT NULL,
                        created_at timestamptz NOT NULL DEFAULT now(),
                        indexed_at timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS harness_memories_embedding_hnsw ON harness_memories USING hnsw (embedding vector_cosine_ops)")
            self._schema_ready = True

    def _index_source(self, source: Path) -> bool:
        return bool(self._index_sources([source]))

    def _index_sources(self, sources: list[Path]) -> int:
        """Index changed sources in one embedding batch; skip stable hashes."""
        self._ensure_schema()
        records: list[tuple[str, str, str, str, str]] = []
        for source in sources:
            content = source.read_text(encoding="utf-8").strip()
            digest = hashlib.sha256(f"{_EMBEDDING_VERSION}\0{content}".encode()).hexdigest()
            relative = source.relative_to(self.root).as_posix()
            memory_id = hashlib.sha256(f"{relative}:{digest}".encode()).hexdigest()[:32]
            records.append((memory_id, source.parent.name, relative, content, digest))
        if not records:
            return 0

        with self._connect() as conn, conn.cursor() as cur:
            paths = [item[2] for item in records]
            cur.execute(
                "SELECT source_path, content_hash FROM harness_memories WHERE source_path = ANY(%s)",
                (paths,),
            )
            existing = {str(path): str(digest) for path, digest in cur.fetchall()}
            changed = [item for item in records if existing.get(item[2]) != item[4]]
            if not changed:
                return 0
            vectors = self._embed_many([item[3] for item in changed])
            cur.executemany(
                """
                INSERT INTO harness_memories
                    (memory_id, thread_id, source_path, content, content_hash, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector)
                ON CONFLICT (source_path) DO UPDATE SET
                    content = EXCLUDED.content,
                    content_hash = EXCLUDED.content_hash,
                    embedding = EXCLUDED.embedding,
                    indexed_at = now()
                """,
                [(*item, self._vector_literal(vector)) for item, vector in zip(changed, vectors, strict=True)],
            )
        return len(changed)

    @staticmethod
    def _turns(messages: list[Any]) -> list[tuple[str, str]]:
        turns: list[tuple[str, str]] = []
        for message in messages:
            kind = getattr(message, "type", "")
            if kind not in {"human", "ai"}:
                continue
            content = getattr(message, "content", "")
            if isinstance(content, list):
                content = " ".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
            text = str(content).strip()
            if text:
                turns.append(("User" if kind == "human" else "Assistant", text))
        return turns

    @staticmethod
    def _compact(turns: list[tuple[str, str]]) -> str:
        if not turns:
            return "No durable conversation content."
        selected: list[str] = []
        for role, text in turns[-12:]:
            sentences = re.split(r"(?<=[。！？.!?])\s*|\n+", text)
            durable = [item.strip() for item in sentences if _DURABLE_SIGNAL.search(item)]
            if durable:
                selected.append(f"- {role}: {' '.join(durable[:3])[:1000]}")
        if not selected:
            first_user = next((text for role, text in turns if role == "User"), "")
            last_assistant = next((text for role, text in reversed(turns) if role == "Assistant"), "")
            if first_user:
                selected.append(f"- user goal: {first_user[:1000]}")
            if last_assistant:
                selected.append(f"- outcome: {last_assistant[:1400]}")
        return "\n".join(selected)[-4000:]

    @staticmethod
    def _raw_markdown(thread_id: str, run_id: str, now: datetime, agent_name: str | None, metadata: dict[str, Any], turns: list[tuple[str, str]]) -> str:
        header = {
            "thread_id": thread_id,
            "run_id": run_id,
            "ended_at": now.isoformat(),
            "agent": agent_name,
            "metadata": metadata,
        }
        body = "\n\n".join(f"## {role}\n\n{text}" for role, text in turns)
        return f"---\n{json.dumps(header, ensure_ascii=False, default=str)}\n---\n\n# Run transcript\n\n{body}\n"

    @staticmethod
    def _memory_markdown(thread_id: str, run_id: str, now: datetime, raw_name: str, summary: str) -> str:
        return f"---\nthread_id: {thread_id}\nrun_id: {run_id}\ncreated_at: {now.isoformat()}\nsource: {raw_name}\n---\n\n# Extracted memory\n\n{summary}\n"

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _embed(text: str) -> list[float]:
        return HarnessMemory._embed_many([text])[0]

    @staticmethod
    def _embed_many(texts: list[str]) -> list[list[float]]:
        """Fast, dependency-free vectorization for names and durable facts.

        Word tokens plus CJK character bi/tri-grams retain exact terminology
        without loading a model into every app-server process. Feature hashing
        gives a fixed pgvector dimension and deterministic cold-start rebuilds.
        """
        result: list[list[float]] = []
        for text in texts:
            normalized = text.casefold()
            tokens = re.findall(r"[a-z0-9_./:-]+|[\u3400-\u9fff]", normalized)
            cjk = "".join(re.findall(r"[\u3400-\u9fff]", normalized))
            tokens.extend(cjk[index : index + size] for size in (2, 3) for index in range(max(0, len(cjk) - size + 1)))
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            values = [0.0] * _VECTOR_DIM
            for token, count in counts.items():
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % _VECTOR_DIM
                sign = 1.0 if digest[4] & 1 else -1.0
                values[index] += sign * (1.0 + math.log(count))
            norm = sum(item * item for item in values) ** 0.5 or 1.0
            result.append([item / norm for item in values])
        return result

    @staticmethod
    def _vector_literal(values: list[float]) -> str:
        return "[" + ",".join(f"{item:.9g}" for item in values) + "]"

    @staticmethod
    def _connect():
        import psycopg

        dsn = os.getenv("OCTOAGENT_CHECKPOINTER_DSN") or os.getenv("DATABASE_URL")
        if not dsn:
            raise RuntimeError("PostgreSQL DSN is not configured")
        return psycopg.connect(dsn, connect_timeout=5)


_memory: HarnessMemory | None = None
_memory_lock = threading.Lock()


def get_harness_memory() -> HarnessMemory:
    global _memory
    if _memory is None:
        with _memory_lock:
            if _memory is None:
                _memory = HarnessMemory()
    return _memory


__all__ = ["HarnessMemory", "MemoryHit", "get_harness_memory"]
