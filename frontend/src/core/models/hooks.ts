import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createModel, deleteModel, loadModels, setDefaultModel, testModelConnection, updateModel } from "./api";
import type { ModelCreateRequest, ModelUpdateRequest } from "./types";

const MODELS_STALE_MS = 5 * 60_000;
const MODELS_GC_MS = 30 * 60_000;

export function useModels({ enabled = true }: { enabled?: boolean } = {}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["models"],
    queryFn: () => loadModels(),
    enabled,
    refetchOnWindowFocus: false,
    staleTime: MODELS_STALE_MS,
    gcTime: MODELS_GC_MS,
  });
  return { models: data ?? [], isLoading, error };
}


export function useDeleteModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (modelName: string) => deleteModel(modelName),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });
}

export function useCreateModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ModelCreateRequest) => createModel(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });
}

export function useUpdateModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ modelName, payload }: { modelName: string; payload: ModelUpdateRequest }) =>
      updateModel(modelName, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });
}

export function useSetDefaultModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (modelName: string) => setDefaultModel(modelName),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["models"] }),
  });
}

export function useTestModelConnection() {
  return useMutation({ mutationFn: (modelName: string) => testModelConnection(modelName) });
}
