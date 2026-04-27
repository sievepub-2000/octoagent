import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  applyTaskWorkspaceBuilderAction,
  applyTaskWorkspaceBuilderActionBatch,
  compileTaskWorkspace,
  createTaskAgentMessage,
  createTaskCheckpoint,
  createTaskWorkspace,
  deleteTaskWorkspace,
  listTaskWorkspaces,
  loadTaskAgentMessages,
  loadTaskAgents,
  loadTaskArtifacts,
  loadTaskCardGraph,
  loadTaskResult,
  loadTaskRunLog,
  loadTaskStudioRuntime,
  loadTaskStudioRuntimeEvents,
  loadTaskWorkspaceBuilderHistory,
  loadTaskWorkspaceBuilderPreview,
  loadTaskWorkspace,
  pauseTaskAgent,
  pauseTaskWorkspace,
  resumeTaskAgent,
  resumeTaskWorkspace,
  runTaskWorkspace,
  terminateTaskAgent,
  terminateTaskWorkspace,
  updateTaskCardGraph,
  updateTaskWorkspace,
} from "./api";
import { taskWorkspaceQueryKeys } from "./query-keys";
import type {
  TaskWorkspace,
  TaskWorkspaceListResponse,
  TaskWorkspaceStatus,
  TaskWorkspaceSummary,
} from "./types";

type WorkspaceMutationContext = {
  previousWorkspace?: TaskWorkspace;
  previousList?: TaskWorkspaceListResponse;
};

type QueryHookOptions = {
  enabled?: boolean;
  refetchInterval?: number | false;
};

function toTaskWorkspaceSummary(workspace: TaskWorkspace): TaskWorkspaceSummary {
  return {
    task_id: workspace.task_id,
    name: workspace.name,
    mode: workspace.mode,
    summary: workspace.summary,
    agent_runtime_provider: workspace.agent_runtime_provider,
    execution_strategy: workspace.execution_strategy,
    status: workspace.status,
    created_at: workspace.created_at,
    updated_at: workspace.updated_at,
    goal: workspace.goal,
    progress: workspace.progress,
  };
}

function upsertTaskWorkspaceCaches(
  queryClient: ReturnType<typeof useQueryClient>,
  workspace: TaskWorkspace,
) {
  queryClient.setQueryData(taskWorkspaceQueryKeys.detail(workspace.task_id), workspace);
  queryClient.setQueryData<TaskWorkspaceListResponse | undefined>(
    taskWorkspaceQueryKeys.all,
    (current) => {
      const nextSummary = toTaskWorkspaceSummary(workspace);
      if (!current) {
        return { workspaces: [nextSummary] };
      }
      const withoutCurrent = current.workspaces.filter(
        (entry) => entry.task_id !== workspace.task_id,
      );
      return { workspaces: [nextSummary, ...withoutCurrent] };
    },
  );
}

function patchTaskWorkspaceCachesStatus(
  queryClient: ReturnType<typeof useQueryClient>,
  taskId: string,
  status: TaskWorkspaceStatus,
) {
  queryClient.setQueryData<TaskWorkspace | undefined>(
    taskWorkspaceQueryKeys.detail(taskId),
    (current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        status,
        updated_at: new Date().toISOString(),
      };
    },
  );
  queryClient.setQueryData<TaskWorkspaceListResponse | undefined>(
    taskWorkspaceQueryKeys.all,
    (current) => {
      if (!current) {
        return current;
      }
      return {
        workspaces: current.workspaces.map((entry) =>
          entry.task_id === taskId
            ? {
                ...entry,
                status,
                updated_at: new Date().toISOString(),
              }
            : entry,
        ),
      };
    },
  );
}

export function useTaskWorkspaces({ enabled = true }: { enabled?: boolean } = {}) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: taskWorkspaceQueryKeys.all,
    queryFn: listTaskWorkspaces,
    enabled,
    refetchOnWindowFocus: false,
  });

  return {
    workspaces: data?.workspaces ?? [],
    isLoading,
    error,
    refetch,
  };
}

export function useTaskWorkspace(
  taskId: string | null,
  { enabled = true, refetchInterval = false }: QueryHookOptions = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: taskWorkspaceQueryKeys.detail(taskId),
    queryFn: () => loadTaskWorkspace(taskId!),
    enabled: enabled && taskId != null,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return {
    taskWorkspace: data,
    isLoading,
    error,
    refetch,
  };
}

