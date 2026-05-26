import { useQuery } from "@tanstack/react-query";

import { loadTaskObservationTimeline, loadToolTrace } from "./api";

type ObservationHookOptions = {
  enabled?: boolean;
  refetchInterval?: number | false;
};

export function useTaskObservationTimeline(
  taskId: string | null,
  { enabled = true, refetchInterval = false }: ObservationHookOptions = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["task-observation-timeline", taskId],
    queryFn: () => loadTaskObservationTimeline(taskId!),
    enabled: enabled && taskId != null,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { events: data?.events ?? [], isLoading, error, refetch };
}

export function useToolTrace(
  { limit = 80, event = null, enabled = true, refetchInterval = false }: ObservationHookOptions & { limit?: number; event?: string | null } = {},
) {
  const trimmedEvent = event?.trim();
  const normalizedEvent = trimmedEvent && trimmedEvent.length > 0 ? trimmedEvent : null;
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["tool-trace", limit, normalizedEvent],
    queryFn: () => loadToolTrace({ limit, event: normalizedEvent }),
    enabled,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return {
    entries: data?.entries ?? [],
    response: data,
    isLoading,
    isFetching,
    error,
    refetch,
  };
}