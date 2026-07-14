"""Memory API router for retrieving and managing global memory data."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.agents.memory.layer_accessor import (
    get_memory_layer_accessor,
)
from src.agents.memory.system_rag_store import (
    get_system_rag_store,
)
from src.agents.memory.updater import ensure_memory_schema
from src.gateway.routers.memory_schemas import (
    GlobalMemoryEntry,
    GlobalMemoryStore,
    GlobalMemoryUpdateRequest,
    MemoryConfigResponse,
    MemoryResponse,
    MemorySchemaStatus,
    MemoryStatusResponse,
)
from src.runtime.config.memory_config import get_memory_config
from src.runtime.config.paths import get_paths

router = APIRouter(prefix="/api", tags=["memory"])


def _normalize_fact_content(text: str) -> str:
    """Normalize fact text for duplicate detection."""
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _augment_with_system_memory_facts(data: dict, *, limit: int = 20) -> dict:
    """Expose system RAG memories in the WebUI memory snapshot.

    The runtime stores conversation summaries and self-evolution notes in the
    system RAG store, while Settings -> Memory renders the working-memory fact
    table. Mirroring a read-only summary here prevents the UI from looking empty
    when long-term memory is active but working-memory summarisation has not yet
    produced profile facts.
    """
    facts = list(data.get("facts") or [])
    seen = {str(item.get("id")) for item in facts if isinstance(item, dict)}
    seen_content = {_normalize_fact_content(item.get("content")) for item in facts if isinstance(item, dict) and item.get("content")}
    try:
        entries = get_system_rag_store().list_entries(limit=limit)
    except Exception:
        data["facts"] = facts
        return data

    for entry in entries:
        fact_id = f"system_{entry.id}"
        if fact_id in seen:
            continue
        norm_content = _normalize_fact_content(entry.content)
        if norm_content and norm_content in seen_content:
            continue
        metadata = dict(entry.metadata or {})
        confidence_raw = metadata.get("memory_confidence") or metadata.get("confidence") or 0.75
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.75
        facts.append(
            {
                "id": fact_id,
                "content": entry.content,
                "category": f"system:{entry.namespace}",
                "confidence": max(0.0, min(1.0, confidence)),
                "createdAt": str(metadata.get("created_at") or metadata.get("timestamp_iso") or ""),
                "source": str(metadata.get("thread_id") or metadata.get("source_thread_id") or "system_memory"),
            }
        )
        seen.add(fact_id)
        if norm_content:
            seen_content.add(norm_content)
    data["facts"] = facts
    return data


def _summary_from_facts(facts: list[dict], *, limit: int = 5) -> str:
    items = [str(fact.get("content") or "").strip() for fact in facts if isinstance(fact, dict)]
    items = [item for item in items if item]
    if not items:
        return ""
    return "；".join(items[:limit])[:900]


def _backfill_empty_summaries(data: dict) -> dict:
    """Populate empty overview sections from recorded facts for legacy stores."""

    facts = list(data.get("facts") or [])
    if not facts:
        return data
    now = str(data.get("lastUpdated") or datetime.now(UTC).isoformat())
    by_category: dict[str, list[dict]] = {}
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        by_category.setdefault(str(fact.get("category") or "context"), []).append(fact)

    user = data.setdefault("user", {})
    history = data.setdefault("history", {})
    work = user.setdefault("workContext", {"summary": "", "updatedAt": ""})
    personal = user.setdefault("personalContext", {"summary": "", "updatedAt": ""})
    top = user.setdefault("topOfMind", {"summary": "", "updatedAt": ""})
    recent = history.setdefault("recentMonths", {"summary": "", "updatedAt": ""})
    long_term = history.setdefault("longTermBackground", {"summary": "", "updatedAt": ""})

    work_facts = by_category.get("knowledge", []) + by_category.get("goal", []) + by_category.get("context", [])
    personal_facts = by_category.get("preference", []) + by_category.get("context", [])
    behavior_facts = by_category.get("behavior", [])
    all_summary = _summary_from_facts(facts)

    if not str(work.get("summary") or "").strip():
        work["summary"] = _summary_from_facts(work_facts) or all_summary
        work["updatedAt"] = now
    if not str(personal.get("summary") or "").strip():
        personal["summary"] = _summary_from_facts(personal_facts, limit=4) or all_summary
        personal["updatedAt"] = now
    if not str(top.get("summary") or "").strip():
        top["summary"] = _summary_from_facts(list(reversed(facts)), limit=5)
        top["updatedAt"] = now
    if not str(recent.get("summary") or "").strip():
        recent["summary"] = _summary_from_facts(behavior_facts or facts, limit=8)
        recent["updatedAt"] = now
    if not str(long_term.get("summary") or "").strip():
        long_term["summary"] = _summary_from_facts(facts, limit=6)
        long_term["updatedAt"] = now
    return data


def _normalize_memory_snapshot(raw: dict) -> dict:
    """Normalize legacy/flat memory payloads into the WebUI schema.

    Older memory files used ``{user_context: str, facts: [...], history: [...]}``.
    The WebUI MemoryResponse expects structured ``user``/``history`` dicts.
    This mapper preserves whatever the legacy file held so Settings → Memory
    shows something useful rather than a blank skeleton.
    """
    data: dict = ensure_memory_schema(raw)

    # facts: keep only dict entries with minimally required id+content.
    facts_raw = data.get("facts") or []
    facts_clean: list[dict] = []
    if isinstance(facts_raw, list):
        for idx, item in enumerate(facts_raw):
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            facts_clean.append(
                {
                    "id": str(item.get("id") or f"fact_{idx}"),
                    "content": content,
                    "category": str(item.get("category") or "context"),
                    "confidence": float(item.get("confidence") or 0.5),
                    "createdAt": str(item.get("createdAt") or ""),
                    "source": str(item.get("source") or "unknown"),
                }
            )
    data["facts"] = facts_clean

    data.setdefault("version", "1.0")
    data.setdefault("lastUpdated", "")
    data = _backfill_empty_summaries(data)
    return _augment_with_system_memory_facts(data)


@router.get(
    "/memory",
    response_model=MemoryResponse,
    summary="Get Memory Data",
    description="Retrieve the current global memory data including user context, history, and facts.",
)
async def get_memory() -> MemoryResponse:
    """Get the current global memory data.

    Returns:
        The current memory data with user context, history, and facts.

    Example Response:
        ```json
        {
            "version": "1.0",
            "lastUpdated": "2024-01-15T10:30:00Z",
            "user": {
                "workContext": {"summary": "Working on OctoAgent project", "updatedAt": "..."},
                "personalContext": {"summary": "Prefers concise responses", "updatedAt": "..."},
                "topOfMind": {"summary": "Building memory API", "updatedAt": "..."}
            },
            "history": {
                "recentMonths": {"summary": "Recent development activities", "updatedAt": "..."},
                "earlierContext": {"summary": "", "updatedAt": ""},
                "longTermBackground": {"summary": "", "updatedAt": ""}
            },
            "facts": [
                {
                    "id": "fact_abc123",
                    "content": "User prefers TypeScript over JavaScript",
                    "category": "preference",
                    "confidence": 0.9,
                    "createdAt": "2024-01-15T10:30:00Z",
                    "source": "thread_xyz"
                }
            ]
        }
        ```
    """
    memory_data = get_memory_layer_accessor().get_working_memory()
    # Normalize legacy flat snapshots into the WebUI schema so Settings →
    # Memory renders user context, history, and facts instead of failing.
    return MemoryResponse(**_normalize_memory_snapshot(memory_data))


@router.get(
    "/memory/schema-status",
    response_model=MemorySchemaStatus,
    summary="Memory schema v2 observation status",
    description=(
        "Observation-only endpoint. Reports whether memory.v2.json has been "
        "generated by backend/scripts/migrate_memory_schema.py and whether the "
        "operator has opted in to read v2 preferentially via MEMORY_PREFER_V2=1. "
        "Runtime normalizer already accepts both shapes, so this flag is a "
        "reporting surface only."
    ),
)
async def get_memory_schema_status() -> MemorySchemaStatus:
    config = get_memory_config()
    raw_path = (config.storage_path or "").strip()
    candidates: list[Path] = []
    if raw_path:
        p = Path(raw_path).expanduser()
        if p.name:
            candidates.append(p)
            if not p.is_absolute():
                candidates.append(Path.cwd() / p)
                candidates.append(Path.cwd().parent / p)
    candidates.extend(
        [
            Path("workspace/default/memory.json"),
            Path("../workspace/default/memory.json"),
            get_paths().memory_file,
        ]
    )

    storage_path = next((c for c in candidates if c.exists()), candidates[0])
    v2_path = storage_path.with_name(f"{storage_path.stem}.v2.json")
    legacy_path = storage_path.with_name(f"{storage_path.stem}.legacy.json")

    schema_version = "1.0"
    try:
        if storage_path.exists():
            raw = json.loads(storage_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and str(raw.get("version") or "").startswith("2"):
                schema_version = "2.0"
    except Exception:
        schema_version = "1.0"

    prefer_v2 = os.environ.get("MEMORY_PREFER_V2", "").strip().lower() in {"1", "true", "yes", "on"}

    return MemorySchemaStatus(
        storage_path=str(storage_path),
        schema_version=schema_version,
        v2_available=v2_path.exists(),
        legacy_backup_present=legacy_path.exists(),
        prefer_v2=prefer_v2,
        note=(
            "Run `backend/.venv/bin/python backend/scripts/migrate_memory_schema.py "
            "--memory <path>` to generate memory.v2.json. The runtime already "
            "normalizes both shapes; set MEMORY_PREFER_V2=1 to mark the v2 file "
            "as authoritative in status reports."
        ),
    )


@router.get(
    "/memory/status",
    response_model=MemoryStatusResponse,
    summary="Get Memory Status",
    description="Retrieve both memory configuration and current data in a single request.",
)
async def get_memory_status() -> MemoryStatusResponse:
    """Get the memory system status including configuration and data.

    Returns:
        Combined memory configuration and current data.
    """
    config = get_memory_config()
    memory_data = get_memory_layer_accessor().get_working_memory()

    return MemoryStatusResponse(
        config=MemoryConfigResponse(
            enabled=config.enabled,
            storage_path=config.storage_path,
            debounce_seconds=config.debounce_seconds,
            max_facts=config.max_facts,
            fact_confidence_threshold=config.fact_confidence_threshold,
            injection_enabled=config.injection_enabled,
            max_injection_tokens=config.max_injection_tokens,
            write_governance_enabled=config.write_governance_enabled,
            write_governance_mode=config.write_governance_mode,
            long_term_retention_days=config.long_term_retention_days,
            permanent_retention_days=config.permanent_retention_days,
            permanent_memory_immutable=config.permanent_memory_immutable,
        ),
        data=MemoryResponse(**_normalize_memory_snapshot(memory_data)),
    )


# ---------------------------------------------------------------------------
# Global Memory (user-editable persistent prompt / instructions)
# ---------------------------------------------------------------------------

_GLOBAL_MEMORY_PATH = Path(".octoagent/global_memory.json")


def _load_global_memory() -> GlobalMemoryStore:
    if _GLOBAL_MEMORY_PATH.exists():
        try:
            raw = json.loads(_GLOBAL_MEMORY_PATH.read_text(encoding="utf-8"))
            return GlobalMemoryStore(**raw)
        except Exception:
            pass
    return GlobalMemoryStore()


def _save_global_memory(store: GlobalMemoryStore) -> None:
    _GLOBAL_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _GLOBAL_MEMORY_PATH.write_text(
        json.dumps(store.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@router.get(
    "/memory/global",
    response_model=GlobalMemoryStore,
    summary="List global memory entries",
)
async def list_global_memory() -> GlobalMemoryStore:
    return _load_global_memory()


@router.post(
    "/memory/global",
    response_model=GlobalMemoryEntry,
    summary="Create a global memory entry",
)
async def create_global_memory(body: GlobalMemoryUpdateRequest) -> GlobalMemoryEntry:
    import uuid
    from datetime import datetime

    store = _load_global_memory()
    now = datetime.now(UTC).isoformat()
    entry = GlobalMemoryEntry(
        id=str(uuid.uuid4()),
        title=body.title,
        content=body.content,
        source="manual",
        createdAt=now,
        updatedAt=now,
    )
    store.entries.append(entry)
    _save_global_memory(store)
    return entry


@router.put(
    "/memory/global/{entry_id}",
    response_model=GlobalMemoryEntry,
    summary="Update a global memory entry",
)
async def update_global_memory(entry_id: str, body: GlobalMemoryUpdateRequest) -> GlobalMemoryEntry:
    from datetime import datetime

    store = _load_global_memory()
    for entry in store.entries:
        if entry.id == entry_id:
            entry.title = body.title
            entry.content = body.content
            entry.updatedAt = datetime.now(UTC).isoformat()
            _save_global_memory(store)
            return entry

    raise HTTPException(status_code=404, detail="Entry not found")


@router.delete(
    "/memory/global/{entry_id}",
    summary="Delete a global memory entry",
)
async def delete_global_memory(entry_id: str) -> dict:
    store = _load_global_memory()
    original_len = len(store.entries)
    store.entries = [e for e in store.entries if e.id != entry_id]
    if len(store.entries) == original_len:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Entry not found")
    _save_global_memory(store)
    return {"ok": True}


_ALLOWED_IMPORT_EXTENSIONS = {".txt", ".md", ".json", ".doc", ".docx"}


# ── System Memory (RAG) — read-only endpoints ─────────────────────────


@router.get("/memory/system/stats")
async def get_system_memory_stats():
    """Return statistics of the system RAG memory store."""
    try:
        store = get_system_rag_store()
        return store.stats()
    except Exception as e:
        return {"error": str(e), "total_entries": 0}
