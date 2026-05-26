import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteChannelConfig,
  loadChannelIdentity,
  loadChannelsStatus,
  logoutChannel,
  restartChannel,
  setChannelEnabled,
  updateChannelConfig,
} from "./api";

export function useChannelsStatus({
  enabled = true,
}: {
  enabled?: boolean;
} = {}) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["channels-status"],
    queryFn: loadChannelsStatus,
    enabled,
    refetchOnWindowFocus: false,
  });

  return { status: data, isLoading, error, refetch };
}

export function useRestartChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: restartChannel,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["channels-status"] });
    },
  });
}

export function useUpdateChannelConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      name,
      config,
    }: {
      name: string;
      config: Record<string, unknown>;
    }) => updateChannelConfig(name, { config }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["channels-status"] });
    },
  });
}

export function useSetChannelEnabled() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      setChannelEnabled(name, enabled),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["channels-status"] });
    },
  });
}
export function useDeleteChannelConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => deleteChannelConfig(name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["channels-status"] });
    },
  });
}


export function useLogoutChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => logoutChannel(name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["channels-status"] });
    },
  });
}

export function useChannelIdentity(name: string | null, { enabled = true }: { enabled?: boolean } = {}) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["channel-identity", name],
    queryFn: () => loadChannelIdentity(name ?? ""),
    enabled: enabled && Boolean(name),
    refetchOnWindowFocus: false,
  });
  return { identity: data, isLoading, error, refetch };
}
