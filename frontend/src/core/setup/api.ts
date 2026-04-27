import { getJSON, postJSON } from "../api/http";

import type {
  ApplySetupRequest,
  ApplySetupResponse,
  BrowseDirectoryResponse,
  CreateDirectoryResponse,
  SystemSetupStatus,
  UpdateDefaultModelRequest,
  UpdateDefaultModelResponse,
  ValidateWorkspaceResponse,
} from "./types";

export async function loadSetupStatus() {
  return getJSON<SystemSetupStatus>("/api/setup/status");
}

export async function validateWorkspace(path: string) {
  return postJSON<ValidateWorkspaceResponse>("/api/setup/validate-workspace", { path });
}

export async function applySetup(input: ApplySetupRequest) {
  return postJSON<ApplySetupResponse>("/api/setup/apply", input);
}

export async function updateDefaultModel(input: UpdateDefaultModelRequest) {
  return postJSON<UpdateDefaultModelResponse>("/api/setup/default-model", input);
}

export async function browseDirectory(path: string) {
  return postJSON<BrowseDirectoryResponse>("/api/setup/browse-directory", { path });
}

export async function createDirectory(path: string) {
  return postJSON<CreateDirectoryResponse>("/api/setup/create-directory", { path });
}
