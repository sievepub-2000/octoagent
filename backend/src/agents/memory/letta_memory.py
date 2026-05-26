"""Letta-inspired core blocks and archival memory facade.

This module does not run Letta as a sidecar. It imports the useful memory
model into OctoAgent's existing stores:

* core memory blocks are always-visible structured sections in memory.json
* archival memory is a semantic namespace in the DuckDB-backed system memory
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from src.agents.memory.system_rag_store import get_system_rag_store
from src.agents.memory.updater import _save_memory_to_file, ensure_memory_schema, get_memory_data

DEFAULT_BLOCK_DESCRIPTIONS = {
    "persona": "The persona block: Stores details about the assistant identity, behavior, and response style.",
    "human": "The human block: Stores key details about the person being helped, including durable preferences and context.",
    "task_state": "Tracks active long-running task objectives, constraints, progress, risks, and next actions.",
    "tool_policy": "Stores durable tool-use lessons and constraints learned from prior execution.",
}


@dataclass(frozen=True)
class MemoryBlock:
    label: str
    description: str
    value: str
    limit: int = 5000
    read_only: bool = False
    updated_at: str = ""

    def clipped(self) -> MemoryBlock:
        return MemoryBlock(
            label=self.label,
            description=self.description,
            value=self.value[: max(1, self.limit)],
            limit=self.limit,
            read_only=self.read_only,
            updated_at=self.updated_at,
        )


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _blocks_dict(memory_data: dict[str, Any]) -> dict[str, Any]:
    blocks = memory_data.get("memory_blocks")
    if not isinstance(blocks, dict):
        blocks = {}
        memory_data["memory_blocks"] = blocks
    return blocks


def _hydrate(label: str, raw: Any) -> MemoryBlock:
    if not isinstance(raw, dict):
        raw = {"value": str(raw or "")}
    return MemoryBlock(
        label=label,
        description=str(raw.get("description") or DEFAULT_BLOCK_DESCRIPTIONS.get(label, f"Memory block '{label}'.")),
        value=str(raw.get("value") or ""),
        limit=max(1, int(raw.get("limit") or 5000)),
        read_only=bool(raw.get("read_only", False)),
        updated_at=str(raw.get("updated_at") or ""),
    ).clipped()


class LettaMemoryService:
    """Facade for Letta-style core and archival memory."""

    def list_blocks(self, agent_name: str | None = None) -> list[MemoryBlock]:
        memory_data = ensure_memory_schema(get_memory_data(agent_name))
        return [_hydrate(label, raw) for label, raw in sorted(_blocks_dict(memory_data).items())]

    def upsert_block(
        self,
        label: str,
        value: str,
        *,
        description: str | None = None,
        limit: int = 5000,
        read_only: bool = False,
        agent_name: str | None = None,
        override_read_only: bool = False,
    ) -> MemoryBlock:
        clean_label = label.strip()
        if not clean_label:
            raise ValueError("label is required")
        memory_data = ensure_memory_schema(get_memory_data(agent_name))
        blocks = _blocks_dict(memory_data)
        existing = _hydrate(clean_label, blocks.get(clean_label)) if clean_label in blocks else None
        if existing and existing.read_only and not override_read_only:
            raise PermissionError(f"memory block '{clean_label}' is read-only")
        block = MemoryBlock(
            label=clean_label,
            description=description or (existing.description if existing else DEFAULT_BLOCK_DESCRIPTIONS.get(clean_label, f"Memory block '{clean_label}'.")),
            value=value,
            limit=max(1, int(limit or existing.limit if existing else limit)),
            read_only=read_only if not existing else bool(read_only or existing.read_only),
            updated_at=_now(),
        ).clipped()
        blocks[clean_label] = asdict(block)
        _save_memory_to_file(memory_data, agent_name)
        return block

    def delete_block(
        self,
        label: str,
        *,
        agent_name: str | None = None,
        override_read_only: bool = False,
    ) -> bool:
        clean_label = label.strip()
        memory_data = ensure_memory_schema(get_memory_data(agent_name))
        blocks = _blocks_dict(memory_data)
        if clean_label not in blocks:
            return False
        existing = _hydrate(clean_label, blocks[clean_label])
        if existing.read_only and not override_read_only:
            raise PermissionError(f"memory block '{clean_label}' is read-only")
        del blocks[clean_label]
        _save_memory_to_file(memory_data, agent_name)
        return True

    def format_blocks_context(self, agent_name: str | None = None) -> str:
        blocks = self.list_blocks(agent_name)
        if not blocks:
            return ""
        lines = ["<memory_blocks>"]
        for block in blocks:
            lines.extend(
                [
                    f"<{block.label}>",
                    f"<description>{block.description}</description>",
                    "<metadata>",
                    f"- chars_current={len(block.value)}",
                    f"- chars_limit={block.limit}",
                    f"- read_only={str(block.read_only).lower()}",
                    "</metadata>",
                    f"<value>{block.value}</value>",
                    f"</{block.label}>",
                ]
            )
        lines.append("</memory_blocks>")
        return "\n".join(lines)

    def archival_insert(
        self,
        content: str,
        *,
        tags: list[str] | None = None,
        agent_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        meta = dict(metadata or {})
        meta.update({"source": "letta_archival_memory", "source_kind": "agent_archival", "pipeline": "letta_memory", "tags": tags or []})
        return get_system_rag_store().add("archival_memory", content, agent_name=agent_name, metadata=meta)

    def archival_search(
        self,
        query: str,
        *,
        top_k: int = 5,
    ):
        return get_system_rag_store().search(query, namespace="archival_memory", top_k=top_k)


_service: LettaMemoryService | None = None


def get_letta_memory_service() -> LettaMemoryService:
    global _service
    if _service is None:
        _service = LettaMemoryService()
    return _service


__all__ = ["MemoryBlock", "LettaMemoryService", "get_letta_memory_service"]
