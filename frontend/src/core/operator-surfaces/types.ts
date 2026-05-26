export interface ExecutionNode {
	node_id: string
	address: string
	status: string
	capacity: number
	current_load: number
	available_capacity: number
	tags: string[]
	last_heartbeat: number
	is_healthy: boolean
	metadata?: Record<string, unknown>
}

export interface ExecutionNodesListResponse {
	nodes: ExecutionNode[]
	total: number
	healthy_count: number
}

export interface RegisterNodeRequest {
	node_id: string
	address: string
	capacity?: number
	tags?: string[]
}

export interface RouteTaskRequest {
	task_id: string
	affinity_node?: string | null
}

export interface RouteTaskResponse {
	task_id: string
	target_node_id: string
	strategy: string
	reason: string
}

export interface DispatchTaskResponse {
	dispatch_id: string
	task_id: string
	target_node_id: string | null
	status: string
	strategy: string
	reason: string
	lease_id: string
	attempts: Array<Record<string, unknown>>
	result: Record<string, unknown>
	error: string | null
	created_at: number
	updated_at: number | null
	audit: Record<string, unknown>
}

export interface TenantPolicy {
	workspace_isolation: "shared" | "namespace" | "dedicated" | string
	data_isolation: "row_level" | "schema_level" | "database_level" | string
	skill_sharing: "none" | "read_only" | "full" | string
	max_concurrent_workspaces: number
	max_agents_per_workspace: number
}

export interface Tenant {
	tenant_id: string
	display_name: string
	tier: "free" | "pro" | "enterprise" | string
	metadata: Record<string, unknown>
	is_enterprise: boolean
}

export interface TenantDetail {
	tenant: Tenant
	policy: TenantPolicy
}

export interface TenantsListResponse {
	tenants: Tenant[]
	total: number
}

export interface MultiTenantGovernanceResponse {
	tenant_count: number
	enterprise_count: number
	max_concurrent_workspaces: number
	max_agents_per_workspace: number
	audit_events: Array<{
		event: string
		tenant_id: string
		timestamp: number
		details: Record<string, unknown>
	}>
}

export interface CreateTenantRequest {
	tenant_id: string
	display_name?: string
	tier?: "free" | "pro" | "enterprise"
	metadata?: Record<string, unknown>
	policy?: TenantPolicy
}

export interface TenantLimitResponse {
	tenant_id: string
	check: string
	current_count: number
	allowed: boolean
	limit: number
}

export interface MetricSnapshot {
	name: string
	value: number
	labels: Record<string, string>
	kind: string
}

export interface MetricsJsonResponse {
	metrics: MetricSnapshot[]
	count: number
}

export type ReflectionObservationCategory =
	| "outcome"
	| "performance"
	| "error"
	| "tool_usage"
	| "model_quality"

export type ReflectionObservationSeverity = "info" | "warning" | "critical"

export type ReflectionInsightCategory =
	| "skill_gap"
	| "model_mismatch"
	| "tool_failure"
	| "prompt_quality"
	| "efficiency"

export interface ReflectionObservation {
	observation_id: string
	task_id: string
	timestamp: number
	category: ReflectionObservationCategory
	summary: string
	details: Record<string, unknown>
	severity: ReflectionObservationSeverity
}

export interface ReflectionObservationListResponse {
	observations: ReflectionObservation[]
	total: number
}

export interface RecordReflectionObservationRequest {
	task_id: string
	category: ReflectionObservationCategory
	summary: string
	details?: Record<string, unknown>
	severity: ReflectionObservationSeverity
}

export interface ReflectionInsight {
	insight_id: string
	source_observations: string[]
	category: ReflectionInsightCategory
	description: string
	suggested_action: string
	confidence: number
}

export interface ReflectionInsightListResponse {
	insights: ReflectionInsight[]
	total: number
}

export interface ReflectionSummary {
	window_size: number
	outcomes: Record<string, number>
	error_count: number
	success_rate: number
	insight_count: number
}

export type EvolutionChangeType =
	| "model_default"
	| "prompt_template"
	| "skill_config"
	| "tool_config"
	| "brain_policy"
	| "memory_policy"

export type EvolutionProposalStatus =
	| "pending"
	| "shadow_running"
	| "shadow_complete"
	| "validation_failed"
	| "awaiting_approval"
	| "approved"
	| "promoted"
	| "rejected"
	| "rolled_back"

export interface EvolutionProposal {
	proposal_id: string
	change_type: EvolutionChangeType
	title: string
	description: string
	proposed_change: Record<string, unknown>
	current_value: Record<string, unknown>
	source: string
	status: EvolutionProposalStatus
	created_at: number
	updated_at: number
	shadow_metrics: Record<string, unknown>
	validation_notes: string
	approved_by: string | null
	approved_at: number | null
	promoted_at: number | null
	rejection_reason: string
	rollback_reason: string
	tags: string[]
}

export interface EvolutionProposalListResponse {
	proposals: EvolutionProposal[]
	total: number
}

export interface EvolutionAuditEntry {
	entry_id: string
	proposal_id: string
	action: string
	timestamp: number
	actor: string
	from_status: string | null
	to_status: string | null
	notes: string
	metadata: Record<string, unknown>
}

export interface EvolutionAuditListResponse {
	entries: EvolutionAuditEntry[]
	total: number
}

export interface CreateEvolutionProposalRequest {
	change_type: EvolutionChangeType
	title: string
	description: string
	proposed_change?: Record<string, unknown>
	current_value?: Record<string, unknown>
	source?: string
	tags?: string[]
}

export interface EvolutionValidationResponse {
	proposal_id: string
	passed: boolean
	notes: string
}

export interface EvolutionShadowRunResponse {
	run_id: string
	proposal_id: string
	success: boolean
	metrics: Record<string, unknown>
	errors: string[]
	completed_at: number | null
}