export function useTaskCardGraph(
  taskId: string | null,
  { enabled = true, refetchInterval = false }: QueryHookOptions = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: taskWorkspaceQueryKeys.cardGraph(taskId),
    queryFn: () => loadTaskCardGraph(taskId!),
    enabled: enabled && taskId != null,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { cardGraph: data, isLoading, error, refetch };
}

export function useTaskAgents(
  taskId: string | null,
  { enabled = true, refetchInterval = false }: QueryHookOptions = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: taskWorkspaceQueryKeys.agents(taskId),
    queryFn: () => loadTaskAgents(taskId!),
    enabled: enabled && taskId != null,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { agents: data?.agents ?? [], isLoading, error, refetch };
}

export function useTaskRunLog(
  taskId: string | null,
  { enabled = true, refetchInterval = false }: QueryHookOptions = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: taskWorkspaceQueryKeys.runLog(taskId),
    queryFn: () => loadTaskRunLog(taskId!),
    enabled: enabled && taskId != null,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { runLog: data?.run_log ?? "", isLoading, error, refetch };
}

export function useTaskResult(
  taskId: string | null,
  { enabled = true, refetchInterval = false }: QueryHookOptions = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: taskWorkspaceQueryKeys.result(taskId),
    queryFn: () => loadTaskResult(taskId!),
    enabled: enabled && taskId != null,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return {
    resultContent: data?.result_content ?? "",
    hasResult: data?.has_result ?? false,
    sourcePath: data?.source_path ?? null,
    sourceLabel: data?.source_label ?? null,
    availableSources: data?.available_sources ?? [],
    isLoading,
    error,
    refetch,
  };
}

export function useTaskArtifacts(
  taskId: string | null,
  { enabled = true, refetchInterval = false }: QueryHookOptions = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: taskWorkspaceQueryKeys.artifacts(taskId),
    queryFn: () => loadTaskArtifacts(taskId!),
    enabled: enabled && taskId != null,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { artifacts: data?.files ?? [], isLoading, error, refetch };
}

export function useTaskStudioRuntime(
  taskId: string | null,
  { enabled = true, refetchInterval = false }: QueryHookOptions = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: taskWorkspaceQueryKeys.studioRuntime(taskId),
    queryFn: () => loadTaskStudioRuntime(taskId!),
    enabled: enabled && taskId != null,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { studioRuntime: data, isLoading, error, refetch };
}

export function useTaskStudioRuntimeEvents(
  taskId: string | null,
  cursor = 0,
  limit = 20,
  { enabled = true, refetchInterval = false }: QueryHookOptions = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: taskWorkspaceQueryKeys.studioRuntimeEvents(taskId, cursor, limit),
    queryFn: () => loadTaskStudioRuntimeEvents(taskId!, cursor, limit),
    enabled: enabled && taskId != null,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { studioRuntimeEvents: data, isLoading, error, refetch };
}

export function useTaskWorkspaceBuilderPreview(
  taskId: string | null,
  { enabled = true, refetchInterval = false }: QueryHookOptions = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: taskWorkspaceQueryKeys.builderPreview(taskId),
    queryFn: () => loadTaskWorkspaceBuilderPreview(taskId!),
    enabled: enabled && taskId != null,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { builderPreview: data, isLoading, error, refetch };
}

export function useTaskWorkspaceBuilderHistory(
  taskId: string | null,
  { enabled = true, refetchInterval = false }: QueryHookOptions = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: taskWorkspaceQueryKeys.builderHistory(taskId),
    queryFn: () => loadTaskWorkspaceBuilderHistory(taskId!),
    enabled: enabled && taskId != null,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { builderHistory: data, isLoading, error, refetch };
}

export function useTaskAgentMessages(
  taskId: string | null,
  agentId: string | null,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: taskWorkspaceQueryKeys.agentMessages(taskId, agentId),
    queryFn: () => loadTaskAgentMessages(taskId!, agentId!),
    enabled: enabled && taskId != null && agentId != null,
    refetchOnWindowFocus: false,
  });

  return { messages: data?.messages ?? [], isLoading, error, refetch };
}

function invalidateTaskWorkspaceQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  taskId?: string | null,
  agentId?: string | null,
) {
  void queryClient.invalidateQueries({ queryKey: taskWorkspaceQueryKeys.all });
  if (taskId) {
    void queryClient.invalidateQueries({ queryKey: taskWorkspaceQueryKeys.detail(taskId) });
    void queryClient.invalidateQueries({ queryKey: taskWorkspaceQueryKeys.cardGraph(taskId) });
    void queryClient.invalidateQueries({ queryKey: taskWorkspaceQueryKeys.agents(taskId) });
    void queryClient.invalidateQueries({ queryKey: taskWorkspaceQueryKeys.runLog(taskId) });
    void queryClient.invalidateQueries({ queryKey: taskWorkspaceQueryKeys.result(taskId) });
    void queryClient.invalidateQueries({ queryKey: taskWorkspaceQueryKeys.artifacts(taskId) });
    void queryClient.invalidateQueries({ queryKey: taskWorkspaceQueryKeys.studioRuntime(taskId) });
    void queryClient.invalidateQueries({ queryKey: taskWorkspaceQueryKeys.studioRuntimeEvents(taskId) });
    void queryClient.invalidateQueries({ queryKey: taskWorkspaceQueryKeys.builderPreview(taskId) });
    void queryClient.invalidateQueries({ queryKey: taskWorkspaceQueryKeys.builderHistory(taskId) });
  }
  if (taskId && agentId) {
    void queryClient.invalidateQueries({
      queryKey: taskWorkspaceQueryKeys.agentMessages(taskId, agentId),
    });
  }
}

export function useCreateTaskWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createTaskWorkspace,
    onSuccess: (workspace) => {
      queryClient.setQueryData<TaskWorkspaceListResponse | undefined>(
        taskWorkspaceQueryKeys.all,
        (current) => {
          const nextSummary = toTaskWorkspaceSummary(workspace);
          if (!current) {
            return { workspaces: [nextSummary] };
          }
          const withoutCurrent = current.workspaces.filter(
            (entry) => entry.task_id !== workspace.task_id,
          );
          return { workspaces: [nextSummary, ...withoutCurrent] };
        },
      );
      queryClient.setQueryData(taskWorkspaceQueryKeys.detail(workspace.task_id), workspace);
      invalidateTaskWorkspaceQueries(queryClient, workspace.task_id);
    },
  });
}

export function useDeleteTaskWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => deleteTaskWorkspace(taskId),
    onSuccess: () => invalidateTaskWorkspaceQueries(queryClient),
  });
}

export function useUpdateTaskWorkspace(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Parameters<typeof updateTaskWorkspace>[1]) =>
      updateTaskWorkspace(taskId, input),
    onSuccess: (workspace) => {
      upsertTaskWorkspaceCaches(queryClient, workspace);
      invalidateTaskWorkspaceQueries(queryClient, taskId);
    },
  });
}

export function useUpdateTaskCardGraph(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Parameters<typeof updateTaskCardGraph>[1]) =>
      updateTaskCardGraph(taskId, input),
    onSuccess: (workspace) => {
      upsertTaskWorkspaceCaches(queryClient, workspace);
      invalidateTaskWorkspaceQueries(queryClient, taskId);
    },
  });
}

export function useCompileTaskWorkspace(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => compileTaskWorkspace(taskId),
    onSuccess: (workspace) => {
      upsertTaskWorkspaceCaches(queryClient, workspace);
      invalidateTaskWorkspaceQueries(queryClient, taskId);
    },
  });
}

