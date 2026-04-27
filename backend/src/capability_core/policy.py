"""Auditable operator policy overlay for capability binding contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.operator_governance import signed_audit_event
from src.skills.loader import get_skills_root_path
from src.utils.json_atomic import write_json_atomic

CapabilityPolicyDecision = Literal["inherit", "allow", "deny", "audit_only"]


class CapabilityOperatorPolicy(BaseModel):
    capability_id: str
    tenant_id: str = "default"
    decision: CapabilityPolicyDecision = "inherit"
    reason: str = ""
    updated_by: str = "operator"
    updated_at: str


class CapabilityPolicyAuditEvent(BaseModel):
    event: str
    capability_id: str
    tenant_id: str = "default"
    decision: CapabilityPolicyDecision
    reason: str = ""
    operator: str = "operator"
    created_at: str
    signature_algorithm: str = "sha256"
    signature: str = ""


class CapabilityPolicyState(BaseModel):
    policies: dict[str, CapabilityOperatorPolicy] = Field(default_factory=dict)
    audit_events: list[CapabilityPolicyAuditEvent] = Field(default_factory=list)


def _repo_root() -> Path:
    return get_skills_root_path().parent


def _policy_path() -> Path:
    return _repo_root() / "workspace" / "runtime" / "capability_operator_policies.json"


class CapabilityPolicyService:
    """Persist and apply local operator policy without mutating capability manifests."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _policy_path()
        self._state: CapabilityPolicyState | None = None

    def _load(self) -> CapabilityPolicyState:
        if self._state is not None:
            return self._state
        if not self._path.exists():
            self._state = CapabilityPolicyState()
            return self._state
        payload = self._path.read_text(encoding="utf-8")
        self._state = CapabilityPolicyState.model_validate_json(payload)
        return self._state

    def _save(self) -> None:
        state = self._load()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self._path, state.model_dump(mode="json"))

    @staticmethod
    def _policy_key(capability_id: str, tenant_id: str = "default") -> str:
        tenant = (tenant_id or "default").strip() or "default"
        if tenant == "default":
            return capability_id
        return f"{tenant}:{capability_id}"

    def list_state(self) -> dict[str, object]:
        state = self._load()
        return {
            "policy_path": str(self._path),
            "policies": [
                item.model_dump()
                for item in sorted(state.policies.values(), key=lambda item: (item.tenant_id, item.capability_id))
            ],
            "audit_events": [item.model_dump() for item in state.audit_events[:50]],
            "summary": {
                "policy_count": len(state.policies),
                "audit_event_count": len(state.audit_events),
            },
        }

    def export_state(self) -> dict[str, object]:
        state = self._load()
        payload = {
            "version": "capability-operator-policy-v1",
            "policy_path": str(self._path),
            "generated_at": datetime.now(UTC).isoformat(),
            "state": state.model_dump(mode="json"),
        }
        canonical = json.dumps(payload["state"], ensure_ascii=False, sort_keys=True)
        payload["signature_algorithm"] = "sha256"
        payload["signature"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return payload

    def import_state(
        self,
        payload: dict[str, object],
        *,
        operator: str = "operator",
        reason: str = "imported_policy_state",
    ) -> dict[str, object]:
        state_payload = payload.get("state") if isinstance(payload.get("state"), dict) else payload
        imported = CapabilityPolicyState.model_validate(state_payload)
        now = datetime.now(UTC).isoformat()
        state = self._load()
        state.policies = imported.policies
        state.audit_events = list(imported.audit_events)
        audit = signed_audit_event(
            "capability_policy.imported",
            actor=operator.strip() or "operator",
            capability_id="*",
            decision="inherit",
            reason=reason,
        )
        state.audit_events.insert(
            0,
            CapabilityPolicyAuditEvent(
                event="capability_policy.imported",
                capability_id="*",
                decision="inherit",
                reason=reason,
                operator=operator.strip() or "operator",
                created_at=now,
                signature_algorithm=str(audit.get("signature_algorithm") or "sha256"),
                signature=str(audit.get("signature") or ""),
            ),
        )
        del state.audit_events[100:]
        self._save()
        return self.list_state()

    def get_policy(self, capability_id: str, *, tenant_id: str = "default") -> CapabilityOperatorPolicy | None:
        state = self._load()
        tenant_key = self._policy_key(capability_id, tenant_id)
        return state.policies.get(tenant_key) or state.policies.get(capability_id)

    def policy_payload_for(self, capability_id: str, *, tenant_id: str = "default") -> dict[str, object]:
        policy = self.get_policy(capability_id, tenant_id=tenant_id)
        if policy is None:
            return {
                "capability_id": capability_id,
                "tenant_id": tenant_id or "default",
                "decision": "inherit",
                "reason": "",
                "updated_by": None,
                "updated_at": None,
                "effective_bindable": True,
            }
        payload = policy.model_dump()
        payload["effective_bindable"] = policy.decision != "deny"
        return payload

    def set_policy(
        self,
        capability_id: str,
        decision: CapabilityPolicyDecision,
        *,
        reason: str = "",
        operator: str = "operator",
        tenant_id: str = "default",
    ) -> CapabilityOperatorPolicy:
        now = datetime.now(UTC).isoformat()
        state = self._load()
        policy_key = self._policy_key(capability_id, tenant_id)
        tenant = (tenant_id or "default").strip() or "default"
        if decision == "inherit":
            state.policies.pop(policy_key, None)
        else:
            state.policies[policy_key] = CapabilityOperatorPolicy(
                capability_id=capability_id,
                tenant_id=tenant,
                decision=decision,
                reason=reason.strip(),
                updated_by=operator.strip() or "operator",
                updated_at=now,
            )
        audit = signed_audit_event(
            "capability_policy.updated",
            actor=operator.strip() or "operator",
            capability_id=capability_id,
            tenant_id=tenant,
            decision=decision,
            reason=reason.strip(),
        )
        state.audit_events.insert(
            0,
            CapabilityPolicyAuditEvent(
                event="capability_policy.updated",
                capability_id=capability_id,
                tenant_id=tenant,
                decision=decision,
                reason=reason.strip(),
                operator=operator.strip() or "operator",
                created_at=now,
                signature_algorithm=str(audit.get("signature_algorithm") or "sha256"),
                signature=str(audit.get("signature") or ""),
            ),
        )
        del state.audit_events[100:]
        self._save()
        return state.policies.get(
            policy_key,
            CapabilityOperatorPolicy(
                capability_id=capability_id,
                tenant_id=tenant,
                decision="inherit",
                reason="",
                updated_by=operator.strip() or "operator",
                updated_at=now,
            ),
        )


_capability_policy_service: CapabilityPolicyService | None = None


def get_capability_policy_service() -> CapabilityPolicyService:
    global _capability_policy_service
    if _capability_policy_service is None:
        _capability_policy_service = CapabilityPolicyService()
    return _capability_policy_service
