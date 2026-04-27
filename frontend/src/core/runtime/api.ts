import { getJSON, postJSON } from "../api/http";

import type {
  RuntimeCapabilities,
  RuntimeLongRunningHealth,
  RuntimeMaintenanceStatus,
  SystemGuardExportResponse,
  SystemGuardRepairRequest,
  SystemGuardRepairResponse,
  SystemGuardStatus,
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

export async function runRuntimeMaintenance(input: {
  max_checkpoints_per_thread?: number;
  max_runs_per_thread?: number;
} = {}) {
  return postJSON<Record<string, unknown>>("/api/runtime/maintenance/run", input);
}

export async function loadSystemGuardStatus(limit = 10) {
  return getJSON<SystemGuardStatus>("/api/runtime/system-guard/status", { limit });
}

export async function runSystemGuardRepair(
  input: SystemGuardRepairRequest = {},
) {
  return postJSON<SystemGuardRepairResponse>(
    "/api/runtime/system-guard/repair",
    input,
  );
}

export async function exportSystemGuardSnapshots(limit = 20) {
  return getJSON<SystemGuardExportResponse>(
    "/api/runtime/system-guard/export",
    { limit },
  );
}
