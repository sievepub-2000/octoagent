import { getJSON } from "../api/http";

import type {
  CompiledTaskGraph,
  OrchestrationCapability,
  PromptStackProfile,
} from "./types";

export function loadOrchestrationCapabilities() {
  return getJSON<OrchestrationCapability>("/api/orchestration/capabilities");
}

export function loadPromptStacks() {
  return getJSON<PromptStackProfile[]>("/api/orchestration/prompt-stacks");
}

export function loadSeedTaskGraph() {
  return getJSON<CompiledTaskGraph>("/api/orchestration/graphs/seed");
}
