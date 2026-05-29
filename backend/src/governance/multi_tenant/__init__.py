"""Multi-tenant isolation contracts and workspace-level security boundaries.

P3 module — provides tenant-scoped access control so that workspaces,
agents, and data belong to isolated tenants.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from src.governance.operator import signed_audit_event
from src.runtime.config.paths import get_paths
from src.utils.json_atomic import write_json_atomic

logger = logging.getLogger(__name__)

REGISTRY_VERSION = "multi-tenant-registry-v1"


@dataclass
class TenantContext:
    """Identifies the current tenant for scoped operations."""

    tenant_id: str
    display_name: str = ""
    tier: Literal["free", "pro", "enterprise"] = "free"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_enterprise(self) -> bool:
        return self.tier == "enterprise"


@dataclass
class TenantIsolationPolicy:
    """Defines how resources are isolated between tenants."""

    workspace_isolation: Literal["shared", "namespace", "dedicated"] = "namespace"
    data_isolation: Literal["row_level", "schema_level", "database_level"] = "row_level"
    skill_sharing: Literal["none", "read_only", "full"] = "read_only"
    max_concurrent_workspaces: int = 10
    max_agents_per_workspace: int = 20


def _registry_path():
    return get_paths().runtime_root / "multi_tenant_registry.json"


class TenantRegistry:
    """Registry of active tenants and their isolation policies."""

    def __init__(self, path=None) -> None:
        self._path = path or _registry_path()
        self._tenants: dict[str, TenantContext] = {}
        self._policies: dict[str, TenantIsolationPolicy] = {}
        self._audit_events: list[dict[str, Any]] = []
        self._default = TenantContext(tenant_id="default", display_name="Default Tenant")
        self._load()
        if "default" not in self._tenants:
            self._tenants["default"] = self._default
            self._policies.setdefault("default", TenantIsolationPolicy())
            self._save()

    @property
    def path(self) -> str:
        return str(self._path)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            import json

            payload = json.loads(self._path.read_text(encoding="utf-8"))
            tenants = payload.get("tenants", {})
            policies = payload.get("policies", {})
            if isinstance(tenants, dict):
                self._tenants = {str(tenant_id): TenantContext(**tenant_payload) for tenant_id, tenant_payload in tenants.items() if isinstance(tenant_payload, dict)}
            if isinstance(policies, dict):
                self._policies = {str(tenant_id): TenantIsolationPolicy(**policy_payload) for tenant_id, policy_payload in policies.items() if isinstance(policy_payload, dict)}
            audit_events = payload.get("audit_events", [])
            if isinstance(audit_events, list):
                self._audit_events = [event for event in audit_events if isinstance(event, dict)][:200]
        except Exception as exc:
            logger.warning("Failed to load multi-tenant registry from %s: %s", self._path, exc)

    def _save(self) -> None:
        write_json_atomic(
            self._path,
            {
                "version": REGISTRY_VERSION,
                "updated_at": time.time(),
                "tenants": {tenant_id: asdict(tenant) for tenant_id, tenant in self._tenants.items()},
                "policies": {tenant_id: asdict(policy) for tenant_id, policy in self._policies.items()},
                "audit_events": self._audit_events[:200],
            },
        )

    def _audit(self, event: str, tenant_id: str, **details: Any) -> None:
        self._audit_events.insert(
            0,
            signed_audit_event(event, tenant_id=tenant_id, timestamp=time.time(), **details),
        )
        del self._audit_events[200:]
        self._save()

    def register(self, tenant: TenantContext, policy: TenantIsolationPolicy | None = None) -> None:
        self._tenants[tenant.tenant_id] = tenant
        self._policies[tenant.tenant_id] = policy or TenantIsolationPolicy()
        self._audit("tenant.registered", tenant.tenant_id, tier=tenant.tier)

    def deregister(self, tenant_id: str) -> bool:
        removed = self._tenants.pop(tenant_id, None)
        self._policies.pop(tenant_id, None)
        if removed is not None:
            self._audit("tenant.deregistered", tenant_id)
            return True
        return False

    def update_policy(self, tenant_id: str, policy: TenantIsolationPolicy) -> TenantIsolationPolicy:
        self._policies[tenant_id] = policy
        self._audit(
            "tenant.policy_updated",
            tenant_id,
            workspace_isolation=policy.workspace_isolation,
            data_isolation=policy.data_isolation,
            skill_sharing=policy.skill_sharing,
        )
        return policy

    def get_tenant(self, tenant_id: str) -> TenantContext:
        return self._tenants.get(tenant_id, self._default)

    def get_policy(self, tenant_id: str) -> TenantIsolationPolicy:
        return self._policies.get(tenant_id, TenantIsolationPolicy())

    def list_tenants(self) -> list[TenantContext]:
        return sorted(self._tenants.values(), key=lambda item: item.tenant_id)

    def enforce_workspace_limit(self, tenant_id: str, current_count: int) -> bool:
        """Return True if the tenant can create another workspace."""
        policy = self.get_policy(tenant_id)
        return current_count < policy.max_concurrent_workspaces

    def enforce_agent_limit(self, tenant_id: str, current_count: int) -> bool:
        """Return True if the tenant can spawn another agent."""
        policy = self.get_policy(tenant_id)
        return current_count < policy.max_agents_per_workspace

    def governance_snapshot(self) -> dict[str, Any]:
        tenants = self.list_tenants()
        policies = {tenant.tenant_id: self.get_policy(tenant.tenant_id) for tenant in tenants}
        return {
            "registry_path": self.path,
            "tenant_count": len(tenants),
            "enterprise_count": sum(1 for tenant in tenants if tenant.is_enterprise),
            "max_concurrent_workspaces": sum(policy.max_concurrent_workspaces for policy in policies.values()),
            "max_agents_per_workspace": sum(policy.max_agents_per_workspace for policy in policies.values()),
            "audit_events": list(self._audit_events[:20]),
        }

    def export_state(self) -> dict[str, Any]:
        return {
            "version": REGISTRY_VERSION,
            "registry_path": self.path,
            "tenants": {tenant_id: asdict(tenant) for tenant_id, tenant in self._tenants.items()},
            "policies": {tenant_id: asdict(policy) for tenant_id, policy in self._policies.items()},
            "audit_events": self._audit_events[:200],
        }


_registry: TenantRegistry | None = None


def get_tenant_registry() -> TenantRegistry:
    global _registry
    if _registry is None:
        _registry = TenantRegistry()
    return _registry
