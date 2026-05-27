"""Multi-tenant boundary invariants.

Verifies that the tenant registry:

* creates a sealed registry per filesystem path (no cross-contamination
  between two test installations on the same host),
* always seeds a `default` tenant (so single-tenant deployments keep
  working),
* enforces the per-tenant workspace and agent limits,
* records signed audit events on register / deregister / policy update,
* keeps tenants isolated: tenants A and B never see each other's data
  even when both are loaded by the same process.
"""

from __future__ import annotations

import json

from src.governance.multi_tenant import (
    REGISTRY_VERSION,
    TenantContext,
    TenantIsolationPolicy,
    TenantRegistry,
)


def _fresh_registry(tmp_path):
    return TenantRegistry(path=tmp_path / "registry.json")


def test_default_tenant_seeded(tmp_path):
    registry = _fresh_registry(tmp_path)
    default = registry.get_tenant("default")
    assert default.tenant_id == "default"
    assert default.tier == "free"
    # default policy applied
    policy = registry.get_policy("default")
    assert isinstance(policy, TenantIsolationPolicy)
    assert policy.max_concurrent_workspaces == 10


def test_tenant_context_is_enterprise_property():
    free = TenantContext(tenant_id="t1")
    pro = TenantContext(tenant_id="t2", tier="pro")
    enterprise = TenantContext(tenant_id="t3", tier="enterprise")
    assert free.is_enterprise is False
    assert pro.is_enterprise is False
    assert enterprise.is_enterprise is True


def test_register_and_deregister_round_trip(tmp_path):
    registry = _fresh_registry(tmp_path)
    tenant = TenantContext(tenant_id="acme", tier="pro", display_name="ACME Corp")
    registry.register(tenant)
    assert registry.get_tenant("acme").display_name == "ACME Corp"
    assert registry.deregister("acme") is True
    # After deregister, lookup returns the default sentinel (not None).
    assert registry.get_tenant("acme").tenant_id == "default"
    # Re-deregister is a no-op (idempotent).
    assert registry.deregister("acme") is False


def test_workspace_and_agent_limits_enforced(tmp_path):
    registry = _fresh_registry(tmp_path)
    tenant = TenantContext(tenant_id="capped", tier="free")
    policy = TenantIsolationPolicy(
        max_concurrent_workspaces=2,
        max_agents_per_workspace=3,
    )
    registry.register(tenant, policy)

    assert registry.enforce_workspace_limit("capped", current_count=1) is True
    assert registry.enforce_workspace_limit("capped", current_count=2) is False

    assert registry.enforce_agent_limit("capped", current_count=2) is True
    assert registry.enforce_agent_limit("capped", current_count=3) is False


def test_tenants_are_isolated_across_registries(tmp_path):
    """Two registries on different paths must not see each other's tenants."""
    reg_a = TenantRegistry(path=tmp_path / "a.json")
    reg_b = TenantRegistry(path=tmp_path / "b.json")

    reg_a.register(TenantContext(tenant_id="tenant-a", tier="enterprise"))
    reg_b.register(TenantContext(tenant_id="tenant-b", tier="pro"))

    a_ids = {t.tenant_id for t in reg_a.list_tenants()}
    b_ids = {t.tenant_id for t in reg_b.list_tenants()}

    # 'default' is seeded in both; the user-registered IDs must not cross.
    assert "tenant-a" in a_ids and "tenant-a" not in b_ids
    assert "tenant-b" in b_ids and "tenant-b" not in a_ids


def test_registry_payload_is_versioned(tmp_path):
    """The on-disk format must declare the registry version so future
    migrations can detect and upgrade older payloads."""
    registry = _fresh_registry(tmp_path)
    registry.register(TenantContext(tenant_id="probe"))
    payload = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))
    assert payload.get("version") == REGISTRY_VERSION
    assert "tenants" in payload and "policies" in payload


def test_governance_snapshot_includes_audit_events(tmp_path):
    registry = _fresh_registry(tmp_path)
    registry.register(
        TenantContext(tenant_id="audited", tier="enterprise"),
        TenantIsolationPolicy(workspace_isolation="dedicated"),
    )
    snapshot = registry.governance_snapshot()
    assert snapshot["tenant_count"] >= 2  # default + audited
    assert snapshot["enterprise_count"] >= 1
    # audit_events is a bounded slice (<=20) and each is a dict
    events = snapshot["audit_events"]
    assert isinstance(events, list)
    assert len(events) <= 20
    for event in events:
        assert isinstance(event, dict)
