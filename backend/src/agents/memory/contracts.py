"""Layered memory contracts for working, long-term, and permanent memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

MemoryLayerKind = Literal["working", "long_term", "permanent"]
MemoryRetentionMode = Literal["window", "expires_at", "permanent"]


@dataclass(frozen=True)
class MemoryProvenance:
    """Normalized provenance describing how a memory entry was produced."""

    source: str = "system"
    source_kind: str = "system"
    source_thread_id: str | None = None
    pipeline: str = "octoagent"
    agent_name: str | None = None
    recorded_at: str = ""


@dataclass(frozen=True)
class MemoryRetentionPolicy:
    """Retention contract applied to a memory entry."""

    mode: MemoryRetentionMode = "window"
    namespace: str = ""
    ttl_days: int | None = None
    expires_at: str | None = None
    immutable: bool = False
    reason: str = ""


@dataclass(frozen=True)
class MemoryGovernanceDecision:
    """Result of evaluating whether a memory write should persist."""

    allowed: bool = True
    reason: str = "accepted"
    policy_name: str = "default"
    namespace: str = ""
    confidence: float = 0.0
    threshold: float = 0.0
    mode: str = "enforce"
    evaluated_at: str = ""


@dataclass(frozen=True)
class GovernedMemoryWriteResult:
    """Normalized write result produced by the memory governance layer."""

    entry_id: str | None = None
    namespace: str = ""
    allowed: bool = False
    confidence: float = 0.0
    provenance: MemoryProvenance = field(default_factory=MemoryProvenance)
    retention: MemoryRetentionPolicy = field(default_factory=MemoryRetentionPolicy)
    governance: MemoryGovernanceDecision = field(default_factory=MemoryGovernanceDecision)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemorySearchEntry:
    """Normalized search result shared across memory layers."""

    id: str
    namespace: str
    content: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: MemoryProvenance | None = None
    confidence: float | None = None
    retention: MemoryRetentionPolicy | None = None
    governance: MemoryGovernanceDecision | None = None


@dataclass(frozen=True)
class MemoryLayerSnapshot:
    """Snapshot for a single memory layer."""

    layer: MemoryLayerKind
    namespaces: tuple[str, ...] = ()
    entries: tuple[MemorySearchEntry, ...] = ()
    working_memory: dict[str, Any] | None = None
    governance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LayeredMemoryContext:
    """Three-tier memory snapshot for future provider-agnostic retrieval."""

    working: MemoryLayerSnapshot
    long_term: MemoryLayerSnapshot
    permanent: MemoryLayerSnapshot


@runtime_checkable
class MemoryLayerAccessorContract(Protocol):
    """Compatibility contract over the current memory implementations."""

    def get_working_memory(self, agent_name: str | None = None) -> dict[str, Any]:
        """Return working/session-style memory for the agent or global scope."""

    def reload_working_memory(self, agent_name: str | None = None) -> dict[str, Any]:
        """Force reload the working memory backing store."""

    def format_working_memory_context(
        self,
        agent_name: str | None = None,
        *,
        max_tokens: int = 2000,
    ) -> str:
        """Return injection-ready working memory context."""

    def store_long_term_memory(
        self,
        unit,
        *,
        namespace: str = "conversation_summary",
        agent_name: str | None = None,
    ) -> str:
        """Persist an atomic memory unit to the long-term memory layer."""

    def governed_store_long_term_memory(
        self,
        unit,
        *,
        namespace: str = "conversation_summary",
        agent_name: str | None = None,
    ) -> GovernedMemoryWriteResult:
        """Persist an atomic memory unit while exposing governance metadata."""

    def search_long_term(self, query: str, *, top_k: int = 5) -> list[MemorySearchEntry]:
        """Search long-term memory namespaces."""

    def search_permanent(self, query: str, *, top_k: int = 5) -> list[MemorySearchEntry]:
        """Search permanent memory namespaces."""

    def get_system_memory_stats(self) -> dict[str, Any]:
        """Return aggregate stats from the vector-backed system memory store."""

    def get_governance_summary(self) -> dict[str, Any]:
        """Return the effective write-governance summary for layered memory."""

    def get_layered_context(
        self,
        *,
        agent_name: str | None = None,
        query: str | None = None,
        top_k: int = 5,
    ) -> LayeredMemoryContext:
        """Return a snapshot across working, long-term, and permanent layers."""