export function useRunTaskWorkspace(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Parameters<typeof runTaskWorkspace>[1]) =>
      runTaskWorkspace(taskId, input),
    onMutate: async (): Promise<WorkspaceMutationContext> => {
      await queryClient.cancelQueries({ queryKey: taskWorkspaceQueryKeys.detail(taskId) });
      await queryClient.cancelQueries({ queryKey: taskWorkspaceQueryKeys.all });
      const previousWorkspace = queryClient.getQueryData<TaskWorkspace>(taskWorkspaceQueryKeys.detail(taskId));
      const previousList = queryClient.getQueryData<TaskWorkspaceListResponse>(taskWorkspaceQueryKeys.all);
      patchTaskWorkspaceCachesStatus(queryClient, taskId, "running");
      return { previousWorkspace, previousList };
    },
    onError: (_error, _input, context) => {
      if (context?.previousWorkspace) {
        queryClient.setQueryData(taskWorkspaceQueryKeys.detail(taskId), context.previousWorkspace);
      }
      if (context?.previousList) {
        queryClient.setQueryData(taskWorkspaceQueryKeys.all, context.previousList);
      }
    },
    onSuccess: (workspace) => {
      upsertTaskWorkspaceCaches(queryClient, workspace);
      invalidateTaskWorkspaceQueries(queryClient, taskId);
    },
  });
}

export function useCreateTaskCheckpoint(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Parameters<typeof createTaskCheckpoint>[1]) =>
      createTaskCheckpoint(taskId, input),
    onSuccess: () => invalidateTaskWorkspaceQueries(queryClient, taskId),
  });
}

export function useTaskWorkspaceAction(taskId: string, action: "pause" | "resume" | "terminate") {
  const queryClient = useQueryClient();
  const fn =
    action === "pause"
      ? pauseTaskWorkspace
      : action === "resume"
        ? resumeTaskWorkspace
        : terminateTaskWorkspace;
  const optimisticStatus: TaskWorkspaceStatus =
    action === "pause"
      ? "paused"
      : action === "resume"
        ? "running"
        : "terminated";
  return useMutation({
    mutationFn: () => fn(taskId),
    onMutate: async (): Promise<WorkspaceMutationContext> => {
      await queryClient.cancelQueries({ queryKey: taskWorkspaceQueryKeys.detail(taskId) });
      await queryClient.cancelQueries({ queryKey: taskWorkspaceQueryKeys.all });
      const previousWorkspace = queryClient.getQueryData<TaskWorkspace>(taskWorkspaceQueryKeys.detail(taskId));
      const previousList = queryClient.getQueryData<TaskWorkspaceListResponse>(taskWorkspaceQueryKeys.all);
      patchTaskWorkspaceCachesStatus(queryClient, taskId, optimisticStatus);
      return { previousWorkspace, previousList };
    },
    onError: (_error, _input, context) => {
      if (context?.previousWorkspace) {
        queryClient.setQueryData(taskWorkspaceQueryKeys.detail(taskId), context.previousWorkspace);
      }
      if (context?.previousList) {
        queryClient.setQueryData(taskWorkspaceQueryKeys.all, context.previousList);
      }
    },
    onSuccess: (workspace) => {
      upsertTaskWorkspaceCaches(queryClient, workspace);
      invalidateTaskWorkspaceQueries(queryClient, taskId);
    },
  });
}

export function useApplyTaskWorkspaceBuilderAction(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Parameters<typeof applyTaskWorkspaceBuilderAction>[1]) =>
      applyTaskWorkspaceBuilderAction(taskId, input),
    onSuccess: () => invalidateTaskWorkspaceQueries(queryClient, taskId),
  });
}

export function useApplyTaskWorkspaceBuilderActionBatch(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Parameters<typeof applyTaskWorkspaceBuilderActionBatch>[1]) =>
      applyTaskWorkspaceBuilderActionBatch(taskId, input),
    onSuccess: () => invalidateTaskWorkspaceQueries(queryClient, taskId),
  });
}

export function useCreateTaskAgentMessage(taskId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Parameters<typeof createTaskAgentMessage>[2]) =>
      createTaskAgentMessage(taskId, agentId, input),
    onSuccess: () => invalidateTaskWorkspaceQueries(queryClient, taskId, agentId),
  });
}

export function useTaskAgentAction(
  taskId: string,
  agentId: string,
  action: "pause" | "resume" | "terminate",
) {
  const queryClient = useQueryClient();
  const fn =
    action === "pause"
      ? pauseTaskAgent
      : action === "resume"
        ? resumeTaskAgent
        : terminateTaskAgent;
  return useMutation({
    mutationFn: () => fn(taskId, agentId),
    onSuccess: () => invalidateTaskWorkspaceQueries(queryClient, taskId, agentId),
  });
}

