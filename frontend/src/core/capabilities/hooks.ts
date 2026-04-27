import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  exportCapabilityPolicies,
  importCapabilityPolicies,
  loadCapabilityAuditState,
  loadCapabilityCompatPreview,
  loadCapabilityInventory,
  loadCapabilityPolicies,
  loadCapabilityRegistry,
  loadCapabilityRuntimeState,
  migrateCapabilities,
  updateCapabilityCompatSettings,
  updateCapabilityPolicy,
  updateCapabilityState,
} from "./api";
import type { CapabilityCategory, CapabilityCompatTrustLevel, CapabilityPolicyDecision } from "./types";

export function useCapabilityInventory() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["capability-inventory"],
    queryFn: loadCapabilityInventory,
    refetchOnWindowFocus: false,
  });

  return { inventory: data, isLoading, error, refetch };
}

export function useCapabilityRuntimeState() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["capability-runtime-state"],
    queryFn: loadCapabilityRuntimeState,
    refetchOnWindowFocus: false,
  });

  return { runtimeState: data, isLoading, error, refetch };
}

export function useCapabilityAuditState() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["capability-audit-state"],
    queryFn: loadCapabilityAuditState,
    refetchOnWindowFocus: false,
  });

  return { auditState: data, isLoading, error, refetch };
}

export function useCapabilityRegistry() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["capability-registry"],
    queryFn: loadCapabilityRegistry,
    refetchOnWindowFocus: false,
  });

  return { registry: data, isLoading, error, refetch };
}

export function useCapabilityCompatPreview() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["capability-compat-preview"],
    queryFn: loadCapabilityCompatPreview,
    refetchOnWindowFocus: false,
  });

  return { compatPreview: data, isLoading, error, refetch };
}

export function useCapabilityPolicies() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["capability-policies"],
    queryFn: loadCapabilityPolicies,
    refetchOnWindowFocus: false,
  });

  return { policyState: data, isLoading, error, refetch };
}

export function useUpdateCapabilityPolicy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      capabilityId,
      decision,
      reason,
      operator,
    }: {
      capabilityId: string;
      decision: CapabilityPolicyDecision;
      reason?: string;
      operator?: string;
    }) => updateCapabilityPolicy(capabilityId, { decision, reason, operator }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["capability-policies"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-registry"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-audit-state"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-runtime-state"] });
    },
  });
}

export function useExportCapabilityPolicies() {
  return useMutation({ mutationFn: exportCapabilityPolicies });
}

export function useImportCapabilityPolicies() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: importCapabilityPolicies,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["capability-policies"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-registry"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-audit-state"] });
    },
  });
}

export function useUpdateCapabilityState() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      capabilityId,
      enabled,
    }: {
      capabilityId: string;
      enabled: boolean;
    }) => updateCapabilityState(capabilityId, enabled),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["capability-registry"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-audit-state"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-runtime-state"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-compat-preview"] });
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
      void queryClient.invalidateQueries({ queryKey: ["repo-hooks"] });
      void queryClient.invalidateQueries({ queryKey: ["mcpConfig"] });
    },
  });
}

export function useUpdateCapabilityCompatSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      enabled,
      trustLevel,
    }: {
      enabled?: boolean;
      trustLevel?: CapabilityCompatTrustLevel;
    }) =>
      updateCapabilityCompatSettings({
        enabled,
        trust_level: trustLevel,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["capability-registry"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-compat-preview"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-audit-state"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-runtime-state"] });
    },
  });
}

export function useMigrateCapabilities() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (categories?: CapabilityCategory[]) => migrateCapabilities(categories),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["capability-inventory"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-registry"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-compat-preview"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-runtime-state"] });
      void queryClient.invalidateQueries({ queryKey: ["capability-audit-state"] });
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
      void queryClient.invalidateQueries({ queryKey: ["mcpConfig"] });
      void queryClient.invalidateQueries({ queryKey: ["repo-hooks"] });
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}
