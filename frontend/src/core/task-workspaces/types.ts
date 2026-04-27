import type { BrainBuilderActionModel } from "../brain/types";

export type TaskExecutionMode = "single" | "branch" | "group";
export type TaskAgentPermissionMode = "workspace" | "system" | "yolo";
export type TaskAgentRuntimeProvider = "langgraph";
export type AgentExecutionStrategy = "fixed";

export type TaskWorkspaceStatus =
  | "created"
  | "planned"
  | "running"
  | "paused"
  | "waiting_review"
  | "completed"
  | "terminated"
  | "failed";

export type TaskCardKind =
  | "start"
  | "agent"
  | "conversation-interface"
  | "tooling"
  | "research"
  | "docker-runtime"
  | "branch-router"
  | "group-manager"
  | "checkpoint"
  | "artifact"
  | "review";

export type TaskCardStatus =
  | "idle"
  | "configured"
  | "running"
  | "paused"
  | "blocked"
  | "completed"
  | "terminated";

export type AgentHandleStatus =
  | "idle"
  | "queued"
  | "running"
  | "paused"
  | "waiting_handoff"
  | "completed"
  | "terminated"
  | "failed";

export interface TaskProgress {
  completed_cards: number;
  total_cards: number;
  active_agents: number;
  completed_agents: number;
  checkpoint_count: number;
}

export interface DeploymentInterface {
  kind: "conversation" | "api" | "webhook" | "internal";
  label: string;
  enabled: boolean;
  config: Record<string, unknown>;
}

export interface DockerExecutionProfile {
  profile_id: string;
  label: string;
  runtime_kind:
    | "local_host"
    | "docker_local"
    | "docker_provisioner"
    | "remote_runtime"
    | "desktop_local";
  selected: boolean;
  image?: string | null;
  resource_limits: Record<string, unknown>;
  mounts: string[];
  network_policy: string;
  persistence_mode: string;
  checkpoint_policy: string;
  approval_level: "none" | "soft" | "strict";
  live_status: "ready" | "degraded" | "disabled";
  capabilities: string[];
}

export interface TaskCard {
  card_id: string;
  kind: TaskCardKind;
  title: string;
  description?: string | null;
  status: TaskCardStatus;
  linked_agent_id?: string | null;
  permission_mode: TaskAgentPermissionMode;
  config: Record<string, unknown>;
  tags: string[];
}

export interface TaskCardEdge {
  edge_id: string;
  source_card_id: string;
  target_card_id: string;
  label?: string | null;
}

export interface TaskCardGraph {
  cards: TaskCard[];
  edges: TaskCardEdge[];
}

export interface CheckpointRef {
  checkpoint_id: string;
  label: string;
  task_status: TaskWorkspaceStatus;
  created_at: string;
  card_id?: string | null;
  note?: string | null;
}

export interface AgentConversationRef {
  task_id: string;
  agent_id: string;
  message_count: number;
  last_message_at?: string | null;
}

export interface AgentHandle {
  agent_id: string;
  name: string;
  role: string;
  status: AgentHandleStatus;
  model_name?: string | null;
  runtime_provider?: string | null;
  linked_card_id?: string | null;
  task_scope?: string | null;
  conversation: AgentConversationRef;
  metadata: Record<string, unknown>;
}

export interface AgentMessage {
  message_id: string;
  role: "system" | "user" | "assistant";
  content: string;
  created_at: string;
}

export interface TaskWorkspaceSummary {
  task_id: string;
  name: string;
  mode: TaskExecutionMode;
  summary: string;
  agent_runtime_provider: TaskAgentRuntimeProvider;
  execution_strategy?: AgentExecutionStrategy;
  status: TaskWorkspaceStatus;
  created_at: string;
  updated_at: string;
  goal: string;
  progress: TaskProgress;
}

