import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  loadEvolutionConfig,
  loadEvolutionRecords,
  loadHealthReports,
  loadQualityMetrics,
  updateEvolutionConfig,
  registerEvolutionSkill,
} from "./api";
import type { EvolutionConfig } from "./type";

export function useEvolutionConfig() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["evolution-config"],
    queryFn: () => loadEvolutionConfig(),
  });
  return { config: data, isLoading, error };
}

export function useUpdateEvolutionConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: EvolutionConfig) => updateEvolutionConfig(config),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["evolution-config"] });
    },
  });
}

export function useEvolutionRecords(limit = 50) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["evolution-records", limit],
    queryFn: () => loadEvolutionRecords(limit),
  });
  return { records: data ?? [], isLoading, error };
}

export function useQualityMetrics() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["quality-metrics"],
    queryFn: () => loadQualityMetrics(),
  });
  return { metrics: data ?? [], isLoading, error };
}

export function useHealthReports() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["health-reports"],
    queryFn: () => loadHealthReports(),
  });
  return { reports: data ?? [], isLoading, error };
}


export function useRegisterEvolutionSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (skillName: string) => registerEvolutionSkill(skillName),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["evolution-records"] });
      void queryClient.invalidateQueries({ queryKey: ["health-reports"] });
      void queryClient.invalidateQueries({ queryKey: ["quality-metrics"] });
    },
  });
}
