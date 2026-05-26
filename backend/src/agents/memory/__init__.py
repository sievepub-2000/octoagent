"""Memory module for OctoAgent.

This module provides a global memory mechanism that:
- Stores user context and conversation history in memory.json
- Uses LLM to summarize and extract facts from conversations
- Injects relevant memory into system prompts for personalized responses
"""

from src.agents.memory.contracts import (
    GovernedMemoryWriteResult,
    LayeredMemoryContext,
    MemoryGovernanceDecision,
    MemoryLayerAccessorContract,
    MemoryLayerSnapshot,
    MemoryProvenance,
    MemoryRetentionPolicy,
    MemorySearchEntry,
)
from src.agents.memory.governance import build_memory_governance_summary
from src.agents.memory.layer_accessor import (
    LONG_TERM_MEMORY_NAMESPACES,
    PERMANENT_MEMORY_NAMESPACES,
    MemoryLayerAccessor,
    get_memory_layer_accessor,
)
from src.agents.memory.letta_memory import LettaMemoryService, MemoryBlock, get_letta_memory_service
from src.agents.memory.prompt import (
    FACT_EXTRACTION_PROMPT,
    MEMORY_UPDATE_PROMPT,
    format_conversation_for_update,
    format_memory_for_injection,
)
from src.agents.memory.queue import (
    ConversationContext,
    MemoryUpdateQueue,
    get_memory_queue,
    reset_memory_queue,
)
from src.agents.memory.updater import (
    MemoryUpdater,
    get_memory_data,
    reload_memory_data,
    update_memory_from_conversation,
)

__all__ = [
    # Prompt utilities
    "MEMORY_UPDATE_PROMPT",
    "FACT_EXTRACTION_PROMPT",
    "format_memory_for_injection",
    "format_conversation_for_update",
    "GovernedMemoryWriteResult",
    "LayeredMemoryContext",
    "MemoryGovernanceDecision",
    "MemoryLayerAccessor",
    "MemoryLayerAccessorContract",
    "MemoryLayerSnapshot",
    "MemoryProvenance",
    "MemoryRetentionPolicy",
    "MemorySearchEntry",
    "LONG_TERM_MEMORY_NAMESPACES",
    "PERMANENT_MEMORY_NAMESPACES",
    "build_memory_governance_summary",
    "get_memory_layer_accessor",
    "MemoryBlock",
    "LettaMemoryService",
    "get_letta_memory_service",
    # Queue
    "ConversationContext",
    "MemoryUpdateQueue",
    "get_memory_queue",
    "reset_memory_queue",
    # Updater
    "MemoryUpdater",
    "get_memory_data",
    "reload_memory_data",
    "update_memory_from_conversation",
]
