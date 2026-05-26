"""self_evolution.lessons — persistent "lessons learned" store.

A thin, dependency-free SQLite-backed log of post-mortem entries that any
component (reflection service, system_guard, watchdog ingestion, manual
operator notes) can append to and query.

Design goals (octoagent 2026-05-13):
* Zero external deps — uses stdlib ``sqlite3`` only.
* Append-mostly; no destructive updates from agent code paths.
* Stable schema so the reflection service and skill_evolution can consume
  rows long after they were written.
* Concurrent-safe via WAL + short-lived connections (the langgraph worker
  pool and the gateway both write).

Schema::

    CREATE TABLE lessons (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts          TEXT NOT NULL,                  -- ISO-8601 UTC
        source      TEXT NOT NULL,                  -- e.g. "reflection",
                                                    --      "watchdog",
                                                    --      "lead_agent",
                                                    --      "operator"
        category    TEXT NOT NULL,                  -- short tag, free-form
        pattern     TEXT NOT NULL,                  -- 1-line situation summary
        root_cause  TEXT,                           -- optional explanation
        fix         TEXT,                           -- corrective action
        evidence    TEXT,                           -- JSON blob, free-form
        session_id  TEXT,                           -- optional langgraph thread
        severity    INTEGER NOT NULL DEFAULT 2      -- 1=info,2=warn,3=error
    );

    CREATE INDEX lessons_category_ts ON lessons(category, ts);
    CREATE INDEX lessons_source_ts   ON lessons(source, ts);

Use ``LessonsStore.default()`` from any process; the store auto-resolves to
``$REPO_ROOT/workspace/lessons.db`` (consistent with ``checkpoints.db``).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = ["Lesson", "LessonsStore", "LessonsError"]


class LessonsError(RuntimeError):
    """Raised for unrecoverable problems with the lessons store."""


@dataclass(frozen=True)
class Lesson:
    source: str
    category: str
    pattern: str
    root_cause: str | None = None
    fix: str | None = None
    evidence: Mapping[str, Any] | None = None
    session_id: str | None = None
    severity: int = 2  # 1=info, 2=warn, 3=error
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="milliseconds"))

    def to_row(self) -> tuple[Any, ...]:
        return (
            self.ts,
            self.source,
            self.category,
            self.pattern,
            self.root_cause,
            self.fix,
            json.dumps(self.evidence, ensure_ascii=False) if self.evidence else None,
            self.session_id,
            int(self.severity),
        )


_SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    source      TEXT NOT NULL,
    category    TEXT NOT NULL,
    pattern     TEXT NOT NULL,
    root_cause  TEXT,
    fix         TEXT,
    evidence    TEXT,
    session_id  TEXT,
    severity    INTEGER NOT NULL DEFAULT 2
);
CREATE INDEX IF NOT EXISTS lessons_category_ts ON lessons(category, ts);
CREATE INDEX IF NOT EXISTS lessons_source_ts   ON lessons(source, ts);
"""


def _default_db_path() -> Path:
    # Same convention as checkpointer: $REPO_ROOT/workspace/<name>.db
    # In OctoAgent the langgraph worker cwd is backend/, so workspace is one up.
    env = os.environ.get("OCTO_LESSONS_DB_PATH")
    if env:
        return Path(env).expanduser()
    here = Path(__file__).resolve()
    # backend/src/self_evolution/lessons.py -> walk up to repo root
    for parent in here.parents:
        if (parent / "workspace").is_dir():
            return parent / "workspace" / "lessons.db"
    # Fall back to CWD/workspace (lazy-create) — same as checkpoints.db
    return Path.cwd() / "workspace" / "lessons.db"


class LessonsStore:
    """Thread-safe, append-mostly SQLite log of lessons-learned entries."""

    _DEFAULT: LessonsStore | None = None
    _DEFAULT_LOCK = threading.Lock()

    def __init__(self, db_path: str | os.PathLike[str] | None = None):
        self._db_path = Path(db_path) if db_path else _default_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_schema()

    @classmethod
    def default(cls) -> LessonsStore:
        with cls._DEFAULT_LOCK:
            if cls._DEFAULT is None:
                cls._DEFAULT = cls()
            return cls._DEFAULT

    @property
    def db_path(self) -> Path:
        return self._db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # Short-lived connection; rely on WAL for cross-process concurrency.
        conn = sqlite3.connect(str(self._db_path), timeout=5.0, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)

    def record(self, lesson: Lesson) -> int:
        """Append a lesson; returns its rowid. Errors are non-fatal: callers
        in hot paths can swallow ``LessonsError``."""
        try:
            with self._lock, self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO lessons
                        (ts, source, category, pattern, root_cause, fix,
                         evidence, session_id, severity)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    lesson.to_row(),
                )
                rowid = cur.lastrowid
                if rowid is None:
                    raise LessonsError("INSERT returned no rowid")
                return rowid
        except sqlite3.Error as exc:  # pragma: no cover - infra failure
            raise LessonsError(f"failed to record lesson: {exc}") from exc

    def record_many(self, lessons: Iterable[Lesson]) -> int:
        rows = [lesson.to_row() for lesson in lessons]
        if not rows:
            return 0
        try:
            with self._lock, self._connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO lessons
                        (ts, source, category, pattern, root_cause, fix,
                         evidence, session_id, severity)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                return len(rows)
        except sqlite3.Error as exc:  # pragma: no cover
            raise LessonsError(f"failed to record lessons: {exc}") from exc

    def recent(
        self,
        *,
        limit: int = 50,
        category: str | None = None,
        source: str | None = None,
        min_severity: int = 1,
    ) -> list[dict[str, Any]]:
        clauses = ["severity >= ?"]
        params: list[Any] = [int(min_severity)]
        if category:
            clauses.append("category = ?")
            params.append(category)
        if source:
            clauses.append("source = ?")
            params.append(source)
        where = " AND ".join(clauses)
        params.append(int(limit))
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                f"""
                SELECT id, ts, source, category, pattern, root_cause, fix,
                       evidence, session_id, severity
                FROM lessons
                WHERE {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                params,
            )
            out: list[dict[str, Any]] = []
            for row in cur.fetchall():
                d = dict(row)
                if d.get("evidence"):
                    try:
                        d["evidence"] = json.loads(d["evidence"])
                    except (TypeError, ValueError):
                        pass
                out.append(d)
            return out

    def search(self, *, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        like = f"%{keyword}%"
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """
                SELECT id, ts, source, category, pattern, root_cause, fix,
                       evidence, session_id, severity
                FROM lessons
                WHERE pattern    LIKE ? COLLATE NOCASE
                   OR root_cause LIKE ? COLLATE NOCASE
                   OR fix        LIKE ? COLLATE NOCASE
                ORDER BY id DESC
                LIMIT ?
                """,
                (like, like, like, int(limit)),
            )
            return [dict(r) for r in cur.fetchall()]

    def count(self) -> int:
        with self._connect() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM lessons")
            return int(cur.fetchone()[0])
