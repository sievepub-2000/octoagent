import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  exportSystemGuardSnapshots,
  loadRuntimeCapabilities,
  loadRuntimeLongRunningHealth,
  loadRuntimeMaintenanceStatus,
  loadRuntimeRunRecords,
  loadSystemGuardStatus,
  runRuntimeMaintenance,
  runSystemGuardRepair,
} from "./api";

const RUNTIME_CAPABILITIES_STALE_MS = 5 * 60_000;
const RUNTIME_CAPABILITIES_GC_MS = 30 * 60_000;

export function useRuntimeCapabilities({
  enabled = true,
}: {
  enabled?: boolean;
} = {}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["runtime-capabilities"],
    queryFn: () => loadRuntimeCapabilities(),
    enabled,
    refetchOnWindowFocus: false,
    staleTime: RUNTIME_CAPABILITIES_STALE_MS,
    gcTime: RUNTIME_CAPABILITIES_GC_MS,
  });

  return { runtime: data, isLoading, error };
}

export function useRuntimeLongRunningHealth({
  enabled = true,
  refetchInterval = 15_000,
}: {
  enabled?: boolean;
  refetchInterval?: number | false;
} = {}) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["runtime-long-running-health"],
    queryFn: loadRuntimeLongRunningHealth,
    enabled,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { health: data, isLoading, error, refetch };
}

export function useRuntimeMaintenanceStatus({
  enabled = true,
  refetchInterval = 15_000,
}: {
  enabled?: boolean;
  refetchInterval?: number | false;
} = {}) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["runtime-maintenance-status"],
    queryFn: loadRuntimeMaintenanceStatus,
    enabled,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { maintenance: data, isLoading, error, refetch };
}

export function useRunRuntimeMaintenance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: runRuntimeMaintenance,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["runtime-long-running-health"] });
      await queryClient.invalidateQueries({ queryKey: ["runtime-maintenance-status"] });
    },
  });
}

export function useRuntimeRunRecords({
  enabled = true,
  limit = 20,
  threadId,
}: {
  enabled?: boolean;
  limit?: number;
  threadId?: string;
} = {}) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["runtime-run-records", limit, threadId ?? null],
    queryFn: () => loadRuntimeRunRecords({ limit, thread_id: threadId }),
    enabled,
    refetchOnWindowFocus: false,
  });

  return { runRecords: data, isLoading, error, refetch };
}

export function useSystemGuardStatus({
  enabled = true,
  limit = 10,
  refetchInterval = 30_000,
}: {
  enabled?: boolean;
  limit?: number;
  refetchInterval?: number | false;
} = {}) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["system-guard-status", limit],
    queryFn: () => loadSystemGuardStatus(limit),
    enabled,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { systemGuard: data, isLoading, error, refetch };
}

export function useRunSystemGuardRepair() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: runSystemGuardRepair,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["system-guard-status"] });
    },
  });
}

export function useExportSystemGuardSnapshots() {
  return useMutation({
    mutationFn: exportSystemGuardSnapshots,
  });
}
