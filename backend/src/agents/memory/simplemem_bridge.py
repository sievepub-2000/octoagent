"""SimpleMem integration bridge for OctoAgent memory system.

Implements the three-stage SimpleMem pipeline using OctoAgent's own
LLM and embedding infrastructure — no external SimpleMem library required:

  Stage 1 — Semantic Structured Compression
    Dialogues → compact, atomic, self-contained memory units via LLM.

  Stage 2 — Online Semantic Synthesis
    Related fragments are merged on the fly during the write phase.

  Stage 3 — Intent-Aware Hybrid Retrieval
    Query → semantic + keyword + metadata parallel retrieval → ranked results.

This bridge is used by MemoryMiddleware and the MemoryUpdateQueue to
store high-quality, deduplicated memories in SystemRAGStore instead of
raw conversation excerpts.

Reference: aiming-lab/SimpleMem (arXiv 2601.02553)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

from src.agents.memory.text_normalization import repair_mojibake

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class AtomicMemoryUnit:
    """A single compressed, self-contained memory fact.

    Corresponds to one atomic entry {m_k} in the SimpleMem paper.

    Sprint-1 P0 additions (A-MEM episodic decay): ``importance``, ``cite_count``,
    and ``last_access_iso`` are populated lazily by the retriever/feedback loop
    and used by the maintenance scheduler to age out cold memories. All fields
    are backward compatible — older serialised units load with defaults.
    """

    entry_id: str
    content: str  # Lossless restatement — no pronouns, absolute time
    keywords: list[str] = field(default_factory=list)
    persons: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    topic: str = ""
    timestamp_iso: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5  # 0.0–1.0; updated by feedback
    cite_count: int = 0  # increments each time retriever surfaces this unit
    last_access_iso: str = ""  # ISO-8601 of last retrieval/citation

    def dedup_key(self) -> str:
        """Stable content hash used for deduplication."""
        norm = re.sub(r"\s+", " ", self.content.lower().strip())
        return hashlib.sha256(norm.encode()).hexdigest()[:16]


@dataclass
class RetrievalResult:
    """A single result from hybrid retrieval."""

    unit: AtomicMemoryUnit
    semantic_score: float = 0.0
    keyword_score: float = 0.0
    combined_score: float = 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 — Semantic Structured Compression
# ──────────────────────────────────────────────────────────────────────────────

_COMPRESSION_SYSTEM_PROMPT = """You are a memory compression engine for an AI agent.
Your task is to extract concise, self-contained atomic facts from a conversation.