export interface TaskWorkspace {
  task_id: string;
  name: string;
  mode: TaskExecutionMode;
  agent_runtime_provider: TaskAgentRuntimeProvider;
  execution_strategy?: AgentExecutionStrategy;
  status: TaskWorkspaceStatus;
  created_at: string;
  updated_at: string;
  goal: string;
  summary: string;
  top_bar_label?: string | null;
  deployment_interfaces: DeploymentInterface[];
  runtime_profiles: DockerExecutionProfile[];
  card_graph: TaskCardGraph;
  agents: AgentHandle[];
  checkpoints: CheckpointRef[];
  progress: TaskProgress;
  metadata: Record<string, unknown>;
}

export interface TaskWorkspaceListResponse {
  workspaces: TaskWorkspaceSummary[];
}

export interface TaskCardGraphResponse {
  task_id: string;
  card_graph: TaskCardGraph;
  progress: TaskProgress;
}

export interface TaskAgentListResponse {
  task_id: string;
  agents: AgentHandle[];
}

export interface TaskAgentMessagesResponse {
  task_id: string;
  agent_id: string;
  messages: AgentMessage[];
}

export interface TaskRunLogResponse {
  task_id: string;
  run_log: string;
}

export interface TaskResultResponse {
  task_id: string;
  result_content: string;
  has_result: boolean;
  source_path?: string | null;
  source_label?: string | null;
  available_sources?: string[];
}

export interface TaskArtifactFile {
  name: string;
  path: string;
  download_url: string;
}

export interface TaskArtifactListResponse {
  task_id: string;
  files: TaskArtifactFile[];
}

export interface TaskStudioChannelBinding {
  kind: string;
  label: string;
  enabled: boolean;
  status: string;
  source: string;
}

export interface TaskStudioBindingItem {
  binding_id: string;
  kind: string;
  label: string;
  enabled: boolean;
  status: string;
  source: string;
}

export interface TaskStudioBindings {
  channels: TaskStudioBindingItem[];
  mcp_servers: TaskStudioBindingItem[];
  skills: TaskStudioBindingItem[];
  plugins: TaskStudioBindingItem[];
}

export interface TaskStudioTimelineEvent {
  event_id: string;
  kind: string;
  created_at: string;
  title: string;
  details: string[];
  summary?: string | null;
  source?: string | null;
  agent_id?: string | null;
  card_id?: string | null;
  session_id?: string | null;
}

export interface TaskStudioHandoff {
  handoff_id: string;
  source_agent_id: string;
  target_agent_id: string;
  status: string;
  query_session_id?: string | null;
  runtime_session_id?: string | null;
  linked_card_id?: string | null;
  created_at: string;
  summary?: string | null;
}

export interface TaskStudioCheckpointSummary {
  total: number;
  latest?: string | null;
  ready_for_review: boolean;
}

export interface TaskStudioWorkflowSummary {
  graph_version: string;
  cards_total: number;
  active_cards: number;
  completed_cards: number;
  blocked_cards: number;
  queued_cards: number;
  review_policy: string;
}

export interface TaskStudioReadiness {
  can_run: boolean;
  can_resume: boolean;
  requires_review: boolean;
  blocked_cards: number;
  queued_cards: number;
  completed_cards: number;
  active_handoffs: number;
  enabled_bindings: number;
  artifact_count: number;
}

export interface TaskStudioAgentSummary {
  agent_id: string;
  name: string;
  role: string;
  status: AgentHandleStatus | TaskWorkspaceStatus | string;
  model_name?: string | null;
  task_scope?: string | null;
  linked_card_id?: string | null;
  query_session_id?: string | null;
  runtime_session_id?: string | null;
  langgraph_assistant_id?: string | null;
  langgraph_thread_scope?: string | null;
  last_runtime_provider?: string | null;
  latest_checkpoint_id?: string | null;
  memory_status?: string | null;
  last_execution_target?: string | null;
  last_execution_status?: string | null;
  last_result_summary?: string | null;
  message_count: number;
  last_message_at?: string | null;
}

