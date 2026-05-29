import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createAgent,
  deleteAgent,
  getAgentTemplate,
  getAgent,
  listAgentTemplates,
  listAgents,
  updateAgent,
} from "./api";
import type { CreateAgentRequest, UpdateAgentRequest } from "./types";

const AGENTS_STALE_MS = 5 * 60_000;
const AGENTS_GC_MS = 30 * 60_000;

export function useAgents() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["agents"],
    queryFn: () => listAgents(),
    refetchOnWindowFocus: false,
    staleTime: AGENTS_STALE_MS,
    gcTime: AGENTS_GC_MS,
  });
  return { agents: data ?? [], isLoading, error };
}

export function useAgent(name: string | null | undefined) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["agents", name],
    queryFn: () => getAgent(name!),
    enabled: !!name,
    refetchOnWindowFocus: false,
    staleTime: AGENTS_STALE_MS,
    gcTime: AGENTS_GC_MS,
  });
  return { agent: data ?? null, isLoading, error };
}

export function useCreateAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateAgentRequest) => createAgent(request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function useAgentTemplates() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["agent-templates"],
    queryFn: () => listAgentTemplates(),
    refetchOnWindowFocus: false,
    staleTime: AGENTS_STALE_MS,
    gcTime: AGENTS_GC_MS,
  });
  return { templates: data ?? [], isLoading, error };
}

export function useAgentTemplate(skillName: string | null, templateId: string | null) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["agent-template", skillName, templateId],
    queryFn: () => getAgentTemplate(skillName!, templateId!),
    enabled: !!skillName && !!templateId,
    refetchOnWindowFocus: false,
    staleTime: AGENTS_STALE_MS,
    gcTime: AGENTS_GC_MS,
  });
  return { template: data ?? null, isLoading, error };
}

export function useUpdateAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      name,
      request,
    }: {
      name: string;
      request: UpdateAgentRequest;
    }) => updateAgent(name, request),
    onSuccess: (_data, { name }) => {
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
      void queryClient.invalidateQueries({ queryKey: ["agents", name] });
    },
  });
}

export function useDeleteAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => deleteAgent(name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}