Rules:
1. Resolve all coreferences — replace pronouns with their referents ("he" → person's name).
2. Convert relative time expressions to absolute ISO-8601 (use the session timestamp as anchor).
3. Each fact must be independent; no "as mentioned above" or implied context.
4. Discard small talk, greetings, and zero-information exchanges.
5. Output ONLY a JSON array of objects, each with:
   {
     "content":   "<self-contained fact>",
     "keywords":  ["<key_term>", ...],
     "persons":   ["<person_name>", ...],
     "entities":  ["<place/org/thing>", ...],
     "topic":     "<one-phrase topic>",
     "timestamp": "<ISO-8601 or empty>"
   }
Keep each fact under 200 characters. Output valid JSON only."""

_SYNTHESIS_SYSTEM_PROMPT = """You are a memory synthesis engine.
Given a set of closely related atomic memory facts, merge them into a single, more
complete, non-redundant fact.

Rules:
1. Preserve all unique information from the input facts.
2. The output must be a single compact fact string (≤ 300 characters).
3. Keep people, places, and timestamps intact.
4. Output ONLY the merged fact string, no JSON, no labels."""


class SimpleMemCompressor:
    """Stage 1: compress a dialogue window into atomic memory units."""

    WINDOW_SIZE = 10  # messages per compression batch

    def __init__(self, llm_client: Any) -> None:
        """
        Args:
            llm_client: Any LangChain-compatible chat model (supports .invoke).
        """
        self._llm = llm_client

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def compress(
        self,
        messages: list[dict[str, str]],
        *,
        session_timestamp: str | None = None,
        agent_name: str | None = None,
    ) -> list[AtomicMemoryUnit]:
        """Compress a conversation into atomic memory units.

        Args:
            messages: List of {"role": "user"|"assistant", "content": "..."}.
            session_timestamp: ISO-8601 anchor for relative time resolution.
            agent_name: Optional agent name for metadata.

        Returns:
            List of AtomicMemoryUnit, deduplicated.
        """
        if not messages:
            return []

        # Split into windows
        windows = [messages[i : i + self.WINDOW_SIZE] for i in range(0, len(messages), self.WINDOW_SIZE)]
        all_units: list[AtomicMemoryUnit] = []
        seen_keys: set[str] = set()

        for window in windows:
            units = self._compress_window(
                window,
                session_timestamp=session_timestamp,
                agent_name=agent_name,
            )
            for u in units:
                k = u.dedup_key()
                if k not in seen_keys:
                    seen_keys.add(k)
                    all_units.append(u)

        return all_units

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _compress_window(
        self,
        window: list[dict[str, str]],
        *,
        session_timestamp: str | None,
        agent_name: str | None,
    ) -> list[AtomicMemoryUnit]:
        """LLM call for one window."""

        if self._llm is None or not hasattr(self._llm, "invoke"):
            return self._fallback_compress(window, agent_name=agent_name)

        dialogue_text = "\n".join(f"[{m.get('role', 'user').upper()}] {m.get('content', '')}" for m in window)
        if session_timestamp:
            dialogue_text = f"Session time: {session_timestamp}\n\n{dialogue_text}"

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            response = self._llm.invoke(
                [
                    SystemMessage(content=_COMPRESSION_SYSTEM_PROMPT),
                    HumanMessage(content=dialogue_text),
                ]
            )
            raw = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.warning("SimpleMemCompressor LLM call failed: %s", exc)
            return self._fallback_compress(window, agent_name=agent_name)

        units = self._parse_json_units(raw, agent_name=agent_name)
        if not units:
            units = self._fallback_compress(window, agent_name=agent_name)
        return units

    def _parse_json_units(
        self,
        raw: str,
        *,
        agent_name: str | None,
    ) -> list[AtomicMemoryUnit]:
        """Parse LLM JSON output into AtomicMemoryUnit list."""
        import uuid

        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        # Extract first JSON array
        m = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not m:
            return []

        try:
            items = json.loads(m.group())
        except json.JSONDecodeError:
            logger.debug("SimpleMemCompressor: failed to parse JSON from LLM output")
            return []

        if not isinstance(items, list):
            return []

        units: list[AtomicMemoryUnit] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            content = repair_mojibake(str(item.get("content", ""))).strip()
            if not content:
                continue
            entry_id = uuid.uuid4().hex[:16]
            meta: dict[str, Any] = {}
            if agent_name:
                meta["agent_name"] = agent_name
            units.append(
                AtomicMemoryUnit(
                    entry_id=entry_id,
                    content=content,
                    keywords=[str(k) for k in item.get("keywords", []) if k],
                    persons=[str(p) for p in item.get("persons", []) if p],
                    entities=[str(e) for e in item.get("entities", []) if e],
                    topic=str(item.get("topic", "")),
                    timestamp_iso=str(item.get("timestamp", "")),
                    metadata=meta,
                )
            )
        return units

    def _fallback_compress(
        self,
        window: list[dict[str, str]],
        *,
        agent_name: str | None,
    ) -> list[AtomicMemoryUnit]:
        """Simple fallback when LLM call fails: store as one flat summary."""
        import uuid

        parts = [f"{m.get('role', 'user')}: {str(m.get('content', ''))[:200]}" for m in window]
        content = " | ".join(parts)[:500]
        meta: dict[str, Any] = {}
        if agent_name:
            meta["agent_name"] = agent_name
        return [
            AtomicMemoryUnit(
                entry_id=uuid.uuid4().hex[:16],
                content=content,
                metadata=meta,
            )
        ]


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 — Online Semantic Synthesis
# ──────────────────────────────────────────────────────────────────────────────


class SimpleMemSynthesizer:
    """Stage 2: merge related atomic units during write phase.

    Checks newly generated units against recent store entries.  If the
    cosine similarity exceeds a threshold the pair is merged with the LLM
    rather than stored as two separate fragments.
    """

    SIMILARITY_THRESHOLD = 0.88

    def __init__(self, llm_client: Any, embedding_svc: Any) -> None:
        self._llm = llm_client
        self._embed = embedding_svc

    def synthesize(
        self,
        new_units: list[AtomicMemoryUnit],
        existing_units: list[AtomicMemoryUnit],
    ) -> list[AtomicMemoryUnit]:
        """Merge new units with similar existing ones.

        Returns final list to write: existing entries are replaced by merged
        versions; truly-new entries are appended.
        """
        if not new_units:
            return []
        if not existing_units:
            return new_units

        # Embed all contents
        try:
            new_contents = [u.content for u in new_units]
            existing_contents = [u.content for u in existing_units]
            new_vecs = self._embed.embed(new_contents)
            ex_vecs = self._embed.embed(existing_contents)
        except Exception as exc:
            logger.debug("SimpleMemSynthesizer: embedding failed (%s), skipping synthesis", exc)
            return new_units

        import uuid

        final: list[AtomicMemoryUnit] = []
        for new_u, nv in zip(new_units, new_vecs):
            merged = False
            for i, (ex_u, ev) in enumerate(zip(existing_units, ex_vecs)):
                sim = _cosine(nv, ev)
                if sim >= self.SIMILARITY_THRESHOLD:
                    # Merge these two units
                    merged_content = self._merge_pair(ex_u.content, new_u.content)
                    merged_unit = AtomicMemoryUnit(
                        entry_id=uuid.uuid4().hex[:16],
                        content=merged_content,
                        keywords=list(set(ex_u.keywords + new_u.keywords)),
                        persons=list(set(ex_u.persons + new_u.persons)),
                        entities=list(set(ex_u.entities + new_u.entities)),
                        topic=new_u.topic or ex_u.topic,
                        timestamp_iso=new_u.timestamp_iso or ex_u.timestamp_iso,
                        metadata={**ex_u.metadata, **new_u.metadata, "merged": True},
                    )
                    # Replace existing slot
                    existing_units[i] = merged_unit
                    ex_vecs[i] = self._embed.embed_one(merged_content)
                    merged = True
                    break
            if not merged:
                final.append(new_u)

        # Collect any units that were merged into existing_units
        final.extend(u for u in existing_units if u.metadata.get("merged"))
        # Deduplicate by entry_id
        seen: set[str] = set()
        deduped: list[AtomicMemoryUnit] = []
        for u in final:
            if u.entry_id not in seen:
                seen.add(u.entry_id)
                deduped.append(u)
        return deduped

    def _merge_pair(self, a: str, b: str) -> str:
        if self._llm is None or not hasattr(self._llm, "invoke"):
            return f"{a}; {b}"[:400]

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            response = self._llm.invoke(
                [
                    SystemMessage(content=_SYNTHESIS_SYSTEM_PROMPT),
                    HumanMessage(content=f"Fact 1: {a}\nFact 2: {b}"),
                ]
            )
            merged = response.content if hasattr(response, "content") else str(response)
            return merged.strip()[:400]
        except Exception as exc:
            logger.debug("SimpleMemSynthesizer merge LLM failed: %s", exc)
            return f"{a}; {b}"[:400]


# ──────────────────────────────────────────────────────────────────────────────
# Stage 3 — Intent-Aware Hybrid Retrieval
# ──────────────────────────────────────────────────────────────────────────────

_QUERY_DECOMPOSE_PROMPT = """You are a retrieval planner.
Given a user query, generate 1-3 alternative sub-queries that would help retrieve
relevant long-term memories for answering the question.

Output ONLY a JSON array of strings (the sub-queries), nothing else.
Example: ["sub-query 1", "sub-query 2"]"""


class SimpleMemRetriever:
    """Stage 3: Intent-aware hybrid retrieval over SystemRAGStore.

    Extends the base semantic search with:
      - Query decomposition (planning) for complex queries
      - Keyword-based scoring boost
      - Result deduplication and ranking
    """

    def __init__(self, llm_client: Any, store: Any, embedding_svc: Any) -> None:
        self._llm = llm_client
        self._store = store
        self._embed = embedding_svc

    def retrieve(
        self,
        query: str,
        *,
        namespace: str | None = None,
        top_k: int = 8,
        enable_planning: bool = True,
    ) -> list[Any]:  # list[SystemMemoryEntry]
        """Hybrid retrieval: semantic + keyword + optional query decomposition.

        Args:
            query: User query string.
            namespace: Optional namespace filter.
            top_k: Maximum results to return.
            enable_planning: Whether to decompose complex queries.

        Returns:
            Ranked list of SystemMemoryEntry.
        """
        queries = [query]
        if enable_planning and self._is_complex_query(query):
            sub_queries = self._decompose_query(query)
            queries.extend(sub_queries)

        # Collect candidates from all sub-queries
        seen_ids: set[str] = set()
        candidates: list[Any] = []
        for q in queries:
            results = self._store.search(q, namespace=namespace, top_k=top_k)
            for r in results:
                if r.id not in seen_ids:
                    seen_ids.add(r.id)
                    candidates.append(r)

        # Re-rank with keyword boost
        query_keywords = set(_extract_keywords(query))
        for entry in candidates:
            kw_score = _keyword_overlap(query_keywords, set(_extract_keywords(entry.content)))
            entry.score = entry.score * 0.7 + kw_score * 0.3  # type: ignore[attr-defined]

        candidates.sort(key=lambda e: e.score, reverse=True)  # type: ignore[attr-defined]
        return candidates[:top_k]

    def _is_complex_query(self, query: str) -> bool:
        """Heuristic: queries with multiple aspects or temporal references are complex."""
        words = query.split()
        if len(words) > 12:
            return True
        temporal_words = {"when", "before", "after", "last", "first", "recent", "yesterday", "ago"}
        if any(w.lower() in temporal_words for w in words):
            return True
        if query.count("?") > 1 or " and " in query.lower():
            return True
        return False

    def _decompose_query(self, query: str) -> list[str]:
        if self._llm is None or not hasattr(self._llm, "invoke"):
            return []

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            resp = self._llm.invoke(
                [
                    SystemMessage(content=_QUERY_DECOMPOSE_PROMPT),
                    HumanMessage(content=query),
                ]
            )
            raw = resp.content if hasattr(resp, "content") else str(resp)
            cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
            m = re.search(r"\[.*\]", cleaned, re.DOTALL)
            if m:
                parts = json.loads(m.group())
                if isinstance(parts, list):
                    return [str(p) for p in parts if p][:3]
        except Exception as exc:
            logger.debug("SimpleMemRetriever decompose failed: %s", exc)
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Unified Facade
# ──────────────────────────────────────────────────────────────────────────────


class SimpleMemBridge:
    """Top-level facade for SimpleMem-style memory in OctoAgent.

    Usage::

        bridge = SimpleMemBridge.create()

        # Write — compress conversation and store atomic facts
        units = bridge.store_conversation(
            messages=[{"role": "user", "content": "..."}, ...],
            namespace="conversation_summary",
            agent_name="my_agent",
        )

        # Read — intent-aware hybrid retrieval
        results = bridge.retrieve(
            "What did we discuss about the deployment plan?",
            namespace="conversation_summary",
        )
    """

    def __init__(
        self,
        compressor: SimpleMemCompressor,
        synthesizer: SimpleMemSynthesizer,
        retriever: SimpleMemRetriever,
        store: Any,
    ) -> None:
        self._compressor = compressor
        self._synthesizer = synthesizer
        self._retriever = retriever
        self._store = store

    # ------------------------------------------------------------------ #
    # Factory                                                              #
    # ------------------------------------------------------------------ #

    @classmethod
    def create(cls) -> SimpleMemBridge:
        """Create a fully wired bridge using OctoAgent's default services."""
        from src.agents.memory.system_rag_store import get_system_rag_store
        from src.models.embedding_service import get_embedding_service

        store = get_system_rag_store()
        embed = get_embedding_service()

        # Use lightweight LLM if available; gracefully degrade if not
        try:
            from src.models.llm_pool import get_model_pool

            pool = get_model_pool()
            llm = pool.get_default_model()
        except Exception:
            llm = None  # bridge will use fallback paths

        compressor = SimpleMemCompressor(llm_client=llm)
        synthesizer = SimpleMemSynthesizer(llm_client=llm, embedding_svc=embed)
        retriever = SimpleMemRetriever(llm_client=llm, store=store, embedding_svc=embed)

        return cls(
            compressor=compressor,
            synthesizer=synthesizer,
            retriever=retriever,
            store=store,
        )

    # ------------------------------------------------------------------ #
    # Write                                                                #
    # ------------------------------------------------------------------ #

    def store_conversation(
        self,
        messages: list[Any],
        *,
        namespace: str = "conversation_summary",
        agent_name: str | None = None,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        session_timestamp: str | None = None,
        enable_synthesis: bool = True,
    ) -> list[AtomicMemoryUnit]:
        """Stage 1 + Stage 2: compress conversation and write to store.

        Args:
            messages: LangChain message objects or {"role":..., "content":...} dicts.
            namespace: SystemRAGStore namespace.
            agent_name: Optional agent identifier.
            thread_id: Optional thread ID for metadata.
            session_timestamp: ISO-8601 session anchor time.
            enable_synthesis: Whether to run online synthesis (Stage 2).

        Returns:
            List of AtomicMemoryUnit that were written.
        """
        # Normalise messages to plain dicts
        msg_dicts = _normalise_messages(messages)
        if not msg_dicts:
            return []

        # Stage 1: compress
        if session_timestamp is None:
            from datetime import datetime

            session_timestamp = datetime.now(UTC).isoformat()

        new_units = self._compressor.compress(
            msg_dicts,
            session_timestamp=session_timestamp,
            agent_name=agent_name,
        )
        if not new_units:
            return []

        # Stage 2: optional synthesis with recent store entries
        if enable_synthesis:
            try:
                recent = self._store.search("", namespace=namespace, top_k=20)
                existing = [
                    AtomicMemoryUnit(
                        entry_id=e.id,
                        content=e.content,
                        keywords=e.metadata.get("keywords", []),
                        persons=e.metadata.get("persons", []),
                        entities=e.metadata.get("entities", []),
                        topic=e.metadata.get("topic", ""),
                        metadata=e.metadata,
                    )
                    for e in recent
                ]
                new_units = self._synthesizer.synthesize(new_units, existing)
            except Exception as exc:
                logger.debug("Synthesis phase skipped: %s", exc)

        # Write all surviving units to store
        meta_base: dict[str, Any] = {}
        if metadata:
            meta_base.update(metadata)
        if thread_id:
            meta_base["thread_id"] = thread_id

        written: list[AtomicMemoryUnit] = []
        for unit in new_units:
            confidence = unit.metadata.get("confidence", 0.85)
            meta = {
                **meta_base,
                **unit.metadata,
                "keywords": unit.keywords,
                "persons": unit.persons,
                "entities": unit.entities,
                "topic": unit.topic,
                "timestamp_iso": unit.timestamp_iso,
                "confidence": confidence,
                "source": "simplemem_bridge",
                "source_kind": "simplemem_atomic_unit",
                "pipeline": "simplemem",
                "simplemem": True,
            }
            try:
                entry_id = self._store.add(
                    namespace,
                    unit.content,
                    agent_name=agent_name,
                    metadata=meta,
                )
                if entry_id:
                    written.append(unit)
            except Exception as exc:
                logger.warning("SimpleMemBridge store.add failed: %s", exc)

        logger.info(
            "SimpleMemBridge: stored %d atomic units in namespace=%s (thread=%s)",
            len(written),
            namespace,
            thread_id,
        )
        return written

    # ------------------------------------------------------------------ #
    # Read                                                                  #
    # ------------------------------------------------------------------ #

    def retrieve(
        self,
        query: str,
        *,
        namespace: str | None = None,
        top_k: int = 8,
        enable_planning: bool = True,
    ) -> list[Any]:  # list[SystemMemoryEntry]
        """Stage 3: intent-aware hybrid retrieval.

        Args:
            query: Natural language query.
            namespace: Optional namespace filter.
            top_k: Maximum results.
            enable_planning: Enable multi-query decomposition.

        Returns:
            Ranked list of SystemMemoryEntry from the store.
        """
        return self._retriever.retrieve(
            query,
            namespace=namespace,
            top_k=top_k,
            enable_planning=enable_planning,
        )

    # ------------------------------------------------------------------ #
    # Fact storage (for task summaries and learned lessons)                #
    # ------------------------------------------------------------------ #

    def store_fact(
        self,
        fact: str,
        *,
        namespace: str = "facts",
        metadata: dict | None = None,
    ) -> None:
        """Store a single fact string to the memory store.

        Used by TaskStateMiddleware to persist task completion summaries
        and by the harness MemoryStore to record learned facts.
        """
        try:
            from langchain_core.messages import SystemMessage

            msg = SystemMessage(content=fact)
            self.store_conversation(
                [msg],
                namespace=namespace,
                agent_name="system",
                thread_id=metadata.get("thread_id", "system") if metadata else "system",
                metadata=metadata or {},
                enable_synthesis=False,  # Facts are already compact
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).debug("store_fact failed: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ──────────────────────────────────────────────────────────────────────────────

_bridge: SimpleMemBridge | None = None


def get_simplemem_bridge() -> SimpleMemBridge:
    """Return the singleton SimpleMemBridge (created on first call)."""
    global _bridge
    if _bridge is None:
        _bridge = SimpleMemBridge.create()
    return _bridge


# ──────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ──────────────────────────────────────────────────────────────────────────────


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _extract_keywords(text: str) -> list[str]:
    """Simple keyword extraction: lower-cased words ≥ 4 chars, no stopwords."""
    stopwords = {
        "this",
        "that",
        "with",
        "from",
        "have",
        "will",
        "what",
        "when",
        "where",
        "which",
        "they",
        "them",
        "their",
        "there",
        "been",
        "were",
        "about",
        "more",
        "also",
        "into",
        "some",
        "than",
        "your",
        "then",
        "would",
        "could",
        "should",
    }
    tokens = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
    return [t for t in tokens if t not in stopwords]


def _keyword_overlap(a: set[str], b: set[str]) -> float:
    """Jaccard-style keyword overlap score."""
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def _normalise_messages(messages: list[Any]) -> list[dict[str, str]]:
    """Convert LangChain messages or plain dicts to {"role":..., "content":...}."""
    result: list[dict[str, str]] = []
    for m in messages:
        if isinstance(m, dict):
            role = m.get("role", "user")
            content = m.get("content", "")
        else:
            # LangChain message objects
            msg_type = getattr(m, "type", "human")
            role = "assistant" if msg_type == "ai" else "user"
            content = getattr(m, "content", "")
            if isinstance(content, list):
                # multimodal content blocks
                content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        content_str = repair_mojibake(str(content)).strip()
        if content_str:
            result.append({"role": role, "content": content_str})
    return result
