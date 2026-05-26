"""Pydantic schemas for the memory router (extracted 2026-05-14).

Defined separately so the router module can shrink and so other modules can
import the schemas without pulling in router-level dependencies.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.agents.memory.system_rag_store import MAX_SYSTEM_MEMORY_SEARCH_TOP_K


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
