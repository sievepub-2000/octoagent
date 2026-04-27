import { getJSON, postJSON } from "../api/http";

import type {
  QueryOperationPlanRequest,
  QueryOperationPlanResponse,
  QueryEngineCapability,
  QuerySession,
  QuerySessionCompactRequest,
  QuerySessionRefreshRequest,
  QueryTurnExecutionRequest,
  QueryTurnRecordRequest,
} from "./types";

export function loadQueryEngineCapabilities() {
  return getJSON<QueryEngineCapability>("/api/query-engine/capabilities");
}

export function planQueryOperation(body: QueryOperationPlanRequest) {
  return postJSON<QueryOperationPlanResponse>("/api/query-engine/plan-operation", body);
}

export function loadQueryEngineSessions() {
  return getJSON<QuerySession[]>("/api/query-engine/sessions");
}

export function loadQueryEngineSession(sessionId: string) {
  return getJSON<QuerySession>(`/api/query-engine/sessions/${sessionId}`);
}

export function recordQueryEngineTurn(sessionId: string, payload: QueryTurnRecordRequest) {
  return postJSON<QuerySession>(`/api/query-engine/sessions/${sessionId}/turns`, payload);
}

export function executeQueryEngineTurn(sessionId: string, payload: QueryTurnExecutionRequest) {
  return postJSON<QuerySession>(`/api/query-engine/sessions/${sessionId}/execute`, payload);
}

export function compactQueryEngineSession(sessionId: string, payload: QuerySessionCompactRequest) {
  return postJSON<QuerySession>(`/api/query-engine/sessions/${sessionId}/compact`, payload);
}

export function refreshQueryEngineSessionProfile(
  sessionId: string,
  payload: QuerySessionRefreshRequest = {},
) {
  return postJSON<QuerySession>(`/api/query-engine/sessions/${sessionId}/refresh-profile`, payload);
}
