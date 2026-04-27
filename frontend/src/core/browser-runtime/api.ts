import { getJSON, postJSON } from "../api/http";

import type {
  BrowserActionExecutionRequest,
  BrowserActionExecutionResult,
  BrowserExecutionSession,
  BrowserProviderProfile,
  BrowserRuntimeCapability,
  BrowserSessionRecoveryRequest,
  BrowserSessionRequest,
  BrowserSessionUpdateRequest,
} from "./types";

export function loadBrowserRuntimeCapabilities() {
  return getJSON<BrowserRuntimeCapability>("/api/browser-runtime/capabilities");
}

export function loadBrowserRuntimeProviders() {
  return getJSON<BrowserProviderProfile[]>("/api/browser-runtime/providers");
}

export function loadBrowserRuntimeSessions() {
  return getJSON<BrowserExecutionSession[]>("/api/browser-runtime/sessions");
}

export function createBrowserRuntimeSession(payload: BrowserSessionRequest) {
  return postJSON<BrowserExecutionSession>("/api/browser-runtime/sessions", payload);
}

export function loadBrowserRuntimeSession(sessionId: string) {
  return getJSON<BrowserExecutionSession>(`/api/browser-runtime/sessions/${sessionId}`);
}

export function updateBrowserRuntimeSession(
  sessionId: string,
  payload: BrowserSessionUpdateRequest,
) {
  return postJSON<BrowserExecutionSession>(
    `/api/browser-runtime/sessions/${sessionId}/status`,
    payload,
  );
}

export function executeNextBrowserRuntimeAction(
  sessionId: string,
  payload: BrowserActionExecutionRequest = {},
) {
  return postJSON<BrowserActionExecutionResult>(
    `/api/browser-runtime/sessions/${sessionId}/execute-next`,
    payload,
  );
}

export function recoverBrowserRuntimeSession(
  sessionId: string,
  payload: BrowserSessionRecoveryRequest = {},
) {
  return postJSON<BrowserExecutionSession>(`/api/browser-runtime/sessions/${sessionId}/recover`, payload);
}
