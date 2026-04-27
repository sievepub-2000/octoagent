import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
	approveEvolutionProposal,
	checkTenantWorkspaceLimit,
	createEvolutionProposal,
	createTenant,
	deriveReflectionInsights,
	deleteTenant,
	deregisterExecutionNode,
	loadEvolutionAuditTrail,
	loadEvolutionProposals,
	loadExecutionNodes,
	loadMetricsJson,
	loadReflectionInsights,
	loadReflectionObservations,
	loadReflectionSummary,
	loadTenantGovernance,
	loadTenants,
	promoteEvolutionProposal,
	recordReflectionObservation,
	registerExecutionNode,
	rejectEvolutionProposal,
	rollbackEvolutionProposal,
	routeExecutionTask,
	shadowRunEvolutionProposal,
	validateEvolutionProposal,
	updateTenantPolicy,
} from "./api"
import type { TenantPolicy } from "./types"

export function useExecutionNodes(refetchInterval: number | false = 15000) {
	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["operator-execution-nodes"],
		queryFn: loadExecutionNodes,
		refetchOnWindowFocus: false,
		refetchInterval,
	})

	return { data, isLoading, error, refetch }
}

export function useRegisterExecutionNode() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: registerExecutionNode,
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["operator-execution-nodes"] })
		},
	})
}

export function useDeregisterExecutionNode() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: deregisterExecutionNode,
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["operator-execution-nodes"] })
		},
	})
}

export function useRouteExecutionTask() {
	return useMutation({ mutationFn: routeExecutionTask })
}

export function useTenants(refetchInterval: number | false = 15000) {
	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["operator-tenants"],
		queryFn: loadTenants,
		refetchOnWindowFocus: false,
		refetchInterval,
	})

	return { data, isLoading, error, refetch }
}

export function useTenantGovernance(refetchInterval: number | false = 15000) {
	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["operator-tenant-governance"],
		queryFn: loadTenantGovernance,
		refetchOnWindowFocus: false,
		refetchInterval,
	})

	return { data, isLoading, error, refetch }
}

export function useCreateTenant() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: createTenant,
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["operator-tenants"] })
			void queryClient.invalidateQueries({ queryKey: ["operator-tenant-governance"] })
		},
	})
}

export function useUpdateTenantPolicy() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: ({ tenantId, policy }: { tenantId: string; policy: TenantPolicy }) =>
			updateTenantPolicy(tenantId, policy),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["operator-tenants"] })
			void queryClient.invalidateQueries({ queryKey: ["operator-tenant-governance"] })
		},
	})
}

export function useDeleteTenant() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: deleteTenant,
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["operator-tenants"] })
			void queryClient.invalidateQueries({ queryKey: ["operator-tenant-governance"] })
		},
	})
}

export function useCheckTenantWorkspaceLimit() {
	return useMutation({
		mutationFn: ({ tenantId, currentCount }: { tenantId: string; currentCount: number }) =>
			checkTenantWorkspaceLimit(tenantId, currentCount),
	})
}

export function useMetricsJson(refetchInterval: number | false = 15000) {
	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["operator-metrics-json"],
		queryFn: loadMetricsJson,
		refetchOnWindowFocus: false,
		refetchInterval,
	})

	return { data, isLoading, error, refetch }
}

export function useReflectionSummary(window = 20) {
	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["operator-reflection-summary", window],
		queryFn: () => loadReflectionSummary(window),
		refetchOnWindowFocus: false,
		refetchInterval: 15000,
	})

	return { data, isLoading, error, refetch }
}

export function useReflectionObservations(limit = 8) {
	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["operator-reflection-observations", limit],
		queryFn: () => loadReflectionObservations(limit),
		refetchOnWindowFocus: false,
		refetchInterval: 15000,
	})

	return { data, isLoading, error, refetch }
}

export function useRecordReflectionObservation() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: recordReflectionObservation,
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["operator-reflection-observations"] })
			void queryClient.invalidateQueries({ queryKey: ["operator-reflection-summary"] })
		},
	})
}

export function useReflectionInsights() {
	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["operator-reflection-insights"],
		queryFn: loadReflectionInsights,
		refetchOnWindowFocus: false,
		refetchInterval: 15000,
	})

	return { data, isLoading, error, refetch }
}

export function useDeriveReflectionInsights() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: deriveReflectionInsights,
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["operator-reflection-insights"] })
			void queryClient.invalidateQueries({ queryKey: ["operator-reflection-summary"] })
		},
	})
}

export function useEvolutionProposals(limit = 8) {
	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["operator-evolution-proposals", limit],
		queryFn: () => loadEvolutionProposals(limit),
		refetchOnWindowFocus: false,
		refetchInterval: 15000,
	})

	return { data, isLoading, error, refetch }
}

export function useEvolutionAuditTrail(limit = 8) {
	const { data, isLoading, error, refetch } = useQuery({
		queryKey: ["operator-evolution-audit", limit],
		queryFn: () => loadEvolutionAuditTrail(limit),
		refetchOnWindowFocus: false,
		refetchInterval: 15000,
	})

	return { data, isLoading, error, refetch }
}

function invalidateEvolutionQueries(queryClient: ReturnType<typeof useQueryClient>) {
	void queryClient.invalidateQueries({ queryKey: ["operator-evolution-proposals"] })
}

export function useCreateEvolutionProposal() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: createEvolutionProposal,
		onSuccess: () => invalidateEvolutionQueries(queryClient),
	})
}

export function useShadowRunEvolutionProposal() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: shadowRunEvolutionProposal,
		onSuccess: () => invalidateEvolutionQueries(queryClient),
	})
}

export function useValidateEvolutionProposal() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: validateEvolutionProposal,
		onSuccess: () => invalidateEvolutionQueries(queryClient),
	})
}

export function useApproveEvolutionProposal() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: approveEvolutionProposal,
		onSuccess: () => invalidateEvolutionQueries(queryClient),
	})
}

export function useRejectEvolutionProposal() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: rejectEvolutionProposal,
		onSuccess: () => invalidateEvolutionQueries(queryClient),
	})
}

export function usePromoteEvolutionProposal() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: promoteEvolutionProposal,
		onSuccess: () => invalidateEvolutionQueries(queryClient),
	})
}

export function useRollbackEvolutionProposal() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: rollbackEvolutionProposal,
		onSuccess: () => invalidateEvolutionQueries(queryClient),
	})
}
