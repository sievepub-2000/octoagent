"""Governance helpers for layered memory provenance, confidence, and retention."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.memory.contracts import (
    GovernedMemoryWriteResult,
    MemoryGovernanceDecision,
    MemoryProvenance,
    MemoryRetentionPolicy,
)
from src.config.memory_config import MemoryConfig, get_memory_config

LONG_TERM_MEMORY_NAMESPACES = ("conversation_summary",)
PERMANENT_MEMORY_NAMESPACES = ("skill_evolution", "system_insight")

MEMORY_PROVENANCE_KEY = "memory_provenance"
MEMORY_CONFIDENCE_KEY = "memory_confidence"
MEMORY_RETENTION_KEY = "memory_retention"
MEMORY_GOVERNANCE_KEY = "memory_governance"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None


def resolve_memory_expiry(metadata: dict[str, Any]) -> datetime | None:
    """Resolve the effective expiry timestamp from normalized memory metadata."""

    retention = metadata.get(MEMORY_RETENTION_KEY)
    if isinstance(retention, dict):
        expires_at = _parse_datetime(str(retention.get("expires_at") or ""))
        if expires_at is not None:
            return expires_at.astimezone(UTC)

    expires_at = _parse_datetime(
        str(metadata.get("expires_at") or metadata.get("expires_on") or "")
    )
    if expires_at is None:
        return None
    return expires_at.astimezone(UTC)


def is_memory_expired(
    metadata: dict[str, Any],
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether a governed memory entry is currently expired."""

    expires_at = resolve_memory_expiry(metadata)
    if expires_at is None:
        return False
    effective_now = (now or _utc_now()).astimezone(UTC)
    return expires_at <= effective_now


def _namespace_default_retention(namespace: str, config: MemoryConfig) -> int | None:
    if namespace in PERMANENT_MEMORY_NAMESPACES:
        return None
    return config.long_term_retention_days


def _explicit_confidence(metadata: dict[str, Any]) -> float | None:
    raw_value = metadata.get("confidence")
    if raw_value is None:
        return None
    try:
        return max(0.0, min(1.0, float(raw_value)))
    except (TypeError, ValueError):
        return None


def _resolved_confidence(namespace: str, metadata: dict[str, Any], config: MemoryConfig) -> float:
    explicit = _explicit_confidence(metadata)
    if explicit is not None:
        return explicit
    if metadata.get("simplemem"):
        return max(config.fact_confidence_threshold, 0.85)
    if namespace in PERMANENT_MEMORY_NAMESPACES:
        return max(config.fact_confidence_threshold, 0.8)
    return max(config.fact_confidence_threshold, 0.75)


def _build_provenance(
    namespace: str,
    metadata: dict[str, Any],
    *,
    agent_name: str | None,
) -> MemoryProvenance:
    existing = metadata.get(MEMORY_PROVENANCE_KEY)
    if isinstance(existing, dict):
        return MemoryProvenance(**existing)

    source = str(metadata.get("source") or namespace)
    source_kind = str(metadata.get("source_kind") or ("simplemem" if metadata.get("simplemem") else "system"))
    pipeline = str(metadata.get("pipeline") or ("simplemem" if metadata.get("simplemem") else "system_rag"))
    source_thread_id = metadata.get("thread_id")
    return MemoryProvenance(
        source=source,
        source_kind=source_kind,
        source_thread_id=str(source_thread_id) if source_thread_id else None,
        pipeline=pipeline,
        agent_name=agent_name or metadata.get("agent_name"),
        recorded_at=_iso_utc(_utc_now()),
    )


def _build_retention_policy(
    namespace: str,
    metadata: dict[str, Any],
    config: MemoryConfig,
) -> MemoryRetentionPolicy:
    existing = metadata.get(MEMORY_RETENTION_KEY)
    if isinstance(existing, dict):
        return MemoryRetentionPolicy(**existing)

    immutable = bool(metadata.get("immutable", namespace in PERMANENT_MEMORY_NAMESPACES and config.permanent_memory_immutable))
    explicit_expires = _parse_datetime(
        str(metadata.get("expires_at") or metadata.get("expires_on") or "")
    )
    if explicit_expires is not None:
        return MemoryRetentionPolicy(
            mode="expires_at",
            namespace=namespace,
            ttl_days=None,
            expires_at=_iso_utc(explicit_expires.astimezone(UTC)),
            immutable=immutable,
            reason="explicit_expiry",
        )

    explicit_days = metadata.get("retention_days")
    ttl_days: int | None = None
    if explicit_days is not None:
        try:
            ttl_days = max(1, int(explicit_days))
        except (TypeError, ValueError):
            ttl_days = None

    if ttl_days is None:
        ttl_days = _namespace_default_retention(namespace, config)

    if ttl_days is None:
        return MemoryRetentionPolicy(
            mode="permanent",
            namespace=namespace,
            ttl_days=None,
            expires_at=None,
            immutable=immutable,
            reason="namespace_default",
        )

    expires_at = _utc_now() + timedelta(days=ttl_days)
    return MemoryRetentionPolicy(
        mode="window",
        namespace=namespace,
        ttl_days=ttl_days,
        expires_at=_iso_utc(expires_at),
        immutable=immutable,
        reason="configured_window",
    )


