import { getJSON, postJSON, putJSON } from "@/core/api/http";

import type {
  CapabilityAuditState,
  CapabilityCategory,
  CapabilityCompatPreview,
  CapabilityCompatTrustLevel,
  CapabilityInventory,
  CapabilityMigrationResponse,
  CapabilityPolicyDecision,
  CapabilityPolicyExport,
  CapabilityPolicyState,
  CapabilityRegistryItem,
  CapabilityRegistrySnapshot,
  CapabilityRuntimeState,
} from "./types";

export function loadCapabilityInventory() {
  return getJSON<CapabilityInventory>("/api/capabilities/inventory");
}

export function migrateCapabilities(categories?: CapabilityCategory[]) {
  return postJSON<CapabilityMigrationResponse>("/api/capabilities/migrate", {
    categories,
  });
}

export function loadCapabilityRuntimeState() {
  return getJSON<CapabilityRuntimeState>("/api/capabilities/runtime-state");
}

export function loadCapabilityAuditState() {
  return getJSON<CapabilityAuditState>("/api/capabilities/audit");
}

export function loadCapabilityRegistry() {
  return getJSON<CapabilityRegistrySnapshot>("/api/capabilities/registry");
}

export function updateCapabilityState(capabilityId: string, enabled: boolean) {
  return putJSON<CapabilityRegistryItem>(
    `/api/capabilities/registry/${encodeURIComponent(capabilityId)}`,
    { enabled },
  );
}

export function loadCapabilityCompatPreview() {
  return getJSON<CapabilityCompatPreview>("/api/capabilities/compat/preview");
}

export function updateCapabilityCompatSettings(request: {
  enabled?: boolean;
  trust_level?: CapabilityCompatTrustLevel;
}) {
  return putJSON<CapabilityCompatPreview>("/api/capabilities/compat/settings", request);
}

export function loadCapabilityPolicies() {
  return getJSON<CapabilityPolicyState>("/api/capabilities/policies");
}

export function updateCapabilityPolicy(
  capabilityId: string,
  request: {
    decision: CapabilityPolicyDecision;
    reason?: string;
    operator?: string;
  },
) {
  return putJSON<CapabilityPolicyState>(
    `/api/capabilities/policies/${encodeURIComponent(capabilityId)}`,
    request,
  );
}

export function exportCapabilityPolicies() {
  return getJSON<CapabilityPolicyExport>("/api/capabilities/policies/export");
}

export function importCapabilityPolicies(request: {
  payload: Record<string, unknown>;
  operator?: string;
  reason?: string;
}) {
  return postJSON<CapabilityPolicyState>("/api/capabilities/policies/import", request);
}
