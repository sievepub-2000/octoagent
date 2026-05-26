export interface RuntimeModelCapability {
  name: string;
  display_name?: string | null;
  supports_thinking?: boolean;
  supports_reasoning_effort?: boolean;
  fallback_models: string[];
  max_context_tokens?: number | null;
  effective_fallback_models: string[];
  embedded_backup_available: boolean;
  degraded_mode_supported: boolean;
}

export interface RuntimeAgentLimits {
  max_concurrent_subagents: number;
  max_active_subagents_per_thread: number;
  max_total_subagents_per_thread: number;
  max_total_subagent_jobs: number;
  max_events_per_subagent: number;
  max_ai_messages_per_subagent: number;
  terminal_job_retention_seconds: number;
  memory_guard_enabled: boolean;
  min_available_memory_gb: number;
  oom_critical_available_memory_gb: number;
  estimated_memory_per_subagent_gb: number;
  recommended_max_parallel_branches: number;
  recommended_max_agents_per_workflow: number;
}

export interface RuntimeStatus {
  active_subagents: number;
  retained_jobs?: number;
  available_memory_gb?: number | null;
  memory_guard_state: "ok" | "tight" | "disabled" | "unknown";
}

export interface RuntimeCapabilities {
  default_model?: string | null;
  embedded_backup_model?: string | null;
  embedded_backup_enabled: boolean;
  models: RuntimeModelCapability[];
  agent_limits: RuntimeAgentLimits;
  runtime_status: RuntimeStatus;
}

export interface SystemGuardSnapshot {
  id?: string;
  session_id?: string;
  namespace?: string;
  phase?: string;
  created_at?: string;
  content?: string;
  metadata?: Record<string, unknown>;
  state?: Record<string, unknown>;
}

export interface SystemGuardRetention {
  namespace?: string;
  snapshot_count?: number;
  retention_limit?: number;
}

export interface SystemGuardStatus {
  latest_snapshot?: SystemGuardSnapshot | null;
  recent_snapshots: SystemGuardSnapshot[];
  retention: SystemGuardRetention;
}

export interface SystemGuardRepairRequest {
  advisory_only?: boolean;
}

export interface SystemGuardRepairResponse {
  ok: boolean;
  issues: Array<Record<string, unknown>>;
  repair_report: Record<string, unknown>;
  persisted?: Record<string, unknown> | null;
  session_id?: string | null;
}

export interface SystemGuardExportResponse {
  namespace: string;
  generated_at: string;
  latest_snapshot?: SystemGuardSnapshot | null;
  recent_snapshots: SystemGuardSnapshot[];
  retention: SystemGuardRetention;
  signed: boolean;
  signature_algorithm: string;
  signature: string;
}

export interface RuntimeLongRunningAlert {
  code: string;
  severity: "info" | "warning" | "critical" | string;
  message: string;
  value?: unknown;
  threshold?: unknown;
}

export interface RuntimeLongRunningHealth {
  snapshot: {
    memory?: {
      available_gb?: number | null;
    };
    disk?: {
      path?: string;
      total_gb?: number;
      used_gb?: number;
      free_gb?: number;
      used_percent?: number;
    };
    processes?: {
      host_process_count?: number | null;
    };
    worker_isolation?: {
      total_active?: number;
      total_queued?: number;
      total_completed?: number;
      pools?: Record<string, {
        limit: number;
        active: number;
        queued: number;
        completed: number;
        rejected: number;
        avg_wait_ms: number;
      }>;
    };
    langgraph_contract?: {
      thread_count?: number;
      task_count?: number;
      checkpoint_count?: number;
      active_runs?: number;
      failed_runs?: number;
      audit_event_count?: number;
      updated_at?: string;
    };
    event_loop?: {
      latency_ms?: number | null;
    };
    alerts?: RuntimeLongRunningAlert[];
  };
}

export interface RuntimeMaintenanceStatus {
  running: boolean;
  interval_seconds: number;
  max_checkpoints_per_thread: number;
  max_runs_per_thread: number;
  last_run?: Record<string, unknown> | null;
}

export interface RuntimeRunRecordsResponse {
  records: Array<Record<string, unknown>>;
  summary: Record<string, unknown>;
}
