"""Repair encoding, deduplicate, cap, and re-embed SystemRAG memories."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from typing import Any

import duckdb

from src.agents.memory.text_normalization import repair_mojibake
from src.models.embedding_service import get_embedding_service
from src.storage.rag import get_unified_rag_store


def _repair_value(value: Any) -> Any:
    if isinstance(value, str):
        return repair_mojibake(value)
    if isinstance(value, list):
        return [_repair_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _repair_value(item) for key, item in value.items()}
    return value


def _content_key(content: str) -> str:
    normalized = " ".join(content.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def repair_store(*, apply: bool, max_entries_per_namespace: int) -> dict[str, Any]:
    db_path = get_unified_rag_store().db_path
    with duckdb.connect(str(db_path), read_only=True) as conn:
        rows = conn.execute("SELECT id, namespace, content, metadata_json, created_at, agent_name FROM system_memories ORDER BY created_at DESC").fetchall()

    kept: list[tuple[Any, ...]] = []
    seen: dict[str, set[str]] = {}
    counts: dict[str, int] = {}
    repaired_count = 0
    duplicate_count = 0
    capped_count = 0
    for entry_id, namespace, content, metadata_json, created_at, agent_name in rows:
        repaired_content = repair_mojibake(str(content or "")).strip()
        try:
            metadata = json.loads(metadata_json or "{}")
        except json.JSONDecodeError:
            metadata = {}
        repaired_metadata = _repair_value(metadata if isinstance(metadata, dict) else {})
        if repaired_content != content or repaired_metadata != metadata:
            repaired_count += 1
        key = _content_key(repaired_content)
        namespace_seen = seen.setdefault(namespace, set())
        if key in namespace_seen:
            duplicate_count += 1
            continue
        if counts.get(namespace, 0) >= max_entries_per_namespace:
            capped_count += 1
            continue
        namespace_seen.add(key)
        counts[namespace] = counts.get(namespace, 0) + 1
        kept.append((entry_id, namespace, repaired_content, repaired_metadata, created_at, agent_name))

    report = {
        "database": str(db_path),
        "before": len(rows),
        "after": len(kept),
        "encoding_repaired": repaired_count,
        "duplicates_removed": duplicate_count,
        "cap_evicted": capped_count,
        "by_namespace": counts,
        "applied": apply,
    }
    if not apply:
        return report

    backup = db_path.with_name(f"{db_path.name}.backup-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}")
    shutil.copy2(db_path, backup)
    service = get_embedding_service()
    embeddings = service.embed([row[2] for row in kept])
    with duckdb.connect(str(db_path)) as conn:
        conn.execute("BEGIN TRANSACTION")
        try:
            conn.execute("DELETE FROM system_memories")
            for row, embedding in zip(kept, embeddings, strict=True):
                entry_id, namespace, content, metadata, created_at, agent_name = row
                conn.execute(
                    "INSERT INTO system_memories (id, namespace, content, metadata_json, embedding_json, created_at, agent_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [entry_id, namespace, content, json.dumps(metadata, ensure_ascii=False), json.dumps(embedding), created_at, agent_name],
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    report.update({"backup": str(backup), "embedding_backend": service.backend_name, "embedding_dim": service.dim})
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-entries-per-namespace", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(repair_store(apply=args.apply, max_entries_per_namespace=max(1, args.max_entries_per_namespace)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
