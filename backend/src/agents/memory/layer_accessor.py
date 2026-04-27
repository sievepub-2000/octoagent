"""Compatibility facade over the current OctoAgent memory implementations."""

from __future__ import annotations

from typing import Any

from src.agents.memory.contracts import (
    GovernedMemoryWriteResult,
    LayeredMemoryContext,
    MemoryLayerSnapshot,
    MemorySearchEntry,
)
from src.agents.memory.governance import (
    LONG_TERM_MEMORY_NAMESPACES,
    PERMANENT_MEMORY_NAMESPACES,
    build_memory_governance_summary,
    hydrate_memory_governance,
    hydrate_memory_provenance,
    hydrate_memory_retention,
    prepare_memory_write,
)
from src.agents.memory.prompt import format_memory_for_injection
from src.agents.memory.simplemem_bridge import AtomicMemoryUnit
from src.agents.memory.system_rag_store import get_system_rag_store
from src.agents.memory.updater import get_memory_data, reload_memory_data


class MemoryLayerAccessor:
    """Facade that presents the existing memory system as layered contracts."""

    def get_working_memory(self, agent_name: str | None = None) -> dict[str, Any]:
        return get_memory_data(agent_name)

    def reload_working_memory(self, agent_name: str | None = None) -> dict[str, Any]:
        return reload_memory_data(agent_name)

    def format_working_memory_context(
        self,
        agent_name: str | None = None,
        *,
        max_tokens: int = 2000,
    ) -> str:
        return format_memory_for_injection(
            self.get_working_memory(agent_name),
            max_tokens=max_tokens,
        )

    def store_long_term_memory(
        self,
        unit: AtomicMemoryUnit,
        *,
        namespace: str = "conversation_summary",
        agent_name: str | None = None,
    ) -> str:
        return self.governed_store_long_term_memory(
            unit,
            namespace=namespace,
            agent_name=agent_name,
        ).entry_id or ""

    def governed_store_long_term_memory(
        self,
        unit: AtomicMemoryUnit,
        *,
        namespace: str = "conversation_summary",
        agent_name: str | None = None,
    ) -> GovernedMemoryWriteResult:
        metadata = dict(unit.metadata or {})
        if unit.keywords:
            metadata["keywords"] = list(unit.keywords)
        if unit.persons:
            metadata["persons"] = list(unit.persons)
        if unit.entities:
            metadata["entities"] = list(unit.entities)
        if unit.topic:
            metadata["topic"] = unit.topic
        if unit.timestamp_iso:
            metadata["timestamp_iso"] = unit.timestamp_iso
        governed = prepare_memory_write(
            namespace,
            agent_name=agent_name,
            metadata=metadata,
            content=unit.content,
        )
        if not governed.allowed:
            return governed

        entry_id = get_system_rag_store().add(
            namespace,
            unit.content,
            agent_name=agent_name,
            metadata=governed.metadata,
        )
        return GovernedMemoryWriteResult(
            entry_id=entry_id or None,
            namespace=namespace,
            allowed=bool(entry_id),
            confidence=governed.confidence,
            provenance=governed.provenance,
            retention=governed.retention,
            governance=governed.governance,
            metadata=governed.metadata,
        )

    def search_long_term(self, query: str, *, top_k: int = 5) -> list[MemorySearchEntry]:
        return self._search_namespaces(query, LONG_TERM_MEMORY_NAMESPACES, top_k=top_k)

    def search_permanent(self, query: str, *, top_k: int = 5) -> list[MemorySearchEntry]:
        return self._search_namespaces(query, PERMANENT_MEMORY_NAMESPACES, top_k=top_k)

    def get_system_memory_stats(self) -> dict[str, Any]:
        return get_system_rag_store().stats()

    def get_governance_summary(self) -> dict[str, Any]:
        return build_memory_governance_summary()

    def get_layered_context(
        self,
        *,
        agent_name: str | None = None,
        query: str | None = None,
        top_k: int = 5,
    ) -> LayeredMemoryContext:
        working_memory = self.get_working_memory(agent_name)
        long_term_entries = tuple(self.search_long_term(query, top_k=top_k)) if query else ()
        permanent_entries = tuple(self.search_permanent(query, top_k=top_k)) if query else ()
        governance_summary = self.get_governance_summary()
        return LayeredMemoryContext(
            working=MemoryLayerSnapshot(
                layer="working",
                working_memory=working_memory,
                governance={
                    "enabled": governance_summary["enabled"],
                    "mode": governance_summary["mode"],
                },
            ),
            long_term=MemoryLayerSnapshot(
                layer="long_term",
                namespaces=LONG_TERM_MEMORY_NAMESPACES,
                entries=long_term_entries,
                governance={
                    namespace: governance_summary["namespace_policies"][namespace]
                    for namespace in LONG_TERM_MEMORY_NAMESPACES
                },
            ),
            permanent=MemoryLayerSnapshot(
                layer="permanent",
                namespaces=PERMANENT_MEMORY_NAMESPACES,
                entries=permanent_entries,
                governance={
                    namespace: governance_summary["namespace_policies"][namespace]
                    for namespace in PERMANENT_MEMORY_NAMESPACES
                },
            ),
        )

    def _search_namespaces(
        self,
        query: str,
        namespaces: tuple[str, ...],
        *,
        top_k: int,
    ) -> list[MemorySearchEntry]:
        if not query.strip():
            return []
        store = get_system_rag_store()
        results: list[MemorySearchEntry] = []
        for namespace in namespaces:
            for entry in store.search(query, namespace=namespace, top_k=top_k):
                results.append(
                    MemorySearchEntry(
                        id=entry.id,
                        namespace=entry.namespace,
                        content=entry.content,
                        score=entry.score,
                        metadata=dict(entry.metadata),
                        provenance=hydrate_memory_provenance(entry.metadata),
                        confidence=float(entry.metadata.get("memory_confidence"))
                        if entry.metadata.get("memory_confidence") is not None
                        else None,
                        retention=hydrate_memory_retention(entry.metadata),
                        governance=hydrate_memory_governance(entry.metadata),
                    )
                )
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]


_layer_accessor: MemoryLayerAccessor | None = None


def get_memory_layer_accessor() -> MemoryLayerAccessor:
    """Get the shared layered memory accessor."""

    global _layer_accessor
    if _layer_accessor is None:
        _layer_accessor = MemoryLayerAccessor()
    return _layer_accessor