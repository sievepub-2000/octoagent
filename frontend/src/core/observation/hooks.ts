import { useQuery } from "@tanstack/react-query";

import { loadTaskObservationTimeline } from "./api";

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