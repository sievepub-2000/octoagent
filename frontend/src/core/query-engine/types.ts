export type QueryEngineCapability = {
  enabled: boolean;
  supports_workspace_sessions: boolean;
  supports_prompt_section_assembly: boolean;
  supports_handoff_ready_sessions: boolean;
  supports_compaction_planning: boolean;
  supports_previous_session_summary: boolean;
  supports_runtime_events: boolean;
  supports_context_snapshots: boolean;
  supports_tool_registry: boolean;
  supports_mcp_server_summary: boolean;
  supports_task_analysis: boolean;
  supports_turn_execution: boolean;
  supports_memory_optimization: boolean;
  supports_client_operation_protocol: boolean;
  supports_session_governance: boolean;
  supports_goal_drift_detection: boolean;
  note: string;
};

export type QueryClientCommand = {
  operation_id: string;
  source: "client" | "server";
  intent:
    | "conversation"
    | "repo_read"
    | "browser"
    | "workspace_cli"
    | "system_cli"
    | "filesystem"
    | "desktop"
    | "research";
  execution_target:
    | "repo_read"
    | "browser_runtime"
    | "system_execution"
    | "research_runtime";
  command_text?: string | null;
  cli_scope?: "workspace" | "system" | null;
  requested_url?: string | null;
  requested_path?: string | null;
  requested_app?: string | null;
  notes: string[];
};

export type QueryGoalDriftReport = {
  status: "aligned" | "watch" | "drifting";
  score: number;
  reason: string;
  suggested_focus?: string | null;
};

export type QuerySessionGovernance = {
  continuation_mode: "fresh" | "continued" | "resumed";
  continuity_summary: string;
  context_pressure: "low" | "medium" | "high";
  recommended_memory_action: "continue" | "refresh" | "compact";
  goal_drift: QueryGoalDriftReport;
  active_operation?: QueryClientCommand | null;
};

export type PromptSection = {
  section_id: string;
  title: string;
  content: string;
  cache_behavior: "stable" | "dynamic";
};

export type QueryTurn = {
  turn_id: string;
  status: "planned" | "running" | "completed" | "failed";
  user_message: string;
  assistant_summary?: string | null;
  operation_id?: string | null;
  tool_call_count: number;
  execution_target?: string | null;
  execution_status: "none" | "planned" | "completed" | "blocked" | "simulated";
  runtime_session_id?: string | null;
  runtime_step_id?: string | null;
  memory_action: "none" | "refreshed" | "compacted";
  created_at: string;
};

export type QuerySessionSummary = {
  summary_id: string;
  session_id: string;
  kind: "compaction" | "previous_session";
  title: string;
  content: string;
  open_items: string[];
  created_at: string;
};

export type QueryRuntimeEvent = {
  event_id: string;
  session_id: string;
  turn_id?: string | null;
  kind:
    | "session_created"
    | "context_snapshot_built"
    | "tool_registry_built"
    | "task_analyzed"
    | "turn_recorded"
    | "turn_executed"
    | "memory_optimized"
    | "session_compacted"
    | "summary_promoted"
    | "client_command_planned"
    | "goal_drift_detected"
    | "continuation_applied";
  detail: string;
  created_at: string;
};

export type QueryOperationPlanRequest = {
  user_message: string;
  current_goal?: string;
  continuation_source?: string;
  permission_mode?: "workspace" | "system" | "yolo";
  archived_turn_count?: number;
};

export type QueryOperationPlanResponse = {
  normalized_message: string;
  command: QueryClientCommand;
  governance: QuerySessionGovernance;
};

export type QueryTurnRecordRequest = {
  user_message: string;
  assistant_summary?: string | null;
  tool_call_count?: number;
  status?: "planned" | "running" | "completed" | "failed";
};

export type QuerySessionCompactRequest = {
  retain_turns?: number;
  title?: string;
};

export type QuerySessionRefreshRequest = {
  reason?: string;
};

export type QueryTurnExecutionRequest = {
  user_message: string;
  allow_side_effects?: boolean;
  auto_compact?: boolean;
  force_profile_refresh?: boolean;
  client_command?: QueryClientCommand;
};

export type QueryContextSnapshot = {
  snapshot_id: string;
  repo_root: string;
  workspace_mode: string;
  active_goal: string;
  top_docs: string[];
  selected_runtime_profiles: string[];
  deployment_interfaces: string[];
  compiled_graph_id?: string | null;
  card_count: number;
  checkpoint_count: number;
  agent_count: number;
};

export type QueryToolDescriptor = {
  tool_id: string;
  title: string;
  source: "builtin" | "mcp";
  kind: "read" | "write" | "exec" | "browser" | "system" | "research" | "coordination" | "integration";
  enabled: boolean;
  requires_approval: boolean;
  note: string;
};

export type QueryMcpServerSummary = {
  server_id: string;
  transport: "stdio" | "sse" | "http";
  enabled: boolean;
  description: string;
  auth_mode: "none" | "oauth";
};

export type QueryTaskAnalysis = {
  analysis_id: string;
  summary: string;
  session_mode: "normal" | "coordinator" | "auto";
  coordination_strategy: "solo" | "coordinator_workers" | "manager_review";
  permission_mode: "workspace" | "system" | "yolo";
  execution_flow: string[];
  plan_items: string[];
  open_questions: string[];
  suggested_runtime_targets: string[];
  primary_risk_labels: string[];
  memory_sources: string[];
  self_review_checklist: string[];
  review_required: boolean;
};

export type QueryMemoryLayer = {
  layer_id: string;
  scope: "session" | "workspace" | "project";
  weight: number;
  summary: string;
  source_refs: string[];
  updated_at?: string | null;
};

export type QueryMemoryProfile = {
  archived_turn_count: number;
  compaction_count: number;
  active_layers: number;
  dominant_scope: "session" | "workspace" | "project" | "mixed";
  weighted_signal_score: number;
  recall_summary: string;
  context_pressure: "low" | "medium" | "high";
  recommended_action: "continue" | "refresh" | "compact";
};

export type QuerySession = {
  session_id: string;
  task_id: string;
  agent_id: string;
  status: "planned" | "ready" | "running" | "paused" | "completed" | "failed";
  current_goal: string;
  prompt_stack_profile_id: string;
  prompt_sections: PromptSection[];
  assembled_system_prompt: string;
  context_snapshot?: QueryContextSnapshot | null;
  available_tools: QueryToolDescriptor[];
  mcp_servers: QueryMcpServerSummary[];
  task_analysis?: QueryTaskAnalysis | null;
  memory_layers: QueryMemoryLayer[];
  memory_profile: QueryMemoryProfile;
  governance: QuerySessionGovernance;
  turns: QueryTurn[];
  summaries: QuerySessionSummary[];
  runtime_events: QueryRuntimeEvent[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};
