export interface SystemExecutionCapability {
  enabled: boolean;
  engine: "none" | "sandbox_exec" | "desktop_agent" | "hybrid";
  supports_desktop_control: boolean;
  supports_window_introspection: boolean;
  supports_file_open_handoffs: boolean;
  supports_browser_handoff: boolean;
  supports_permission_policies: boolean;
  note: string;
}

export interface SystemExecutionPermissionRule {
  rule_id: string;
  scope: "shell" | "filesystem" | "browser" | "desktop" | "runtime";
  effect: "allow" | "ask" | "deny";
  match_prefixes: string[];
  match_values: string[];
  note?: string | null;
}

export interface SystemExecutionPermissionPolicy {
  policy_id: string;
  title: string;
  default_effect: "allow" | "ask" | "deny";
  rules: SystemExecutionPermissionRule[];
}

export interface SystemExecutionConfig {
  enabled: boolean;
  engine: "none" | "sandbox_exec" | "desktop_agent" | "hybrid";
  supports_desktop_control: boolean;
  supports_window_introspection: boolean;
  supports_file_open_handoffs: boolean;
  system_cli_enabled: boolean;
  permission_policy: SystemExecutionPermissionPolicy;
  note: string;
}

export interface SystemExecutionAction {
  kind:
    | "inspect_screen"
    | "focus_window"
    | "launch_app"
    | "open_file"
    | "run_command"
    | "click"
    | "type"
    | "hotkey"
    | "scroll"
    | "wait_for"
    | "verify_state";
  target?: string | null;
  value?: string | null;
  metadata: Record<string, string>;
}

export interface SystemExecutionStep {
  id: string;
  title: string;
  description: string;
  kind: "inspect" | "focus" | "open" | "act" | "verify" | "handoff";
  requires_approval: boolean;
  actions: SystemExecutionAction[];
}

export interface SystemExecutionPlan {
  engine: "none" | "sandbox_exec" | "desktop_agent" | "hybrid";
  status: "unavailable" | "planned" | "ready" | "running" | "blocked";
  target: string;
  steps: SystemExecutionStep[];
  missing_capabilities: string[];
  notes: string[];
  permission_policy?: SystemExecutionPermissionPolicy | null;
  blocked_reasons: string[];
}

export interface SystemExecutionPlanRequest {
  goal: string;
  target?: "desktop" | "browser" | "filesystem" | "hybrid" | "workspace_cli" | "system_cli";
  require_approval?: boolean;
  allowed_apps?: string[];
  requested_commands?: string[];
  requested_paths?: string[];
  expected_outcome?: string;
}

export interface SystemExecutionCliRequest {
  command: string;
  note?: string;
  require_approval?: boolean;
  actor?: string;
  role?: string;
  task_id?: string;
  task_name?: string;
}

export interface SystemExecutionCliResponse {
  session: SystemExecutionSession;
  result: SystemExecutionStepExecutionResult;
}

export interface SystemExecutionSession {
  session_id: string;
  status: "unavailable" | "planned" | "ready" | "running" | "blocked";
  engine: "none" | "sandbox_exec" | "desktop_agent" | "hybrid";
  target: string;
  dry_run: boolean;
  plan: SystemExecutionPlan;
  updated_at?: string | null;
  related_task_id?: string | null;
  related_task_name?: string | null;
  allowed_apps: string[];
  requested_paths: string[];
  requested_commands: string[];
  opened_targets: string[];
  launched_apps: string[];
  executed_commands: string[];
  last_command?: string | null;
  last_exit_code?: number | null;
  last_output?: string | null;
  last_blocked_reason?: string | null;
  pending_step_ids: string[];
  recovery_available: boolean;
  completed_step_ids: string[];
}

export interface SystemExecutionSessionListResponse {
  sessions: SystemExecutionSession[];
}

export interface SystemExecutionSessionUpdateRequest {
  status: "ready" | "running" | "blocked";
  detail?: string;
}

export interface SystemExecutionSessionRecoveryRequest {
  note?: string;
}

export interface SystemExecutionStepExecutionRequest {
  note?: string;
}

export interface SystemExecutionStepExecutionResult {
  session_id: string;
  step_id: string;
  status: "simulated" | "blocked" | "completed";
  detail: string;
  remaining_steps: number;
  last_command?: string | null;
  last_exit_code?: number | null;
  last_output?: string | null;
  recovery_available: boolean;
}

export interface SystemExecutionDesktopSnapshot {
  session_id: string;
  active_app?: string | null;
  active_window?: string | null;
  focused_target?: string | null;
  screen_summary: string;
  cursor_hint?: string | null;
  timestamp: string;
}

export interface SystemExecutionAuditEntry {
  session_id: string;
  step_id: string;
  action_kind:
    | "inspect_screen"
    | "focus_window"
    | "launch_app"
    | "open_file"
    | "run_command"
    | "click"
    | "type"
    | "hotkey"
    | "scroll"
    | "wait_for"
    | "verify_state";
  status: "planned" | "skipped" | "blocked" | "simulated" | "completed";
  detail: string;
  timestamp: string;
}

export interface RuntimeDoctorCheck {
  id: string;
  title: string;
  status: "ok" | "warn" | "fail" | string;
  detail: string;
  recommendation?: string | null;
}

export interface RuntimeDoctorResponse {
  overall_status: "ok" | "warn" | "fail" | string;
  checks: RuntimeDoctorCheck[];
}
