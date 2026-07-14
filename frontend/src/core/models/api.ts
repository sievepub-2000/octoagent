import { deleteJSON, getJSON, postJSON, putJSON } from "../api/http";

import type { Model, ModelCreateRequest, ModelUpdateRequest } from "./types";

export async function loadModels() {
  const { models } = await getJSON<{ models: Model[] }>("/api/models");
  return models;
}

export async function deleteModel(modelName: string) {
  return deleteJSON<{ deleted: boolean; model_name: string }>(`/api/models/${encodeURIComponent(modelName)}`);
}

export async function createModel(payload: ModelCreateRequest) {
  return postJSON<Model>("/api/models", payload);
}

export async function updateModel(modelName: string, payload: ModelUpdateRequest) {
  return putJSON<Model>(`/api/models/${encodeURIComponent(modelName)}`, payload);
}

export async function setDefaultModel(modelName: string) {
  return putJSON<Model>(`/api/models/${encodeURIComponent(modelName)}/default`, {});
}

export async function testModelConnection(modelName: string) {
  return postJSON<{ ok: boolean; model_name: string; latency_ms: number; response_preview: string }>(
    `/api/models/${encodeURIComponent(modelName)}/test`,
    {},
  );
}
