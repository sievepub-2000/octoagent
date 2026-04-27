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
  context_pressure?: "low" | "medium" | "high" | null;
  recommended_memory_action?: "continue" | "refresh" | "compact" | null;
  goal_drift_status?: "aligned" | "watch" | "drifting" | null;
  client_command_target?: string | null;
  planned_operation_id?: string | null;
  final_error?: string | null;
  updated_at?: string | null;
}

export interface AgentThreadState extends Record<string, unknown> {
  title: string;
  messages: Message[];
  artifacts: string[];
  continuation?: ThreadContinuation;
  runtime?: ThreadRuntimeState;
  todos?: Todo[];
  workflows?: Workflow[];
  workflow_events?: WorkflowEvent[];
  task_workspace_ids?: string[];
  active_task_workspace_id?: string | null;
}

export interface AgentThread extends Thread<AgentThreadState> {}

export interface AgentThreadContext extends Record<string, unknown> {
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
  continue_workflows?: Workflow[];
  client_command?: Record<string, unknown>;
  session_governance?: Record<string, unknown>;
  ml_intern_profile?: "interactive" | "headless";
  ml_intern_source_repo?: string;
  ml_intern_source_commit?: string;
  permission_mode?: "workspace" | "system" | "yolo";
}
