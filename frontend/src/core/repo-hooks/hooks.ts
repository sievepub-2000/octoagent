import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { loadRepoHooks, updateRepoHook } from "./api";

export function useRepoHooks() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["repo-hooks"],
    queryFn: loadRepoHooks,
    refetchOnWindowFocus: false,
  });

  return { hooks: data?.hooks ?? [], isLoading, error, refetch };
}

export function useUpdateRepoHook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ hookName, enabled }: { hookName: string; enabled: boolean }) =>
      updateRepoHook(hookName, enabled),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["repo-hooks"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-inventory"] });
      void queryClient.invalidateQueries({ queryKey: ["harness"] });
    },
  });
}
