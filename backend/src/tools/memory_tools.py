from __future__ import annotations

import json
from typing import Literal

from langchain_core.tools import tool

MemoryNamespace = Literal["conversation_summary", "archival_memory", "skill_evolution", "system_insight"]


@tool("search_memory", parse_docstring=True)
def search_memory_tool(
    query: str,
    namespace: MemoryNamespace | None = None,
    top_k: int = 5,
) -> str:
    """Search long-term system memory with semantic and keyword retrieval.

    Use this when a task depends on prior conversations, learned patterns,
    self-evolution notes, or remembered system insights.

    Args:
        query: Natural-language search query.
        namespace: Optional memory namespace filter.
        top_k: Maximum number of results to return.
    """

    from src.agents.memory.simplemem_bridge import get_simplemem_bridge

    if not query.strip():
        return "Error: query is required."

    safe_top_k = max(1, min(int(top_k), 10))
    results = get_simplemem_bridge().retrieve(
        query,
        namespace=namespace,
        top_k=safe_top_k,
        enable_planning=True,
    )
    payload = {
        "query": query,
        "namespace": namespace,
        "results": [
            {
                "id": entry.id,
                "namespace": entry.namespace,
                "content": entry.content,
                "score": float(getattr(entry, "score", 0.0)),
                "metadata": dict(entry.metadata or {}),
            }
            for entry in results
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool("memory_block_upsert", parse_docstring=True)
def memory_block_upsert_tool(
    label: str,
    value: str,
    description: str | None = None,
    limit: int = 5000,
    read_only: bool = False,
) -> str:
    """Create or replace a Letta-style always-visible core memory block.

    Args:
        label: Unique block label such as persona, human, task_state, or tool_policy.
        value: Block content.
        description: Description that tells the agent how to use the block.
        limit: Character limit for the block.
        read_only: Whether future agent writes should be blocked.
    """

    from src.agents.memory.letta_memory import get_letta_memory_service

    block = get_letta_memory_service().upsert_block(
        label,
        value,
        description=description,
        limit=limit,
        read_only=read_only,
    )
    return json.dumps({"block": block.__dict__}, ensure_ascii=False, indent=2)


@tool("memory_block_list", parse_docstring=True)
def memory_block_list_tool() -> str:
    """List Letta-style core memory blocks currently visible to the agent."""

    from src.agents.memory.letta_memory import get_letta_memory_service

    blocks = get_letta_memory_service().list_blocks()
    return json.dumps({"blocks": [block.__dict__ for block in blocks]}, ensure_ascii=False, indent=2)


@tool("archival_memory_insert", parse_docstring=True)
def archival_memory_insert_tool(content: str, tags: list[str] | None = None) -> str:
    """Insert a durable Letta-style archival memory fact for semantic retrieval.

    Args:
        content: Self-contained fact or knowledge to remember.
        tags: Optional tags used to organize the memory.
    """

    from src.agents.memory.letta_memory import get_letta_memory_service

    entry_id = get_letta_memory_service().archival_insert(content, tags=tags)
    return json.dumps({"entry_id": entry_id, "namespace": "archival_memory"}, ensure_ascii=False, indent=2)


@tool("archival_memory_search", parse_docstring=True)
def archival_memory_search_tool(query: str, top_k: int = 5) -> str:
    """Search Letta-style archival memory.

    Args:
        query: Natural-language search query.
        top_k: Maximum number of matches.
    """

    from src.agents.memory.letta_memory import get_letta_memory_service

    results = get_letta_memory_service().archival_search(query, top_k=max(1, min(int(top_k), 10)))
    return json.dumps(
        {
            "query": query,
            "namespace": "archival_memory",
            "results": [
                {
                    "id": entry.id,
                    "namespace": entry.namespace,
                    "content": entry.content,
                    "score": float(getattr(entry, "score", 0.0)),
                    "metadata": dict(entry.metadata or {}),
                }
                for entry in results
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
