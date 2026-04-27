"""Memory API router for retrieving and managing global memory data."""

import json
import os
from datetime import UTC
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from src.agents.memory.governance import build_memory_governance_summary
from src.agents.memory.layer_accessor import (
    LONG_TERM_MEMORY_NAMESPACES,
    PERMANENT_MEMORY_NAMESPACES,
    get_memory_layer_accessor,
)
from src.agents.memory.system_rag_store import (
    MAX_SYSTEM_MEMORY_LIST_LIMIT,
    MAX_SYSTEM_MEMORY_SEARCH_TOP_K,
    get_system_rag_store,
)
from src.config.memory_config import get_memory_config

router = APIRouter(prefix="/api", tags=["memory"])


class ContextSection(BaseModel):
    """Model for context sections (user and history)."""

    summary: str = Field(default="", description="Summary content")
    updatedAt: str = Field(default="", description="Last update timestamp")


class UserContext(BaseModel):
    """Model for user context."""

    workContext: ContextSection = Field(default_factory=ContextSection)
    personalContext: ContextSection = Field(default_factory=ContextSection)
    topOfMind: ContextSection = Field(default_factory=ContextSection)


class HistoryContext(BaseModel):
    """Model for history context."""

    recentMonths: ContextSection = Field(default_factory=ContextSection)
    earlierContext: ContextSection = Field(default_factory=ContextSection)
    longTermBackground: ContextSection = Field(default_factory=ContextSection)


class Fact(BaseModel):
    """Model for a memory fact."""

    id: str = Field(..., description="Unique identifier for the fact")
    content: str = Field(..., description="Fact content")
    category: str = Field(default="context", description="Fact category")
    confidence: float = Field(default=0.5, description="Confidence score (0-1)")
    createdAt: str = Field(default="", description="Creation timestamp")
    source: str = Field(default="unknown", description="Source thread ID")


class MemoryResponse(BaseModel):
    """Response model for memory data."""

    version: str = Field(default="1.0", description="Memory schema version")
    lastUpdated: str = Field(default="", description="Last update timestamp")
    user: UserContext = Field(default_factory=UserContext)
    history: HistoryContext = Field(default_factory=HistoryContext)
    facts: list[Fact] = Field(default_factory=list)


class MemoryConfigResponse(BaseModel):
    """Response model for memory configuration."""

    enabled: bool = Field(..., description="Whether memory is enabled")
    storage_path: str = Field(..., description="Path to memory storage file")
    debounce_seconds: int = Field(..., description="Debounce time for memory updates")
    max_facts: int = Field(..., description="Maximum number of facts to store")
    fact_confidence_threshold: float = Field(..., description="Minimum confidence threshold for facts")
    injection_enabled: bool = Field(..., description="Whether memory injection is enabled")
    max_injection_tokens: int = Field(..., description="Maximum tokens for memory injection")
    write_governance_enabled: bool = Field(..., description="Whether governed memory writes are enabled")
    write_governance_mode: str = Field(..., description="Whether governed writes are audited or enforced")
    long_term_retention_days: int = Field(..., description="Default retention for long-term memory")
    permanent_retention_days: int = Field(..., description="Fallback retention window for permanent memory")
    permanent_memory_immutable: bool = Field(..., description="Whether permanent memory is marked immutable")


class MemoryStatusResponse(BaseModel):
    """Response model for memory status."""

    config: MemoryConfigResponse
    data: MemoryResponse


class MemoryLayerSummaryResponse(BaseModel):
    """Summary of a single memory layer."""

    layer: str = Field(..., description="Layer identifier")
    namespaces: list[str] = Field(default_factory=list, description="Namespaces participating in the layer")
    entry_count: int = Field(default=0, description="Number of entries currently available in the layer")
    available: bool = Field(default=True, description="Whether the layer is available")
    governance_mode: str | None = Field(default=None, description="Effective write-governance mode for this layer")
    confidence_threshold: float | None = Field(default=None, description="Confidence threshold applied to governed writes")
    retention_days: int | None = Field(default=None, description="Default retention window for the layer")
    immutable: bool = Field(default=False, description="Whether entries in this layer are treated as immutable")