def _build_governance_decision(
    namespace: str,
    content: str,
    metadata: dict[str, Any],
    config: MemoryConfig,
    confidence: float,
) -> MemoryGovernanceDecision:
    existing = metadata.get(MEMORY_GOVERNANCE_KEY)
    if isinstance(existing, dict):
        return MemoryGovernanceDecision(**existing)

    reason = "accepted"
    allowed = True
    if not content.strip():
        allowed = False
        reason = "empty_content"
    elif _explicit_confidence(metadata) is not None and confidence < config.fact_confidence_threshold:
        if config.write_governance_mode == "enforce":
            allowed = False
            reason = "confidence_below_threshold"
        else:
            reason = "accepted_in_audit_mode"

    return MemoryGovernanceDecision(
        allowed=allowed,
        reason=reason,
        policy_name=f"{namespace}_write_policy",
        namespace=namespace,
        confidence=confidence,
        threshold=config.fact_confidence_threshold,
        mode=config.write_governance_mode,
        evaluated_at=_iso_utc(_utc_now()),
    )


def prepare_memory_write(
    namespace: str,
    content: str,
    *,
    agent_name: str | None = None,
    metadata: dict[str, Any] | None = None,
    config: MemoryConfig | None = None,
) -> GovernedMemoryWriteResult:
    """Evaluate and normalize a memory write before it reaches persistence."""

    effective_config = config or get_memory_config()
    raw_metadata = dict(metadata or {})
    confidence = _resolved_confidence(namespace, raw_metadata, effective_config)
    provenance = _build_provenance(namespace, raw_metadata, agent_name=agent_name)
    retention = _build_retention_policy(namespace, raw_metadata, effective_config)
    decision = _build_governance_decision(
        namespace,
        content,
        raw_metadata,
        effective_config,
        confidence,
    )

    normalized_metadata = dict(raw_metadata)
    normalized_metadata[MEMORY_CONFIDENCE_KEY] = confidence
    normalized_metadata[MEMORY_PROVENANCE_KEY] = asdict(provenance)
    normalized_metadata[MEMORY_RETENTION_KEY] = asdict(retention)
    normalized_metadata[MEMORY_GOVERNANCE_KEY] = asdict(decision)
    normalized_metadata.setdefault("confidence", confidence)
    normalized_metadata.setdefault("immutable", retention.immutable)
    if retention.expires_at:
        normalized_metadata.setdefault("expires_at", retention.expires_at)

    return GovernedMemoryWriteResult(
        entry_id=None,
        namespace=namespace,
        allowed=decision.allowed or not effective_config.write_governance_enabled,
        confidence=confidence,
        provenance=provenance,
        retention=retention,
        governance=decision,
        metadata=normalized_metadata,
    )


def build_memory_governance_summary(config: MemoryConfig | None = None) -> dict[str, Any]:
    """Build a serializable summary of the effective memory write-governance policy."""

    effective_config = config or get_memory_config()
    namespace_policies: dict[str, dict[str, Any]] = {}
    for namespace in (*LONG_TERM_MEMORY_NAMESPACES, *PERMANENT_MEMORY_NAMESPACES):
        policy = _build_retention_policy(namespace, {}, effective_config)
        namespace_policies[namespace] = asdict(policy)
    return {
        "enabled": effective_config.write_governance_enabled,
        "mode": effective_config.write_governance_mode,
        "confidence_threshold": effective_config.fact_confidence_threshold,
        "long_term_retention_days": effective_config.long_term_retention_days,
        "permanent_retention_days": effective_config.permanent_retention_days,
        "immutable_namespaces": [
            namespace
            for namespace in PERMANENT_MEMORY_NAMESPACES
            if effective_config.permanent_memory_immutable
        ],
        "namespace_policies": namespace_policies,
    }


def hydrate_memory_provenance(metadata: dict[str, Any]) -> MemoryProvenance | None:
    payload = metadata.get(MEMORY_PROVENANCE_KEY)
    if not isinstance(payload, dict):
        return None
    return MemoryProvenance(**payload)


def hydrate_memory_retention(metadata: dict[str, Any]) -> MemoryRetentionPolicy | None:
    payload = metadata.get(MEMORY_RETENTION_KEY)
    if not isinstance(payload, dict):
        return None
    return MemoryRetentionPolicy(**payload)


def hydrate_memory_governance(metadata: dict[str, Any]) -> MemoryGovernanceDecision | None:
    payload = metadata.get(MEMORY_GOVERNANCE_KEY)
    if not isinstance(payload, dict):
        return None
    return MemoryGovernanceDecision(**payload)
