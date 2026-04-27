import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  compactQueryEngineSession,
  executeQueryEngineTurn,
  loadQueryEngineSession,
  refreshQueryEngineSessionProfile,
} from "./api";
import type {
  QuerySessionCompactRequest,
  QuerySessionRefreshRequest,
  QueryTurnExecutionRequest,
} from "./types";

export function useQueryEngineSession(
  sessionId: string | null,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["query-engine-session", sessionId],
    queryFn: () => loadQueryEngineSession(sessionId!),
    enabled: enabled && sessionId != null,
    refetchOnWindowFocus: false,
  });

  return { session: data, isLoading, error, refetch };
}

export function useExecuteQueryEngineTurn(sessionId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: QueryTurnExecutionRequest) =>
      executeQueryEngineTurn(sessionId!, payload),
    onSuccess: (session) => {
      queryClient.setQueryData(["query-engine-session", sessionId], session);
    },
  });
}

export function useCompactQueryEngineSession(sessionId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: QuerySessionCompactRequest) =>
      compactQueryEngineSession(sessionId!, payload),
    onSuccess: (session) => {
      queryClient.setQueryData(["query-engine-session", sessionId], session);
    },
  });
}

export function useRefreshQueryEngineSessionProfile(sessionId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: QuerySessionRefreshRequest) =>
      refreshQueryEngineSessionProfile(sessionId!, payload),
    onSuccess: (session) => {
      queryClient.setQueryData(["query-engine-session", sessionId], session);
    },
  });
}