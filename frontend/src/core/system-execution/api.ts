import { getJSON, postJSON, putJSON } from "../api/http";

import type {
  SystemExecutionAuditEntry,
  SystemExecutionCapability,
  SystemExecutionCliRequest,
  SystemExecutionCliResponse,
  SystemExecutionConfig,
  SystemExecutionDesktopSnapshot,
  SystemExecutionPermissionPolicy,
  RuntimeDoctorResponse,
  SystemExecutionPlan,
  SystemExecutionPlanRequest,
  SystemExecutionSession,
  SystemExecutionSessionListResponse,
  SystemExecutionSessionRecoveryRequest,
  SystemExecutionStepExecutionRequest,
  SystemExecutionStepExecutionResult,
  SystemExecutionSessionUpdateRequest,
} from "./types";

export function loadSystemExecutionCapabilities() {
  return getJSON<SystemExecutionCapability>("/api/system-execution/capabilities");
}

export function loadSystemExecutionPermissionPolicy() {
  return getJSON<SystemExecutionPermissionPolicy>("/api/system-execution/permission-policy");
}

export function loadSystemExecutionConfig() {
  return getJSON<SystemExecutionConfig>("/api/system-execution/config");
}

export function updateSystemExecutionConfig(input: SystemExecutionConfig) {
  return putJSON<SystemExecutionConfig>("/api/system-execution/config", input);
}

export function planSystemExecution(input: SystemExecutionPlanRequest) {
  return postJSON<SystemExecutionPlan>("/api/system-execution/plan", input);
}

export function createSystemExecutionSession(input: SystemExecutionPlanRequest) {
  return postJSON<SystemExecutionSession>("/api/system-execution/sessions", input);
}

export function createLiveSystemExecutionSession(input: SystemExecutionPlanRequest) {
  return postJSON<SystemExecutionSession>("/api/system-execution/sessions/live", input);
}

export function executeWorkspaceCliCommand(input: SystemExecutionCliRequest) {
  return postJSON<SystemExecutionCliResponse>("/api/system-execution/cli/workspace", input);
}

export function executeSystemCliCommand(input: SystemExecutionCliRequest) {
  return postJSON<SystemExecutionCliResponse>("/api/system-execution/cli/system", input);
}

export function loadSystemExecutionSession(sessionId: string) {
  return getJSON<SystemExecutionSession>(`/api/system-execution/sessions/${sessionId}`);
}

export function loadSystemExecutionSessions({
  limit,
  relatedTaskId,
  target,
}: {
  limit?: number;
  relatedTaskId?: string;
  target?: string;
} = {}) {
  return getJSON<SystemExecutionSessionListResponse>("/api/system-execution/sessions", {
    limit,
    related_task_id: relatedTaskId,
    target,
  });
}

export function updateSystemExecutionSession(
  sessionId: string,
  payload: SystemExecutionSessionUpdateRequest,
) {
  return postJSON<SystemExecutionSession>(
    `/api/system-execution/sessions/${sessionId}/status`,
    payload,
  );
}

export function executeNextSystemExecutionStep(
  sessionId: string,
  payload: SystemExecutionStepExecutionRequest = {},
) {
  return postJSON<SystemExecutionStepExecutionResult>(
    `/api/system-execution/sessions/${sessionId}/execute-next`,
    payload,
  );
}

export function recoverSystemExecutionSession(
  sessionId: string,
  payload: SystemExecutionSessionRecoveryRequest = {},
) {
  return postJSON<SystemExecutionSession>(
    `/api/system-execution/sessions/${sessionId}/recover`,
    payload,
  );
}

export function loadSystemExecutionSnapshot(sessionId: string) {
  return getJSON<SystemExecutionDesktopSnapshot>(
    `/api/system-execution/sessions/${sessionId}/snapshot`,
  );
}

export function loadSystemExecutionAudit(sessionId: string) {
  return getJSON<SystemExecutionAuditEntry[]>(
    `/api/system-execution/sessions/${sessionId}/audit`,
  );
}

export function loadRuntimeDoctor() {
  return getJSON<RuntimeDoctorResponse>("/api/runtime/doctor");
}

export interface RuntimeProviderHealthEntry {
  available: boolean;
  detail: string;
  sdk_info?: Record<string, unknown>;
}

export interface RuntimeProviderHealthResponse {
  providers: Record<string, RuntimeProviderHealthEntry>;
}

export function loadRuntimeProviderHealth() {
  return getJSON<RuntimeProviderHealthResponse>("/api/runtime/provider-health");
}