class MemoryLayersResponse(BaseModel):
    """Layered memory snapshot summary."""

    working: MemoryLayerSummaryResponse
    long_term: MemoryLayerSummaryResponse
    permanent: MemoryLayerSummaryResponse


class MemoryRetentionPolicyResponse(BaseModel):
    mode: str
    namespace: str
    ttl_days: int | None = None
    expires_at: str | None = None
    immutable: bool = False
    reason: str = ""


class MemoryGovernanceSummaryResponse(BaseModel):
    enabled: bool
    mode: str
    confidence_threshold: float
    long_term_retention_days: int
    permanent_retention_days: int
    immutable_namespaces: list[str] = Field(default_factory=list)
    namespace_policies: dict[str, MemoryRetentionPolicyResponse] = Field(default_factory=dict)


def _normalize_memory_snapshot(raw: dict) -> dict:
    """Normalize legacy/flat memory payloads into the WebUI schema.

    Older memory files used ``{user_context: str, facts: [...], history: [...]}``.
    The WebUI MemoryResponse expects structured ``user``/``history`` dicts.
    This mapper preserves whatever the legacy file held so Settings → Memory
    shows something useful rather than a blank skeleton.
    """
    data: dict = dict(raw or {})

    # user: accept structured dict; fall back to legacy user_context string.
    user = data.get("user")
    if not isinstance(user, dict):
        legacy = data.get("user_context")
        summary = legacy if isinstance(legacy, str) else ""
        data["user"] = {
            "workContext": {"summary": "", "updatedAt": ""},
            "personalContext": {"summary": "", "updatedAt": ""},
            "topOfMind": {"summary": summary, "updatedAt": ""},
        }

    # history: accept structured dict; flatten legacy list of entries.
    history = data.get("history")
    if not isinstance(history, dict):
        if isinstance(history, list) and history:
            parts: list[str] = []
            for item in history:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("summary") or item.get("content") or ""
                    if text:
                        parts.append(str(text))
            summary = "\n".join(parts).strip()
        else:
            summary = ""
        data["history"] = {
            "recentMonths": {"summary": summary, "updatedAt": ""},
            "earlierContext": {"summary": "", "updatedAt": ""},
            "longTermBackground": {"summary": "", "updatedAt": ""},
        }

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
    return data


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


@router.post(
    "/memory/reload",
    response_model=MemoryResponse,
    summary="Reload Memory Data",
    description="Reload memory data from the storage file, refreshing the in-memory cache.",
)
async def reload_memory() -> MemoryResponse:
    """Reload memory data from file.

    This forces a reload of the memory data from the storage file,
    useful when the file has been modified externally.

    Returns:
        The reloaded memory data.
    """
    memory_data = get_memory_layer_accessor().reload_working_memory()
    return MemoryResponse(**_normalize_memory_snapshot(memory_data))


