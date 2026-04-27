export type BrowserProviderProfile = {
  provider_id: string;
  display_name: string;
  launch_mode: "cli" | "service" | "remote";
  default_session_type: "ephemeral" | "persistent";
  supports_accessibility_snapshot: boolean;
  supports_batch_commands: boolean;
  supports_streaming: boolean;
  recommended_for_default_use: boolean;
};

export type BrowserActionContract = {
  action_id: string;
  kind: "open" | "snapshot" | "click" | "fill" | "eval" | "screenshot" | "wait";
  target?: string | null;
  value?: string | null;
  requires_approval: boolean;
};

export type BrowserRuntimeCapability = {
  enabled: boolean;
  default_provider: "agent_browser" | "none";
  supports_cloud_sandbox: boolean;
  supports_authenticated_sessions: boolean;
  supports_high_privilege_mode: boolean;
  supports_policy_profiles: boolean;
  note: string;
};

export type BrowserSessionRequest = {
  target: string;
  allowed_domains?: string[];
  provider?: string;
  requires_approval?: boolean;
  session_type?: "ephemeral" | "persistent";
  actions?: BrowserActionContract[];
  policy_label?: "safe_read" | "approval_required" | "high_privilege";
};

export type BrowserSessionEvent = {
  event_id: string;
  session_id: string;
  kind: "created" | "started" | "completed" | "failed" | "note";
  detail: string;
  created_at: string;
};

export type BrowserSessionUpdateRequest = {
  status: "running" | "completed" | "failed";
  detail?: string;
};

export type BrowserSessionRecoveryRequest = {
  note?: string;
};

export type BrowserActionExecutionRequest = {
  note?: string;
};

export type BrowserActionExecutionResult = {
  session_id: string;
  action_id: string;
  status: "simulated" | "blocked" | "completed";
  detail: string;
  remaining_actions: number;
  current_url?: string | null;
  page_title?: string | null;
  snapshot_summary?: string | null;
  available_target_count: number;
  available_input_count: number;
  recovery_available: boolean;
};

export type BrowserExecutionSession = {
  session_id: string;
  provider: string;
  target: string;
  status: "planned" | "running" | "completed" | "failed";
  allowed_domains: string[];
  requires_approval: boolean;
  planned_actions: BrowserActionContract[];
  session_type: "ephemeral" | "persistent";
  policy_label: "safe_read" | "approval_required" | "high_privilege";
  created_at?: string | null;
  updated_at?: string | null;
  current_url?: string | null;
  page_title?: string | null;
  available_targets: string[];
  available_inputs: string[];
  form_state: Record<string, string>;
  last_action_id?: string | null;
  last_action_detail?: string | null;
  last_action_status?: "simulated" | "blocked" | "completed" | null;
  latest_snapshot_summary?: string | null;
  last_fetch_status_code?: number | null;
  last_failure_detail?: string | null;
  pending_action_ids: string[];
  recovery_available: boolean;
  executed_action_ids: string[];
  events: BrowserSessionEvent[];
};
