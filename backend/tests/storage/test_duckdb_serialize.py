"""Single-writer convergence guard for the shared RAG DuckDB file.

`connect_duckdb_with_retry` defaults to retry-only behaviour (no lock, identical
to historical behaviour). When ``OCTOAGENT_DUCKDB_SERIALIZE`` is enabled it must
serialize cross-process access with an advisory readers-writer file lock and
release that lock exactly once when the connection is closed.
"""

from __future__ import annotations

import os

import pytest

from src.storage.rag.unified_store import connect_duckdb_with_retry

fcntl = pytest.importorskip("fcntl")


def _ex_lock_free(lock_path: str) -> bool:
    """True if an exclusive non-blocking flock can be taken (i.e. not held)."""
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def _sh_lock_free(lock_path: str) -> bool:
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def test_default_off_is_retry_only(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OCTOAGENT_DUCKDB_SERIALIZE", raising=False)
    db = tmp_path / "rag.duckdb"
    with connect_duckdb_with_retry(db) as conn:
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 1
    # No sidecar lock file is created when serialization is off.
    assert not (tmp_path / "rag.duckdb.rwlock").exists()


def test_serialize_exclusive_held_then_released(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOAGENT_DUCKDB_SERIALIZE", "1")
    db = tmp_path / "rag.duckdb"
    lock_path = str(db) + ".rwlock"

    conn = connect_duckdb_with_retry(db)
    try:
        # Lock file exists and an exclusive lock is currently held by us.
        assert os.path.exists(lock_path)
        assert _ex_lock_free(lock_path) is False
        # Delegation still works through the guarded proxy.
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.execute("INSERT INTO t VALUES (42)")
        assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 1
    finally:
        conn.close()

    # Released after close -> exclusive lock is now free.
    assert _ex_lock_free(lock_path) is True
    # Idempotent close does not raise.
    conn.close()


def test_serialize_with_statement_releases(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOAGENT_DUCKDB_SERIALIZE", "1")
    db = tmp_path / "rag.duckdb"
    lock_path = str(db) + ".rwlock"

    with connect_duckdb_with_retry(db) as conn:
        assert _ex_lock_free(lock_path) is False
        conn.execute("CREATE TABLE t (id INTEGER)")

    assert _ex_lock_free(lock_path) is True


def test_serialize_shared_lock_for_read_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOAGENT_DUCKDB_SERIALIZE", "1")
    db = tmp_path / "rag.duckdb"
    lock_path = str(db) + ".rwlock"

    # Materialise the database first (read_only connect requires an existing file).
    with connect_duckdb_with_retry(db) as conn:
        conn.execute("CREATE TABLE t (id INTEGER)")

    reader = connect_duckdb_with_retry(db, read_only=True)
    try:
        # A shared lock is held: another shared lock is allowed, exclusive is not.
        assert _sh_lock_free(lock_path) is True
        assert _ex_lock_free(lock_path) is False
        assert reader.execute("SELECT count(*) FROM t").fetchone()[0] == 0
    finally:
        reader.close()

    assert _ex_lock_free(lock_path) is True
