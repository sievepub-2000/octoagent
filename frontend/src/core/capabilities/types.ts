export type CapabilityCategory = "skills" | "agents" | "instructions" | "hooks" | "mcp";

export type CapabilityInventory = {
  source_root: string;
  target_root: string;
  source: Record<CapabilityCategory, string[]>;
  installed: Record<CapabilityCategory, string[]>;
  matched: Record<CapabilityCategory, string[]>;
};

export type CapabilityMigrationResult = {
  category: CapabilityCategory;
  name: string;
  status: "installed" | "updated" | "skipped" | "error";
  message: string;
};

export type CapabilityMigrationCategorySummary = {
  category: CapabilityCategory;
  source_total: number;
  installed_before: number;
  installed_after: number;
  matched_before: number;
  matched_after: number;
  pending_before: number;
  pending_after: number;
  installed_delta: number;
  matched_delta: number;
  installed_count: number;
  updated_count: number;
  skipped_count: number;
  error_count: number;
};

export type CapabilityMigrationSummary = {
  total_results: number;
  changed_count: number;
  success_count: number;
  error_count: number;
  pending_after: number;
  matched_delta: number;
  categories: Record<CapabilityCategory, CapabilityMigrationCategorySummary>;
};

export type CapabilityMigrationResponse = {
  success: boolean;
  results: CapabilityMigrationResult[];
  previous_inventory: CapabilityInventory;
  inventory: CapabilityInventory;
  summary: CapabilityMigrationSummary;
};

export type CapabilityHookRuntimeState = {
  total_hooks: number;
  enabled_hooks: number;
  total_webhooks: number;
  enabled_webhooks: number;
};

export type CapabilityCompatTrustLevel = "untrusted" | "trusted";

export type CapabilityCompatRuntimeState = {
  enabled: boolean;
  source_root: string | null;
  trust_level: CapabilityCompatTrustLevel;
  configured_items: number;
};

export type CapabilityRuntimeState = {
  source_root: string;
  target_root: string;
  cache_state: "warm" | "cold";
  listeners_registered: boolean;
  last_inventory_built_at: string | null;
  last_migration_at: string | null;
  total_source_items: number;
  total_installed_items: number;
  total_matched_items: number;
  hook_runtime: CapabilityHookRuntimeState;
  agent_skills_compat: CapabilityCompatRuntimeState;
};

export type CapabilityAuditEvent = {
  event: string;
  created_at: string;
  details: Record<string, unknown>;
};

export type CapabilityAuditState = {
  event_count: number;
  recent_events: CapabilityAuditEvent[];
  last_migration_summary: CapabilityMigrationSummary | null;
  last_migration_at: string | null;
};

export type UnifiedCapabilityKind =
  | "skill"
  | "plugin"
  | "mcp_server"
  | "channel"
  | "hook"
  | "command"
  | "agent_persona"
  | "reference";

export type CapabilityRegistryItem = {
  capability_id: string;
  kind: UnifiedCapabilityKind;
  name: string;
  display_name: string;
  description: string;
  provider: string;
  source: string;
  installed: boolean;
  enabled: boolean;
  version: string | null;
  provides: string[];
  requires: string[];
  configurable: boolean;
  configured_enabled: boolean | null;
  activation_blockers: string[];
  metadata: Record<string, unknown>;
};

export type CapabilityRegistrySummary = {
  total_items: number;
  enabled_items: number;
  installed_items: number;
  by_kind: Partial<Record<UnifiedCapabilityKind, number>>;
  enabled_by_kind: Partial<Record<UnifiedCapabilityKind, number>>;
  installed_by_kind: Partial<Record<UnifiedCapabilityKind, number>>;
};

export type CapabilityRegistrySnapshot = {
  generated_at: string;
  items: CapabilityRegistryItem[];
  summary: CapabilityRegistrySummary;
};

export type CapabilityCompatConflict = {
  capability_id: string;
  kind: string;
  name: string;
  provider: string;
  source: string;
  reason: string;
};

export type CapabilityCompatPreviewItem = {
  capability_id: string;
  kind: UnifiedCapabilityKind;
  name: string;
  display_name: string;
  description: string;
  source: string;
  configured_enabled: boolean;
  projected_enabled: boolean;
  trusted: boolean;
  toggleable: boolean;
  activation_blockers: string[];
  conflicts: CapabilityCompatConflict[];
  metadata: Record<string, unknown>;
};

export type CapabilityCompatPreview = {
  enabled: boolean;
  source_root: string | null;
  trust_level: CapabilityCompatTrustLevel;
  total_items: number;
  conflict_count: number;
  blocked_count: number;
  configurable_count: number;
  items: CapabilityCompatPreviewItem[];
};

export type CapabilityPolicyDecision = "inherit" | "allow" | "deny" | "audit_only";

export type CapabilityOperatorPolicy = {
  capability_id: string;
  decision: CapabilityPolicyDecision;
  reason: string;
  updated_by: string;
  updated_at: string;
};

export type CapabilityPolicyAuditEvent = {
  event: string;
  capability_id: string;
  decision: CapabilityPolicyDecision;
  reason: string;
  operator: string;
  created_at: string;
};

export type CapabilityPolicyState = {
  policy_path: string;
  policies: CapabilityOperatorPolicy[];
  audit_events: CapabilityPolicyAuditEvent[];
  summary: {
    policy_count?: number;
    audit_event_count?: number;
    [key: string]: unknown;
  };
};

export type CapabilityPolicyExport = {
  version: string;
  policy_path: string;
  generated_at: string;
  state: Record<string, unknown>;
  signature_algorithm: string;
  signature: string;
};