export interface TaskStudioRuntimeSummary {
  project_memory_digest?: string | null;
  project_memory_updated_at?: string | null;
  latest_query_session_id?: string | null;
  latest_runtime_session_id?: string | null;
  active_query_sessions?: number;
  active_runtime_sessions?: number;
  memory_guard_state?: string | null;
  current_phase?: string | null;
  last_runtime_sync_at?: string | null;
  langgraph_graph_id?: string | null;
  last_langgraph_assistant_id?: string | null;
  langgraph_thread_scope?: string | null;
  langgraph_native_runtime?: boolean;
  last_execution_target?: string | null;
  last_execution_status?: string | null;
  last_agent_result_summary?: string | null;
  last_runtime_provider?: string | null;
  execution_strategy?: string | null;
}

export interface TaskStudioRuntimeResponse {
  task_id: string;
  name: string;
  mode: TaskExecutionMode;
  status: TaskWorkspaceStatus;
  goal: string;
  updated_at: string;
  progress: TaskProgress;
  workflow_summary: TaskStudioWorkflowSummary;
  agents: TaskStudioAgentSummary[];
  timeline: TaskStudioTimelineEvent[];
  handoffs: TaskStudioHandoff[];
  checkpoints: CheckpointRef[];
  checkpoints_summary: TaskStudioCheckpointSummary;
  artifacts: TaskArtifactFile[];
  bindings: TaskStudioBindings;
  channel_bindings: TaskStudioChannelBinding[];
  readiness: TaskStudioReadiness;
  runtime_summary: TaskStudioRuntimeSummary;
  run_log: string;
}

export interface TaskStudioRuntimeEventsResponse {
  task_id: string;
  cursor: number;
  next_cursor?: number | null;
  events: TaskStudioTimelineEvent[];
}

export interface TaskWorkspaceBuilderHistoryEntry {
  transaction_id: string;
  revision: number;
  applied_at: string;
  action_ids: string[];
  action_title: string;
  patch: Record<string, unknown>;
  source?: string;
  applied_by?: string;
}

export interface TaskWorkspaceBuilderPreviewResponse {
  task_id: string;
  generated_at: string;
  summary: string;
  builder_action_model: BrainBuilderActionModel;
  current_draft: Record<string, unknown>;
  revision: number;
  applied_action_ids: string[];
  history: TaskWorkspaceBuilderHistoryEntry[];
  conflict_warnings?: string[];
}

export interface TaskWorkspaceBuilderApplyResponse {
  task_id: string;
  transaction_id: string;
  status: string;
  revision: number;
  current_draft: Record<string, unknown>;
  applied_action_ids: string[];
  history: TaskWorkspaceBuilderHistoryEntry[];
  affected_keys?: string[];
}

export interface TaskWorkspaceBuilderHistoryResponse {
  task_id: string;
  revision: number;
  current_draft: Record<string, unknown>;
  applied_action_ids: string[];
  history: TaskWorkspaceBuilderHistoryEntry[];
}

export interface ApplyTaskWorkspaceBuilderActionRequest {
  action_id: string;
}

export interface ApplyTaskWorkspaceBuilderBatchRequest {
  action_ids?: string[];
  use_apply_all_patch?: boolean;
}

export interface CreateTaskWorkspaceRequest {
  name?: string;
  goal?: string;
  mode?: TaskExecutionMode;
  agent_runtime_provider?: TaskAgentRuntimeProvider;
  execution_strategy?: AgentExecutionStrategy;
  summary?: string;
  auto_research?: boolean;
  enabled_skills?: string[];
  expected_keywords?: string[];
  max_turns?: number;
  timeout_seconds?: number;
  token_budget?: number;
}

export interface UpdateTaskWorkspaceRequest {
  name?: string;
  goal?: string;
  summary?: string;
  agent_runtime_provider?: TaskAgentRuntimeProvider;
  execution_strategy?: AgentExecutionStrategy;
  status?: TaskWorkspaceStatus;
  top_bar_label?: string;
  metadata?: Record<string, unknown>;
}

export interface UpdateTaskCardGraphRequest {
  card_graph: TaskCardGraph;
}

export interface CreateCheckpointRequest {
  label?: string;
  card_id?: string;
  note?: string;
}

export interface CreateAgentMessageRequest {
  content: string;
  model_override?: string;
}

export interface ExecuteTaskRequest {
  auto_compile?: boolean;
  auto_iterate?: boolean;
  max_iterations?: number;
}