class MemorySchemaStatus(BaseModel):
    storage_path: str = Field(default="")
    schema_version: str = Field(default="1.0", description="Observed schema version")
    v2_available: bool = Field(default=False, description="memory.v2.json exists alongside legacy file")
    legacy_backup_present: bool = Field(default=False, description="memory.legacy.json backup exists")
    prefer_v2: bool = Field(
        default=False,
        description="Operator toggle (env MEMORY_PREFER_V2=1) to read v2 file preferentially",
    )
    note: str = Field(default="")


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
    candidates.extend([
        Path("workspace/default/memory.json"),
        Path("../workspace/default/memory.json"),
        Path("/home/sieve-pub/public-workspace/octoagent/workspace/default/memory.json"),
    ])

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
    "/memory/config",
    response_model=MemoryConfigResponse,
    summary="Get Memory Configuration",
    description="Retrieve the current memory system configuration.",
)
async def get_memory_config_endpoint() -> MemoryConfigResponse:
    """Get the memory system configuration.

    Returns:
        The current memory configuration settings.

    Example Response:
        ```json
        {
            "enabled": true,
            "storage_path": ".octoagent/memory.json",
            "debounce_seconds": 30,
            "max_facts": 100,
            "fact_confidence_threshold": 0.7,
            "injection_enabled": true,
            "max_injection_tokens": 2000
        }
        ```
    """
    config = get_memory_config()
    return MemoryConfigResponse(
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


@router.get(
    "/memory/layers",
    response_model=MemoryLayersResponse,
    summary="Get Memory Layer Summary",
    description="Retrieve working, long-term, and permanent memory layer availability and entry counts.",
)
async def get_memory_layers() -> MemoryLayersResponse:
    """Get a lightweight summary of the layered memory contract."""

    accessor = get_memory_layer_accessor()
    working_memory = accessor.get_working_memory()
    system_stats = accessor.get_system_memory_stats()
    namespace_counts = system_stats.get("by_namespace", {})
    governance_summary = accessor.get_governance_summary()
    namespace_policies = governance_summary.get("namespace_policies", {})
    long_term_policy = namespace_policies.get("conversation_summary", {})
    permanent_policy = namespace_policies.get("skill_evolution", {})

    return MemoryLayersResponse(
        working=MemoryLayerSummaryResponse(
            layer="working",
            namespaces=["memory.json"],
            entry_count=len(working_memory.get("facts", [])),
            available=True,
            governance_mode=governance_summary.get("mode"),
            confidence_threshold=governance_summary.get("confidence_threshold"),
        ),
        long_term=MemoryLayerSummaryResponse(
            layer="long_term",
            namespaces=list(LONG_TERM_MEMORY_NAMESPACES),
            entry_count=sum(int(namespace_counts.get(namespace, 0)) for namespace in LONG_TERM_MEMORY_NAMESPACES),
            available=True,
            governance_mode=governance_summary.get("mode"),
            confidence_threshold=governance_summary.get("confidence_threshold"),
            retention_days=long_term_policy.get("ttl_days"),
            immutable=bool(long_term_policy.get("immutable", False)),
        ),
        permanent=MemoryLayerSummaryResponse(
            layer="permanent",
            namespaces=list(PERMANENT_MEMORY_NAMESPACES),
            entry_count=sum(int(namespace_counts.get(namespace, 0)) for namespace in PERMANENT_MEMORY_NAMESPACES),
            available=True,
            governance_mode=governance_summary.get("mode"),
            confidence_threshold=governance_summary.get("confidence_threshold"),
            retention_days=permanent_policy.get("ttl_days"),
            immutable=bool(permanent_policy.get("immutable", False)),
        ),
    )


@router.get(
    "/memory/governance",
    response_model=MemoryGovernanceSummaryResponse,
    summary="Get Memory Governance Summary",
    description="Retrieve the effective provenance, confidence, and retention policy applied to governed memory writes.",
)
async def get_memory_governance() -> MemoryGovernanceSummaryResponse:
    summary = build_memory_governance_summary()
    namespace_policies = {
        namespace: MemoryRetentionPolicyResponse(**policy)
        for namespace, policy in summary.get("namespace_policies", {}).items()
    }
    return MemoryGovernanceSummaryResponse(
        enabled=bool(summary.get("enabled", False)),
        mode=str(summary.get("mode", "enforce")),
        confidence_threshold=float(summary.get("confidence_threshold", 0.0)),
        long_term_retention_days=int(summary.get("long_term_retention_days", 0)),
        permanent_retention_days=int(summary.get("permanent_retention_days", 0)),
        immutable_namespaces=list(summary.get("immutable_namespaces", [])),
        namespace_policies=namespace_policies,
    )


# ---------------------------------------------------------------------------
# Global Memory (user-editable persistent prompt / instructions)
# ---------------------------------------------------------------------------

_GLOBAL_MEMORY_PATH = Path(".octoagent/global_memory.json")


class GlobalMemoryEntry(BaseModel):
    id: str = Field(..., description="Unique entry identifier")
    title: str = Field(default="", description="Short label")
    content: str = Field(default="", description="Prompt / instruction body")
    source: str = Field(default="manual", description="Origin: manual | file-import")
    createdAt: str = Field(default="", description="ISO-8601 creation time")
    updatedAt: str = Field(default="", description="ISO-8601 last update time")


class GlobalMemoryStore(BaseModel):
    entries: list[GlobalMemoryEntry] = Field(default_factory=list)


class GlobalMemoryUpdateRequest(BaseModel):
    title: str = Field(default="")
    content: str = Field(default="")


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
    from fastapi import HTTPException

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


@router.post(
    "/memory/global/import",
    response_model=GlobalMemoryEntry,
    summary="Import a file as a global memory entry",
)
async def import_global_memory(file: UploadFile = File(...)) -> GlobalMemoryEntry:
    import uuid
    from datetime import datetime

    filename = file.filename or "untitled"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_IMPORT_EXTENSIONS:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(_ALLOWED_IMPORT_EXTENSIONS))}",
        )

    raw_bytes = await file.read()

    # For .doc/.docx, try to extract text; fall back to raw decode
    content = ""
    if ext == ".docx":
        try:
            import io
            import zipfile

            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                from xml.etree import ElementTree

                doc_xml = zf.read("word/document.xml")
                tree = ElementTree.fromstring(doc_xml)  # noqa: S314
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                paragraphs = tree.findall(".//w:p", ns)
                content = "\n".join(
                    "".join(node.text or "" for node in p.findall(".//w:t", ns))
                    for p in paragraphs
                )
        except Exception:
            content = raw_bytes.decode("utf-8", errors="replace")
    elif ext == ".json":
        try:
            parsed = json.loads(raw_bytes.decode("utf-8", errors="replace"))
            content = json.dumps(parsed, ensure_ascii=False, indent=2)
        except Exception:
            content = raw_bytes.decode("utf-8", errors="replace")
    else:
        content = raw_bytes.decode("utf-8", errors="replace")

    store = _load_global_memory()
    now = datetime.now(UTC).isoformat()
    entry = GlobalMemoryEntry(
        id=str(uuid.uuid4()),
        title=filename,
        content=content.strip(),
        source=f"file-import:{filename}",
        createdAt=now,
        updatedAt=now,
    )
    store.entries.append(entry)
    _save_global_memory(store)
    return entry


