"""DuckDB-backed vector lifecycle store for system guard snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb


class SystemGuardVectorStore:
    """Persist lifecycle state snapshots and session markers."""

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
                CREATE TABLE IF NOT EXISTS system_guard_vectors (
                    id VARCHAR PRIMARY KEY,
                    session_id VARCHAR,
                    namespace VARCHAR,
                    phase VARCHAR,
                    created_at TIMESTAMP,
                    content TEXT,
                    metadata_json TEXT,
                    state_json TEXT,
                    embedding_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_guard_sessions (
                    session_id VARCHAR PRIMARY KEY,
                    status VARCHAR,
                    updated_at TIMESTAMP,
                    state_json TEXT
                )
                """
            )

    @property
    def db_path(self) -> Path:
        return self._db_path

    def insert_snapshot(
        self,
        *,
        snapshot_id: str,
        session_id: str,
        namespace: str,
        phase: str,
        created_at: str,
        content: str,
        metadata: dict[str, Any],
        state: dict[str, Any],
        embedding: list[float],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO system_guard_vectors
                (id, session_id, namespace, phase, created_at, content, metadata_json, state_json, embedding_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    snapshot_id,
                    session_id,
                    namespace,
                    phase,
                    created_at,
                    content,
                    json.dumps(metadata, ensure_ascii=False),
                    json.dumps(state, ensure_ascii=False),
                    json.dumps(embedding),
                ],
            )

    def mark_session(
        self,
        *,
        session_id: str,
        status: str,
        updated_at: str,
        state: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO system_guard_sessions
                (session_id, status, updated_at, state_json)
                VALUES (?, ?, ?, ?)
                """,
                [session_id, status, updated_at, json.dumps(state, ensure_ascii=False)],
            )

    def close_running_sessions(self, *, reason: str, updated_at: str) -> int:
        with self._connect() as conn:
            running = conn.execute("SELECT session_id, state_json FROM system_guard_sessions WHERE status = 'running'").fetchall()
            for row in running:
                payload = json.loads(row[1]) if row[1] else {}
                payload["auto_closed_reason"] = reason
                conn.execute(
                    """
                    UPDATE system_guard_sessions
                    SET status = ?, updated_at = ?, state_json = ?
                    WHERE session_id = ?
                    """,
                    ["interrupted", updated_at, json.dumps(payload, ensure_ascii=False), row[0]],
                )
        return len(running)

    def close_selected_running_sessions(
        self,
        *,
        session_ids: list[str],
        reason: str,
        updated_at: str,
    ) -> int:
        if not session_ids:
            return 0

        closed = 0
        with self._connect() as conn:
            for session_id in session_ids:
                row = conn.execute(
                    """
                    SELECT state_json
                    FROM system_guard_sessions
                    WHERE session_id = ? AND status = 'running'
                    """,
                    [session_id],
                ).fetchone()
                if row is None:
                    continue
                payload = json.loads(row[0]) if row[0] else {}
                payload["auto_closed_reason"] = reason
                conn.execute(
                    """
                    UPDATE system_guard_sessions
                    SET status = ?, updated_at = ?, state_json = ?
                    WHERE session_id = ?
                    """,
                    ["interrupted", updated_at, json.dumps(payload, ensure_ascii=False), session_id],
                )
                closed += 1
        return closed

    def list_running_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT session_id, updated_at, state_json FROM system_guard_sessions WHERE status = 'running'").fetchall()
        return [
            {
                "session_id": row[0],
                "updated_at": str(row[1]),
                "state": json.loads(row[2]) if row[2] else {},
            }
            for row in rows
        ]

    def latest_snapshot(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, session_id, namespace, phase, created_at, content, metadata_json, state_json
                FROM system_guard_vectors
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "session_id": row[1],
            "namespace": row[2],
            "phase": row[3],
            "created_at": str(row[4]),
            "content": row[5],
            "metadata": json.loads(row[6]) if row[6] else {},
            "state": json.loads(row[7]) if row[7] else {},
        }

    def recent_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, namespace, phase, created_at, content, metadata_json, state_json
                FROM system_guard_vectors
                ORDER BY created_at DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
        return [
            {
                "id": row[0],
                "session_id": row[1],
                "namespace": row[2],
                "phase": row[3],
                "created_at": str(row[4]),
                "content": row[5],
                "metadata": json.loads(row[6]) if row[6] else {},
                "state": json.loads(row[7]) if row[7] else {},
            }
            for row in rows
        ]

    def count_snapshots(self, *, namespace: str | None = None) -> int:
        with self._connect() as conn:
            if namespace is None:
                row = conn.execute("SELECT COUNT(*) FROM system_guard_vectors").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM system_guard_vectors WHERE namespace = ?",
                    [namespace],
                ).fetchone()
        return int(row[0]) if row else 0

    def prune_snapshots(self, *, namespace: str, keep_latest: int) -> int:
        if keep_latest <= 0:
            return 0

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM system_guard_vectors
                WHERE namespace = ?
                ORDER BY created_at DESC
                OFFSET ?
                """,
                [namespace, keep_latest],
            ).fetchall()
            snapshot_ids = [row[0] for row in rows]
            if not snapshot_ids:
                return 0
            conn.executemany(
                "DELETE FROM system_guard_vectors WHERE id = ?",
                [[snapshot_id] for snapshot_id in snapshot_ids],
            )
        return len(snapshot_ids)
