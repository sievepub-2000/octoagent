import { useMutation, useQuery } from "@tanstack/react-query";

import {
  applySetup,
  browseDirectory,
  createDirectory,
  loadSetupStatus,
  updateDefaultModel,
  validateWorkspace,
} from "./api";

export function useSetupStatus({
  enabled = true,
}: {
  enabled?: boolean;
} = {}) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["setup-status"],
    queryFn: loadSetupStatus,
    enabled,
    refetchOnWindowFocus: false,
  });

  return { status: data, isLoading, error, refetch };
}

export function useValidateWorkspace() {
  return useMutation({
    mutationFn: validateWorkspace,
  });
}

export function useApplySetup() {
  return useMutation({
    mutationFn: applySetup,
  });
}

export function useUpdateDefaultModel() {
  return useMutation({
    mutationFn: updateDefaultModel,
  });
}

export function useBrowseDirectory() {
  return useMutation({
    mutationFn: browseDirectory,
  });
}

export function useCreateDirectory() {
  return useMutation({
    mutationFn: createDirectory,
  });
}
