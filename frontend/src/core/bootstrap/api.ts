import { getJSON, postJSON } from "../api/http";

import type {
  BootstrapGuideResponse,
  BootstrapInstallResponse,
  BootstrapStatus,
} from "./types";

export async function loadBootstrapStatus() {
  return getJSON<BootstrapStatus>("/api/bootstrap/status");
}

export async function installBootstrapModel() {
  return postJSON<BootstrapInstallResponse>("/api/bootstrap/install");
}

export async function generateBootstrapGuide(input: {
  user_goal?: string;
  workspace_summary?: string;
}) {
  return postJSON<BootstrapGuideResponse>("/api/bootstrap/guide", input);
}
