import { getJSON, putJSON } from "@/core/api/http";

import type { RepoHook, RepoHooksResponse } from "./types";

export function loadRepoHooks() {
  return getJSON<RepoHooksResponse>("/api/hooks");
}

export function updateRepoHook(hookName: string, enabled: boolean) {
  return putJSON<RepoHook>(`/api/hooks/${encodeURIComponent(hookName)}`, { enabled });
}