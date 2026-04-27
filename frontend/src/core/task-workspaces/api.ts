import { deleteJSON, getJSON, postJSON, putJSON } from "../api/http";

import type {
  TaskArtifactListResponse,
  CreateAgentMessageRequest,
  ApplyTaskWorkspaceBuilderActionRequest,
  ApplyTaskWorkspaceBuilderBatchRequest,
  CreateCheckpointRequest,
  CreateTaskWorkspaceRequest,
  ExecuteTaskRequest,
  TaskAgentListResponse,
  TaskAgentMessagesResponse,
  TaskWorkspaceBuilderHistoryResponse,
  TaskWorkspaceBuilderPreviewResponse,
  TaskCardGraphResponse,
  TaskResultResponse,
  TaskRunLogResponse,
  TaskStudioRuntimeResponse,
  TaskStudioRuntimeEventsResponse,
  TaskWorkspace,
  TaskWorkspaceListResponse,
  UpdateTaskCardGraphRequest,
  UpdateTaskWorkspaceRequest,
} from "./types";

export async function listTaskWorkspaces() {
  return getJSON<TaskWorkspaceListResponse>("/api/task-workspaces");
}

export async function createTaskWorkspace(input: CreateTaskWorkspaceRequest) {
  return postJSON<TaskWorkspace>("/api/task-workspaces", input);
}

export async function loadTaskWorkspace(taskId: string) {
  return getJSON<TaskWorkspace>(`/api/task-workspaces/${taskId}`);
}

export async function deleteTaskWorkspace(taskId: string) {
  return deleteJSON<void>(`/api/task-workspaces/${taskId}`);
}

export async function updateTaskWorkspace(
  taskId: string,
  input: UpdateTaskWorkspaceRequest,
) {
  return putJSON<TaskWorkspace>(`/api/task-workspaces/${taskId}`, input);
}

export async function loadTaskCardGraph(taskId: string) {
  return getJSON<TaskCardGraphResponse>(`/api/task-workspaces/${taskId}/cards`);
}

export async function updateTaskCardGraph(
  taskId: string,
  input: UpdateTaskCardGraphRequest,
) {
  return putJSON<TaskWorkspace>(`/api/task-workspaces/${taskId}/cards`, input);
}

export async function compileTaskWorkspace(taskId: string) {
  return postJSON<TaskWorkspace>(`/api/task-workspaces/${taskId}/compile`);
}

export async function createTaskCheckpoint(
  taskId: string,
  input: CreateCheckpointRequest,
) {
  return postJSON<TaskWorkspace>(
    `/api/task-workspaces/${taskId}/checkpoints`,
    input,
  );
}

export async function runTaskWorkspace(taskId: string, input: ExecuteTaskRequest) {
  return postJSON<TaskWorkspace>(`/api/task-workspaces/${taskId}/run`, input);
}

export async function loadTaskRunLog(taskId: string) {
  return getJSON<TaskRunLogResponse>(`/api/task-workspaces/${taskId}/run-log`);
}

export async function loadTaskResult(taskId: string) {
  return getJSON<TaskResultResponse>(`/api/task-workspaces/${taskId}/result`);
}

export async function loadTaskArtifacts(taskId: string) {
  return getJSON<TaskArtifactListResponse>(`/api/task-workspaces/${taskId}/artifacts`);
}

export async function loadTaskStudioRuntime(taskId: string) {
  return getJSON<TaskStudioRuntimeResponse>(`/api/task-workspaces/${taskId}/studio-runtime`);
}

export async function loadTaskStudioRuntimeEvents(
  taskId: string,
  cursor = 0,
  limit = 20,
) {
  return getJSON<TaskStudioRuntimeEventsResponse>(
    `/api/task-workspaces/${taskId}/studio-runtime/events?cursor=${cursor}&limit=${limit}`,
  );
}

export async function loadTaskWorkspaceBuilderPreview(taskId: string) {
  return getJSON<TaskWorkspaceBuilderPreviewResponse>(
    `/api/task-workspaces/${taskId}/builder-actions/preview`,
  );
}

export async function loadTaskWorkspaceBuilderHistory(taskId: string) {
  return getJSON<TaskWorkspaceBuilderHistoryResponse>(
    `/api/task-workspaces/${taskId}/builder-actions/history`,
  );
}

export async function applyTaskWorkspaceBuilderAction(
  taskId: string,
  input: ApplyTaskWorkspaceBuilderActionRequest,
) {
  return postJSON<TaskWorkspaceBuilderHistoryResponse>(
    `/api/task-workspaces/${taskId}/builder-actions/apply`,
    input,
  );
}

export async function applyTaskWorkspaceBuilderActionBatch(
  taskId: string,
  input: ApplyTaskWorkspaceBuilderBatchRequest,
) {
  return postJSON<TaskWorkspaceBuilderHistoryResponse>(
    `/api/task-workspaces/${taskId}/builder-actions/apply-batch`,
    input,
  );
}

export async function pauseTaskWorkspace(taskId: string) {
  return postJSON<TaskWorkspace>(`/api/task-workspaces/${taskId}/pause`);
}

export async function resumeTaskWorkspace(taskId: string) {
  return postJSON<TaskWorkspace>(`/api/task-workspaces/${taskId}/resume`);
}

export async function terminateTaskWorkspace(taskId: string) {
  return postJSON<TaskWorkspace>(`/api/task-workspaces/${taskId}/terminate`);
}

export async function loadTaskAgents(taskId: string) {
  return getJSON<TaskAgentListResponse>(`/api/task-workspaces/${taskId}/agents`);
}

export async function loadTaskAgentMessages(taskId: string, agentId: string) {
  return getJSON<TaskAgentMessagesResponse>(
    `/api/task-workspaces/${taskId}/agents/${agentId}/messages`,
  );
}

export async function createTaskAgentMessage(
  taskId: string,
  agentId: string,
  input: CreateAgentMessageRequest,
) {
  return postJSON<TaskAgentMessagesResponse>(
    `/api/task-workspaces/${taskId}/agents/${agentId}/messages`,
    input,
  );
}

export async function pauseTaskAgent(taskId: string, agentId: string) {
  return postJSON<TaskWorkspace>(
    `/api/task-workspaces/${taskId}/agents/${agentId}/pause`,
  );
}

export async function resumeTaskAgent(taskId: string, agentId: string) {
  return postJSON<TaskWorkspace>(
    `/api/task-workspaces/${taskId}/agents/${agentId}/resume`,
  );
}

export async function terminateTaskAgent(taskId: string, agentId: string) {
  return postJSON<TaskWorkspace>(
    `/api/task-workspaces/${taskId}/agents/${agentId}/terminate`,
  );
}
