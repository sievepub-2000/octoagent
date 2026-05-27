"""Memory-governance write-path invariants.

`prepare_memory_write` is the single gate between agent-produced
content and the on-disk memory store. The contract:

* Every write is normalised with provenance + retention + confidence
  metadata under the canonical keys (`memory_provenance`,
  `memory_retention`, `memory_governance`, `memory_confidence`).
* The long-term and permanent namespace sets do NOT overlap — they are
  distinct storage tiers with different retention policies.
* A "permanent" namespace produces a retention policy with the
  `permanent` mode (no TTL eviction).
* `is_memory_expired` correctly classifies expired and unexpired
  entries based on `expires_at`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.agents.memory.contracts import (
    GovernedMemoryWriteResult,
)
from src.agents.memory.governance import (
    LONG_TERM_MEMORY_NAMESPACES,
    MEMORY_CONFIDENCE_KEY,
    MEMORY_GOVERNANCE_KEY,
    MEMORY_PROVENANCE_KEY,
    MEMORY_RETENTION_KEY,
    PERMANENT_MEMORY_NAMESPACES,
    is_memory_expired,
    prepare_memory_write,
    resolve_memory_expiry,
)


def test_namespace_tiers_do_not_overlap():
    """Long-term and permanent must be disjoint sets — otherwise a
    namespace would belong to two retention tiers at once and the
    expiry policy would be ambiguous."""
    overlap = set(LONG_TERM_MEMORY_NAMESPACES) & set(PERMANENT_MEMORY_NAMESPACES)
    assert overlap == set(), f"namespace tiers overlap: {overlap}"


def test_prepare_memory_write_normalises_metadata():
    result = prepare_memory_write(
        namespace="conversation_summary",
        content="user said hello",
        agent_name="alpha",
        metadata={"source": "chat"},
    )
    assert isinstance(result, GovernedMemoryWriteResult)
    assert result.namespace == "conversation_summary"
    # The four canonical keys must be present on the normalised metadata.
    for key in (
        MEMORY_PROVENANCE_KEY,
        MEMORY_RETENTION_KEY,
        MEMORY_GOVERNANCE_KEY,
        MEMORY_CONFIDENCE_KEY,
    ):
        assert key in result.metadata, f"missing key {key}"


def test_permanent_namespace_uses_permanent_retention():
    result = prepare_memory_write(
        namespace="skill_evolution",
        content="learned a new skill",
    )
    assert result.retention.mode == "permanent"
    # A permanent entry has no expires_at.
    assert result.retention.expires_at is None


def test_is_memory_expired_classifies_past_and_future_expiry():
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    future = (datetime.now(UTC) + timedelta(days=30)).isoformat().replace("+00:00", "Z")

    assert is_memory_expired({"expires_at": past}) is True
    assert is_memory_expired({"expires_at": future}) is False
    # No expires_at => treated as non-expired.
    assert is_memory_expired({}) is False


def test_resolve_memory_expiry_returns_none_when_missing():
    assert resolve_memory_expiry({}) is None
    # Malformed timestamps must not crash the resolver.
    assert resolve_memory_expiry({"expires_at": "not-a-date"}) is None


def test_provenance_records_agent_name():
    result = prepare_memory_write(
        namespace="conversation_summary",
        content="...",
        agent_name="lead",
    )
    assert result.provenance.agent_name == "lead"
