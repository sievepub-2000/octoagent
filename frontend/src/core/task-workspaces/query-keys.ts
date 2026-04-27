export const taskWorkspaceQueryKeys = {
  all: ["task-workspaces"] as const,
  detail: (taskId: string | null) => ["task-workspace", taskId] as const,
  cardGraph: (taskId: string | null) => ["task-workspace-card-graph", taskId] as const,
  agents: (taskId: string | null) => ["task-workspace-agents", taskId] as const,
  runLog: (taskId: string | null) => ["task-workspace-run-log", taskId] as const,
  result: (taskId: string | null) => ["task-workspace-result", taskId] as const,
  artifacts: (taskId: string | null) => ["task-workspace-artifacts", taskId] as const,
  studioRuntime: (taskId: string | null) => ["task-workspace-studio-runtime", taskId] as const,
  studioRuntimeEvents: (taskId: string | null, cursor?: number, limit?: number) =>
    cursor == null || limit == null
      ? (["task-workspace-studio-runtime-events", taskId] as const)
      : (["task-workspace-studio-runtime-events", taskId, cursor, limit] as const),
  builderPreview: (taskId: string | null) => ["task-workspace-builder-preview", taskId] as const,
  builderHistory: (taskId: string | null) => ["task-workspace-builder-history", taskId] as const,
  agentMessages: (taskId: string | null, agentId: string | null) =>
    ["task-workspace-agent-messages", taskId, agentId] as const,
};

export const taskWorkspacePolling = {
  off: false,
  detail: 5000,
  live: 3000,
  console: 1500,
} as const;
