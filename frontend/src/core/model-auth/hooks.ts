import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  authorizeModelProvider,
  confirmModelProviderOAuth,
  completeModelProviderOAuth,
  loadModelProviderOAuthModels,
  loadModelAuthStatus,
  loadModelAuthTemplates,
  logoutModelProvider,
  startModelProviderOAuth,
  syncModelProvider,
  testModelProvider,
} from "./api";
import type { ProviderAuthorizeRequest } from "./types";

export function useModelAuthTemplates() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["model-auth", "templates"],
    queryFn: loadModelAuthTemplates,
    refetchOnWindowFocus: false,
  });
  return { templates: data ?? [], isLoading, error };
}

export function useModelAuthStatus() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["model-auth", "status"],
    queryFn: loadModelAuthStatus,
    refetchOnWindowFocus: false,
  });
  return { providers: data ?? {}, isLoading, error };
}

export function useAuthorizeModelProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ providerId, payload }: { providerId: string; payload: ProviderAuthorizeRequest }) =>
      authorizeModelProvider(providerId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["model-auth"] });
      void queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });
}

export function useLogoutModelProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (providerId: string) => logoutModelProvider(providerId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["model-auth"] });
    },
  });
}

export function useStartModelProviderOAuth() {
  return useMutation({
    mutationFn: ({ providerId, callbackUrl }: { providerId: string; callbackUrl?: string }) =>
      startModelProviderOAuth(providerId, { callback_url: callbackUrl, prefer_web_dialog: false }),
  });
}

export function useConfirmModelProviderOAuth() {
  return useMutation({
    mutationFn: ({ providerId, state }: { providerId: string; state: string }) =>
      confirmModelProviderOAuth(providerId, { state }),
  });
}

export function useLoadModelProviderOAuthModels() {
  return useMutation({
    mutationFn: ({ providerId, state }: { providerId: string; state?: string }) =>
      loadModelProviderOAuthModels(providerId, { state }),
  });
}

export function useCompleteModelProviderOAuth() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ providerId, model, accountLabel, setDefault = true, state }: { providerId: string; model: string; accountLabel?: string; setDefault?: boolean; state?: string }) =>
      completeModelProviderOAuth(providerId, { model, account_label: accountLabel, set_default: setDefault, state }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["model-auth"] });
      void queryClient.invalidateQueries({ queryKey: ["models"] });
      void queryClient.invalidateQueries({ queryKey: ["setup-status"] });
      void queryClient.invalidateQueries({ queryKey: ["runtime-capabilities"] });
    },
  });
}

export function useTestModelProvider() {
  return useMutation({ mutationFn: (providerId: string) => testModelProvider(providerId) });
}

export function useSyncModelProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (providerId: string) => syncModelProvider(providerId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });
}
