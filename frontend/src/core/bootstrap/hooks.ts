import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  generateBootstrapGuide,
  installBootstrapModel,
  loadBootstrapStatus,
} from "./api";

export function useBootstrapStatus({ enabled = true }: { enabled?: boolean } = {}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["bootstrap-status"],
    queryFn: () => loadBootstrapStatus(),
    enabled,
    refetchOnWindowFocus: false,
  });
  return { bootstrap: data, isLoading, error };
}

export function useInstallBootstrapModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: installBootstrapModel,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["bootstrap-status"] });
    },
  });
}

export function useGenerateBootstrapGuide() {
  return useMutation({
    mutationFn: generateBootstrapGuide,
  });
}
