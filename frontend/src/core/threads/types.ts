import type { Message, Thread } from "@langchain/langgraph-sdk";

import type { Todo } from "../todos";
import type { Workflow, WorkflowEvent } from "../workflows";

export interface ThreadContinuation {
  source_thread_id: string;
  trigger: "continue";
  source_title?: string | null;
  message_count?: number | null;
  workflow_count?: number | null;
  continued_at?: string | null;
}

export interface ContinuationContract {
  version: 2;
  objective: string;
  status?: string;
  current_phase?: string;
  next_action?: string;
  constraints?: string[];
  forbidden_actions?: string[];
  acceptance_criteria?: string[];
  confirmed_decisions?: string[];
  completed_steps?: string[];
  pending_steps?: string[];
  blockers?: string[];
  evidence?: string[];
  artifacts?: string[];
  permission_scope?: string;
  source_thread_id: string;
  source_title?: string;
  source_message_ids?: string[];
}

export interface ThreadRuntimeState {
  primary_model?: string | null;
  active_model?: string | null;
  fallback_chain?: string[] | null;
  fallback_switches?: Array<{
    from_model: string;
    to_model: string;
    reason: string;
  }> | null;
  fallback_ready?: boolean | null;
  embedded_backup_enabled?: boolean | null;
  instruction_profile_id?: string | null;
  instruction_profile_title?: string | null;
  instruction_source?: string | null;
  loaded_instruction_modules?: string[] | null;
  instruction_module_count?: number | null;
  instruction_focus_mode?:
    | "standard"
    | "focused"
    | "resume"
    | "compact"
    | "clarify"
    | null;
  instruction_focus_summary?: string | null;
  continuation_source?: string | null;
  continuation_mode?: "fresh" | "continued" | "resumed" | null;
  workflow_resume_state?: "fresh" | "loaded" | "resumed" | null;
  memory_guard_state?: "ok" | "tight" | "disabled" | "unknown" | null;
  context_guard_state?: "ok" | "coalesced" | "compacted" | "trimmed" | "truncated" | "emergency_trimmed" | null;
  context_pressure?: "low" | "medium" | "high" | null;
  recommended_memory_action?:
    | "continue"
    | "refresh"
    | "compact"
    | "truncate_oversized_messages"
    | null;
  task_state_status?: "active" | "incomplete" | "completed" | string | null;
  recoverable_failure?: Record<string, unknown> | null;
  incomplete_state?: Record<string, unknown> | null;
  goal_drift_status?: "aligned" | "watch" | "drifting" | null;
  client_command_target?: string | null;
  planned_operation_id?: string | null;
  instruction_contract?: Record<string, unknown> | null;
  skill_evolution_hints?: Array<Record<string, unknown>> | null;
  skill_evolution_suggestions?: Array<Record<string, unknown>> | null;
  memory_write?: Record<string, unknown> | null;
  last_run_record?: Record<string, unknown> | null;
  compaction_strategy?: string | null;
  compaction_trigger?: string | null;
  compaction_summary?: string | null;
  compaction_saved_tokens?: number | null;
  context_cycle_id?: string | null;
  context_cycle_started_at?: string | null;
  context_cycle_base_tokens?: number | null;
  context_handoff?: {
    required: boolean;
    source_thread_id: string;
    reason: string;
    pre_tokens?: number;
    post_tokens?: number;
  } | null;
  task_review_required?: boolean | null;
  execution_review_started_at?: string | null;
  execution_review_last_at?: string | null;
  execution_review_last_reasons?: string[] | null;
  execution_review_pending_reasons?: string[] | null;
  execution_review_status?: string | null;
  self_feedback_action?: string | null;
  resource_recovery_action?: string | null;
  memory_followup_action?: string | null;
  capability_control_mode?: string | null;
  pressure_ratio?: number | null;
  final_error?: string | null;
  run_events?: Array<Record<string, unknown>> | null;
  workplans?: Array<Record<string, unknown>> | null;
  active_workplan_id?: string | null;
  updated_at?: string | null;
}

export interface AgentThreadState extends Record<string, unknown> {
  project_id?: string | null;
  title: string;
  messages: Message[];
  artifacts: string[];
  continuation?: ThreadContinuation;
  runtime?: ThreadRuntimeState;
  todos?: Todo[];
  task_state?: Record<string, unknown> | null;
  workflows?: Workflow[];
  workflow_events?: WorkflowEvent[];
  task_workspace_ids?: string[];
  active_task_workspace_id?: string | null;
}

export interface AgentThread extends Thread<AgentThreadState> {}

export interface AgentThreadContext extends Record<string, unknown> {
  project_id?: string;
  thread_id: string;
  model_name: string | undefined;
  thinking_enabled: boolean;
  is_plan_mode: boolean;
  subagent_enabled: boolean;
  reasoning_effort?: "minimal" | "low" | "medium" | "high";
  conversation_language?: string;
  agent_name?: string;
  continue_trigger?: "continue";
  continue_from_thread_id?: string;
  continue_from_title?: string;
  continue_message_count?: number;
  continue_recent_messages?: Array<{ role: string; content: string }>;
  continue_memory_summary?: string;
  continue_todos?: Todo[];
  continue_task_state?: Record<string, unknown> | null;
  continue_contract?: ContinuationContract;
  continue_workflows?: Workflow[];
  continue_cycle_id?: string;
  continue_cycle_started_at?: string;
  continue_cycle_base_tokens?: number;
  client_command?: Record<string, unknown>;
  session_governance?: Record<string, unknown>;
  ml_intern_profile?: "interactive" | "headless";
  ml_intern_source_repo?: string;
  ml_intern_source_commit?: string;
  permission_mode?: "approval" | "directory" | "system";
}
