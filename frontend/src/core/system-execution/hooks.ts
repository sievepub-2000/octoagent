import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createSystemExecutionSession,
  executeSystemCliCommand,
  executeWorkspaceCliCommand,
  loadRuntimeDoctor,
  loadSystemExecutionConfig,
  loadSystemExecutionPermissionPolicy,
  loadSystemExecutionAudit,
  loadSystemExecutionCapabilities,
  loadSystemExecutionSession,
  loadSystemExecutionSessions,
  loadSystemExecutionSnapshot,
  planSystemExecution,
  updateSystemExecutionConfig,
} from "./api";

export function useSystemExecutionCapabilities({
  enabled = true,
}: {
  enabled?: boolean;
} = {}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["system-execution-capabilities"],
    queryFn: loadSystemExecutionCapabilities,
    enabled,
    refetchOnWindowFocus: false,
  });

  return { capability: data, isLoading, error };
}

export function usePlanSystemExecution() {
  return useMutation({
    mutationFn: planSystemExecution,
  });
}

export function useSystemExecutionPermissionPolicy({
  enabled = true,
}: {
  enabled?: boolean;
} = {}) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["system-execution-permission-policy"],
    queryFn: loadSystemExecutionPermissionPolicy,
    enabled,
    refetchOnWindowFocus: false,
  });

  return { policy: data, isLoading, error, refetch };
}

export function useCreateSystemExecutionSession() {
  return useMutation({
    mutationFn: createSystemExecutionSession,
  });
}

export function useExecuteWorkspaceCliCommand() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: executeWorkspaceCliCommand,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["system-execution-sessions"] });
    },
  });
}

export function useExecuteSystemCliCommand() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: executeSystemCliCommand,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["system-execution-sessions"] });
    },
  });
}

export function useSystemExecutionConfig({
  enabled = true,
}: {
  enabled?: boolean;
} = {}) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["system-execution-config"],
    queryFn: loadSystemExecutionConfig,
    enabled,
    refetchOnWindowFocus: false,
  });

  return { config: data, isLoading, error, refetch };
}

export function useUpdateSystemExecutionConfig() {
  return useMutation({
    mutationFn: updateSystemExecutionConfig,
  });
}

export function useSystemExecutionSession(
  sessionId: string | null,
  {
    enabled = true,
    refetchInterval = false,
  }: { enabled?: boolean; refetchInterval?: number | false } = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["system-execution-session", sessionId],
    queryFn: () => loadSystemExecutionSession(sessionId!),
    enabled: enabled && sessionId != null,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { session: data, isLoading, error, refetch };
}

export function useSystemExecutionSessions(
  {
    limit = 20,
    relatedTaskId,
    target,
  }: {
    limit?: number;
    relatedTaskId?: string;
    target?: string;
  } = {},
  {
    enabled = true,
    refetchInterval = false,
  }: { enabled?: boolean; refetchInterval?: number | false } = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["system-execution-sessions", { limit, relatedTaskId, target }],
    queryFn: () => loadSystemExecutionSessions({ limit, relatedTaskId, target }),
    enabled,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { sessions: data?.sessions ?? [], isLoading, error, refetch };
}

export function useSystemExecutionSnapshot(
  sessionId: string | null,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["system-execution-snapshot", sessionId],
    queryFn: () => loadSystemExecutionSnapshot(sessionId!),
    enabled: enabled && sessionId != null,
    refetchOnWindowFocus: false,
  });

  return { snapshot: data, isLoading, error, refetch };
}

export function useSystemExecutionAudit(
  sessionId: string | null,
  {
    enabled = true,
    refetchInterval = false,
  }: { enabled?: boolean; refetchInterval?: number | false } = {},
) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["system-execution-audit", sessionId],
    queryFn: () => loadSystemExecutionAudit(sessionId!),
    enabled: enabled && sessionId != null,
    refetchOnWindowFocus: false,
    refetchInterval,
  });

  return { audit: data, isLoading, error, refetch };
}

export function useRuntimeDoctor({
  enabled = true,
}: {
  enabled?: boolean;
} = {}) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["runtime-doctor"],
    queryFn: loadRuntimeDoctor,
    enabled,
    refetchOnWindowFocus: false,
  });

  return { doctor: data, isLoading, error, refetch };
}
