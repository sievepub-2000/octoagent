import { useQuery } from "@tanstack/react-query";

import { buildBrainPlan } from "./api";
import type { BrainPlanRequest } from "./types";

export function useBrainPlan(
  payload: BrainPlanRequest | null,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const queryEnabled = enabled && payload != null && payload.user_goal.trim().length > 0;

  const { data, isLoading, error } = useQuery({
    queryKey: ["brain-plan", payload],
    queryFn: () => buildBrainPlan(payload!),
    enabled: queryEnabled,
    refetchOnWindowFocus: false,
  });

  return {
    brainPlan: data,
    isLoading,
    error,
  };
}