# ── System Memory (RAG) — read-only endpoints ─────────────────────────


class SystemMemorySearchRequest(BaseModel):
    query: str = Field(..., description="Search query text")
    namespace: str | None = Field(None, description="Filter by namespace")
    top_k: int = Field(10, ge=1, le=MAX_SYSTEM_MEMORY_SEARCH_TOP_K, description="Max results")


class SystemMemoryCleanupRequest(BaseModel):
    namespace: str | None = Field(default=None, description="Optional namespace to clean up")
    limit: int | None = Field(default=None, description="Optional maximum number of expired entries to delete")


class SystemMemoryCleanupResponse(BaseModel):
    deleted_count: int = 0
    deleted_by_namespace: dict[str, int] = Field(default_factory=dict)
    namespace: str | None = None


@router.get("/memory/system/stats")
async def get_system_memory_stats():
    """Return statistics of the system RAG memory store."""
    try:
        store = get_system_rag_store()
        return store.stats()
    except Exception as e:
        return {"error": str(e), "total_entries": 0}


@router.post("/memory/system/cleanup", response_model=SystemMemoryCleanupResponse)
async def cleanup_system_memory(req: SystemMemoryCleanupRequest) -> SystemMemoryCleanupResponse:
    """Delete expired system-memory entries."""
    store = get_system_rag_store()
    try:
        result = store.cleanup_expired(namespace=req.namespace, limit=req.limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SystemMemoryCleanupResponse.model_validate(result)


@router.post("/memory/system/search")
async def search_system_memory(req: SystemMemorySearchRequest):
    """Semantic search across system-generated memories."""
    store = get_system_rag_store()
    try:
        results = store.search(req.query, namespace=req.namespace, top_k=req.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "results": [
            {
                "id": r.id,
                "namespace": r.namespace,
                "content": r.content,
                "metadata": r.metadata,
                "score": r.score,
            }
            for r in results
        ]
    }


@router.get("/memory/system/list")
async def list_system_memory(
    namespace: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List system memory entries (newest first)."""
    store = get_system_rag_store()
    try:
        entries = store.list_entries(namespace=namespace, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "limit": min(limit, MAX_SYSTEM_MEMORY_LIST_LIMIT),
        "offset": offset,
        "entries": [
            {
                "id": e.id,
                "namespace": e.namespace,
                "content": e.content,
                "metadata": e.metadata,
            }
            for e in entries
        ]
    }

