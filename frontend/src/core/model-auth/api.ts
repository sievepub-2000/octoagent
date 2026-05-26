import { getJSON, postJSON } from "../api/http";

import type {
  ModelAuthProviderStatus,
  ModelAuthTemplate,
  ProviderAuthorizeRequest,
  ProviderOAuthCompleteRequest,
  ProviderOAuthCompleteResponse,
  ProviderOAuthConfirmRequest,
  ProviderOAuthConfirmResponse,
  ProviderOAuthModelsRequest,
  ProviderOAuthModelsResponse,
  ProviderOAuthStartRequest,
  ProviderOAuthStartResponse,
} from "./types";

export async function loadModelAuthTemplates() {
  const { templates } = await getJSON<{ templates: ModelAuthTemplate[] }>("/api/model-auth/templates");
  return templates;
}

export async function loadModelAuthStatus() {
  const { providers } = await getJSON<{ providers: Record<string, ModelAuthProviderStatus> }>("/api/model-auth/status");
  return providers;
}

export async function authorizeModelProvider(providerId: string, payload: ProviderAuthorizeRequest) {
  return postJSON<{ success: boolean; provider: ModelAuthProviderStatus; model?: unknown }>(
    `/api/model-auth/${encodeURIComponent(providerId)}/authorize`,
    payload,
  );
}

export async function startModelProviderOAuth(providerId: string, payload: ProviderOAuthStartRequest) {
  return postJSON<ProviderOAuthStartResponse>(
    `/api/model-auth/${encodeURIComponent(providerId)}/oauth/start`,
    payload,
  );
}

export async function confirmModelProviderOAuth(providerId: string, payload: ProviderOAuthConfirmRequest) {
  return postJSON<ProviderOAuthConfirmResponse>(
    `/api/model-auth/${encodeURIComponent(providerId)}/oauth/confirm`,
    payload,
  );
}

export async function loadModelProviderOAuthModels(providerId: string, payload: ProviderOAuthModelsRequest = {}) {
  return postJSON<ProviderOAuthModelsResponse>(
    `/api/model-auth/${encodeURIComponent(providerId)}/oauth/models`,
    payload,
  );
}

export async function completeModelProviderOAuth(providerId: string, payload: ProviderOAuthCompleteRequest) {
  return postJSON<ProviderOAuthCompleteResponse>(
    `/api/model-auth/${encodeURIComponent(providerId)}/oauth/complete`,
    payload,
  );
}

export async function logoutModelProvider(providerId: string) {
  return postJSON<{ success: boolean; provider: ModelAuthProviderStatus }>(
    `/api/model-auth/${encodeURIComponent(providerId)}/logout`,
  );
}

export async function testModelProvider(providerId: string) {
  return postJSON<{ ok: boolean; message?: string; http_status?: number }>(
    `/api/model-auth/${encodeURIComponent(providerId)}/test`,
  );
}

export async function syncModelProvider(providerId: string) {
  return postJSON<{ success: boolean; model: unknown }>(
    `/api/model-auth/${encodeURIComponent(providerId)}/sync-model`,
  );
}
