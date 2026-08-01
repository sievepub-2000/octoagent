import { getJSON, postJSON } from "../api/http";

import type {
  RuntimeCapabilities,
  RuntimeLongRunningHealth,
  RuntimeMaintenanceStatus,
} from "./types";

export async function loadRuntimeCapabilities() {
  return getJSON<RuntimeCapabilities>("/api/runtime/capabilities");
}

export async function loadRuntimeLongRunningHealth() {
  return getJSON<RuntimeLongRunningHealth>("/api/runtime/long-running-health");
}

export async function loadRuntimeMaintenanceStatus() {
  return getJSON<RuntimeMaintenanceStatus>("/api/runtime/maintenance/status");
}

export async function runRuntimeMaintenance() {
  return postJSON<RuntimeMaintenanceStatus>("/api/runtime/maintenance/run", {});
}
