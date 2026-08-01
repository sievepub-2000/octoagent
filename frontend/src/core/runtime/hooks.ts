import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  loadRuntimeCapabilities,
  loadRuntimeLongRunningHealth,
  loadRuntimeMaintenanceStatus,
  runRuntimeMaintenance,
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
