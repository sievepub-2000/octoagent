import { deleteJSON, getJSON, postJSON, putJSON } from "@/core/api/http"

import type {
	CreateEvolutionProposalRequest,
	CreateTenantRequest,
	EvolutionAuditListResponse,
	EvolutionProposal,
	EvolutionProposalListResponse,
	EvolutionShadowRunResponse,
	EvolutionValidationResponse,
	DispatchTaskResponse,
	ExecutionNode,
	ExecutionNodesListResponse,
	MetricsJsonResponse,
	RecordReflectionObservationRequest,
	ReflectionInsightListResponse,
	ReflectionObservation,
	ReflectionObservationListResponse,
	ReflectionSummary,
	RegisterNodeRequest,
	RouteTaskRequest,
	RouteTaskResponse,
	TenantDetail,
	TenantLimitResponse,
	TenantPolicy,
	TenantsListResponse,
	MultiTenantGovernanceResponse,
} from "./types"

export function loadExecutionNodes() {
	return getJSON<ExecutionNodesListResponse>("/api/execution-nodes")
}

export function loadExecutionDispatches() {
	return getJSON<DispatchTaskResponse[]>("/api/execution-nodes/history/dispatches")
}

export function registerExecutionNode(payload: RegisterNodeRequest) {
	return postJSON<ExecutionNode>("/api/execution-nodes", payload)
}

export function deregisterExecutionNode(nodeId: string) {
	return deleteJSON<void>(`/api/execution-nodes/${nodeId}`, {
		headers: { "X-OctoAgent-Confirmation": "CONFIRM REMOVE NODE" },
	})
}

export function routeExecutionTask(payload: RouteTaskRequest) {
	return postJSON<RouteTaskResponse>("/api/execution-nodes/route", payload)
}

export function loadTenants() {
	return getJSON<TenantsListResponse>("/api/tenants")
}

export function loadTenantGovernance() {
	return getJSON<MultiTenantGovernanceResponse>("/api/tenants/governance")
}

export function createTenant(payload: CreateTenantRequest) {
	return postJSON<TenantDetail>("/api/tenants", payload)
}

export function updateTenantPolicy(tenantId: string, policy: TenantPolicy) {
	return putJSON<TenantDetail>(`/api/tenants/${tenantId}/policy`, policy)
}

export function deleteTenant(tenantId: string) {
	return deleteJSON<void>(`/api/tenants/${tenantId}`, {
		headers: { "X-OctoAgent-Confirmation": "CONFIRM DELETE TENANT" },
	})
}

export function checkTenantWorkspaceLimit(tenantId: string, currentCount: number) {
	return getJSON<TenantLimitResponse>(`/api/tenants/${tenantId}/limits/workspaces`, {
		current_count: currentCount,
	})
}

export function loadMetricsJson() {
	return getJSON<MetricsJsonResponse>("/api/metrics/json")
}

export function loadReflectionSummary(window = 20) {
	return getJSON<ReflectionSummary>("/api/reflection/summary", { window })
}

export function loadReflectionObservations(limit = 8) {
	return getJSON<ReflectionObservationListResponse>("/api/reflection/observations", { limit })
}

export function recordReflectionObservation(payload: RecordReflectionObservationRequest) {
	return postJSON<ReflectionObservation>("/api/reflection/observations", payload)
}

export function loadReflectionInsights() {
	return getJSON<ReflectionInsightListResponse>("/api/reflection/insights")
}

export function deriveReflectionInsights() {
	return postJSON<ReflectionInsightListResponse>("/api/reflection/insights/derive", {})
}

export function loadEvolutionProposals(limit = 8) {
	return getJSON<EvolutionProposalListResponse>("/api/evolution/proposals", { limit })
}

export function loadEvolutionAuditTrail(limit = 8) {
	return getJSON<EvolutionAuditListResponse>("/api/evolution/audit", { limit })
}

export function createEvolutionProposal(payload: CreateEvolutionProposalRequest) {
	return postJSON<EvolutionProposal>("/api/evolution/proposals", payload)
}

export function shadowRunEvolutionProposal(proposalId: string) {
	return postJSON<EvolutionShadowRunResponse>(`/api/evolution/proposals/${proposalId}/shadow-run`, {})
}

export function validateEvolutionProposal(proposalId: string) {
	return postJSON<EvolutionValidationResponse>(`/api/evolution/proposals/${proposalId}/validate`, {})
}

export function approveEvolutionProposal(proposalId: string) {
	return postJSON<EvolutionProposal>(`/api/evolution/proposals/${proposalId}/approve`, {
		approved_by: "webui-operator",
	})
}

export function rejectEvolutionProposal(proposalId: string) {
	return postJSON<EvolutionProposal>(`/api/evolution/proposals/${proposalId}/reject`, {
		reason: "Rejected from WebUI operator panel",
		rejected_by: "webui-operator",
	})
}

export function promoteEvolutionProposal(proposalId: string) {
	return postJSON<EvolutionProposal>(`/api/evolution/proposals/${proposalId}/promote`, {})
}

export function rollbackEvolutionProposal(proposalId: string) {
	return postJSON<EvolutionProposal>(`/api/evolution/proposals/${proposalId}/rollback`, {
		reason: "Rollback requested from WebUI operator panel",
	})
}
