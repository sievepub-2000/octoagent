"use client"

import {
	ActivityIcon,
	BrainCircuitIcon,
	CheckCircle2Icon,
	GaugeIcon,
	GitBranchPlusIcon,
	NetworkIcon,
	RefreshCcwIcon,
	RouteIcon,
	Trash2Icon,
	TrendingUpIcon,
	UsersIcon,
} from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { useCapabilityPolicies } from "@/core/capabilities/hooks"
import {
	useApproveEvolutionProposal,
	useCheckTenantWorkspaceLimit,
	useCreateEvolutionProposal,
	useCreateTenant,
	useDeleteTenant,
	useDeregisterExecutionNode,
	useDeriveReflectionInsights,
	useEvolutionAuditTrail,
	useEvolutionProposals,
	useExecutionDispatches,
	useExecutionNodes,
	useMetricsJson,
	usePromoteEvolutionProposal,
	useRecordReflectionObservation,
	useReflectionInsights,
	useReflectionObservations,
	useReflectionSummary,
	useRegisterExecutionNode,
	useRejectEvolutionProposal,
	useRollbackEvolutionProposal,
	useRouteExecutionTask,
	useShadowRunEvolutionProposal,
	useTenantGovernance,
	useTenants,
	useUpdateTenantPolicy,
	useValidateEvolutionProposal,
} from "@/core/operator-surfaces/hooks"
import type {
	CreateEvolutionProposalRequest,
	EvolutionChangeType,
	EvolutionProposal,
	EvolutionProposalStatus,
	ReflectionObservationCategory,
	ReflectionObservationSeverity,
	TenantPolicy,
} from "@/core/operator-surfaces/types"

import { SettingsSection } from "./settings-section"

function formatTimestamp(value: number | null | undefined) {
	if (!value) {
		return "-"
	}

	return new Date(value * 1000).toLocaleString()
}

function statusBadgeVariant(status: EvolutionProposalStatus | string) {
	if (status === "validation_failed" || status === "rejected" || status === "rolled_back") {
		return "destructive" as const
	}
	if (status === "approved" || status === "promoted") {
		return "default" as const
	}
	return "outline" as const
}

function parseJsonObject(raw: string, label: string) {
	const trimmed = raw.trim()
	if (!trimmed) {
		return {}
	}

	const parsed = JSON.parse(trimmed)
	if (parsed == null || Array.isArray(parsed) || typeof parsed !== "object") {
		throw new Error(`${label} must be a JSON object`)
	}
	return parsed as Record<string, unknown>
}

function splitTags(raw: string) {
	return raw
		.split(",")
		.map((item) => item.trim())
		.filter(Boolean)
}

function testIdSafe(value: string) {
	return value.replace(/[^A-Za-z0-9_-]/g, "-")
}

function ProposalActionBar({ proposal }: { proposal: EvolutionProposal }) {
	const shadowRun = useShadowRunEvolutionProposal()
	const validate = useValidateEvolutionProposal()
	const approve = useApproveEvolutionProposal()
	const reject = useRejectEvolutionProposal()
	const promote = usePromoteEvolutionProposal()
	const rollback = useRollbackEvolutionProposal()

	async function runAction(action: () => Promise<unknown>, successMessage: string) {
		try {
			await action()
			toast.success(successMessage)
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Operator action failed")
		}
	}

	return (
		<div className="flex flex-wrap gap-2">
			{(proposal.status === "pending" || proposal.status === "shadow_complete") && (
				<Button
					size="sm"
					variant="outline"
					onClick={() => void runAction(() => shadowRun.mutateAsync(proposal.proposal_id), "Shadow run started")}
					disabled={shadowRun.isPending}
				>
					Shadow run
				</Button>
			)}
			{proposal.status === "shadow_complete" && (
				<Button
					size="sm"
					variant="outline"
					onClick={() => void runAction(() => validate.mutateAsync(proposal.proposal_id), "Validation complete")}
					disabled={validate.isPending}
				>
					Validate
				</Button>
			)}
			{proposal.status === "awaiting_approval" && (
				<>
					<Button
						size="sm"
						onClick={() => void runAction(() => approve.mutateAsync(proposal.proposal_id), "Proposal approved")}
						disabled={approve.isPending}
					>
						Approve
					</Button>
					<Button
						size="sm"
						variant="outline"
						onClick={() => void runAction(() => reject.mutateAsync(proposal.proposal_id), "Proposal rejected")}
						disabled={reject.isPending}
					>
						Reject
					</Button>
				</>
			)}
			{proposal.status === "approved" && (
				<Button
					size="sm"
					onClick={() => void runAction(() => promote.mutateAsync(proposal.proposal_id), "Proposal promoted")}
					disabled={promote.isPending}
				>
					Promote
				</Button>
			)}
			{proposal.status === "promoted" && (
				<Button
					size="sm"
					variant="outline"
					onClick={() => void runAction(() => rollback.mutateAsync(proposal.proposal_id), "Proposal rolled back")}
					disabled={rollback.isPending}
				>
					Rollback
				</Button>
			)}
		</div>
	)
}

export function OperatorSurfacesSection() {
	const { data: executionNodes, isLoading: executionLoading, error: executionError, refetch: refetchNodes } =
		useExecutionNodes()
	const { data: executionDispatches, error: dispatchesError, refetch: refetchDispatches } = useExecutionDispatches()
	const { policyState } = useCapabilityPolicies()
	const { data: metricsData, isLoading: metricsLoading, error: metricsError, refetch: refetchMetrics } = useMetricsJson()
	const { data: reflectionSummary, error: summaryError, refetch: refetchSummary } = useReflectionSummary()
	const {
		data: reflectionObservations,
		isLoading: observationsLoading,
		error: observationsError,
		refetch: refetchObservations,
	} = useReflectionObservations()
	const { data: reflectionInsights, isLoading: insightsLoading, error: insightsError, refetch: refetchInsights } =
		useReflectionInsights()
	const { data: evolutionProposals, isLoading: proposalsLoading, error: proposalsError, refetch: refetchProposals } =
		useEvolutionProposals()
	const { data: evolutionAudit, isLoading: auditLoading, error: auditError, refetch: refetchAudit } = useEvolutionAuditTrail()

	const registerNode = useRegisterExecutionNode()
	const deregisterNode = useDeregisterExecutionNode()
	const routeTask = useRouteExecutionTask()
	const { data: tenantsData, error: tenantsError, refetch: refetchTenants } = useTenants()
	const { data: tenantGovernance, refetch: refetchTenantGovernance } = useTenantGovernance()
	const createTenant = useCreateTenant()
	const updateTenantPolicy = useUpdateTenantPolicy()
	const deleteTenant = useDeleteTenant()
	const checkTenantLimit = useCheckTenantWorkspaceLimit()
	const recordObservation = useRecordReflectionObservation()
	const deriveInsights = useDeriveReflectionInsights()
	const createProposal = useCreateEvolutionProposal()

	const [nodeId, setNodeId] = useState("")
	const [nodeAddress, setNodeAddress] = useState("http://127.0.0.1:19832")
	const [nodeCapacity, setNodeCapacity] = useState("10")
	const [nodeTags, setNodeTags] = useState("")
	const [routeTaskId, setRouteTaskId] = useState("")
	const [routeAffinityNode, setRouteAffinityNode] = useState("")
	const [tenantId, setTenantId] = useState("")
	const [tenantName, setTenantName] = useState("")
	const [tenantTier, setTenantTier] = useState<"free" | "pro" | "enterprise">("free")
	const [tenantWorkspaceLimit, setTenantWorkspaceLimit] = useState("10")
	const [tenantAgentLimit, setTenantAgentLimit] = useState("20")
	const [tenantLimitProbe, setTenantLimitProbe] = useState("0")
	const [tenantLimitProbeId, setTenantLimitProbeId] = useState("default")

	const [observationTaskId, setObservationTaskId] = useState("")
	const [observationCategory, setObservationCategory] = useState<ReflectionObservationCategory>("outcome")
	const [observationSeverity, setObservationSeverity] = useState<ReflectionObservationSeverity>("info")
	const [observationSummary, setObservationSummary] = useState("")
	const [observationDetails, setObservationDetails] = useState("{}")

	const [proposalTitle, setProposalTitle] = useState("")
	const [proposalType, setProposalType] = useState<EvolutionChangeType>("prompt_template")
	const [proposalDescription, setProposalDescription] = useState("")
	const [proposalTags, setProposalTags] = useState("")
	const [proposalCurrentValue, setProposalCurrentValue] = useState("{}")
	const [proposalNextValue, setProposalNextValue] = useState("{}")

	const routeDecision = routeTask.data
	const metrics = metricsData?.metrics ?? []
	const topMetrics = [...metrics].sort((left, right) => left.name.localeCompare(right.name)).slice(0, 12)
	const proposals = evolutionProposals?.proposals ?? []
	const auditEntries = evolutionAudit?.entries ?? []
	const dispatches = executionDispatches ?? []
	const remoteWorkers = executionNodes?.nodes.filter((node) => node.node_id !== "local") ?? []
	const governanceCards = [
		{
			label: "Runtime",
			value: metricsError ? "unavailable" : `${metricsData?.count ?? 0} metrics`,
			detail: metricsError ? "metrics API error" : "live metrics snapshot",
		},
		{
			label: "Distributed",
			value: `${executionNodes?.healthy_count ?? 0}/${executionNodes?.total ?? 0} healthy`,
			detail: remoteWorkers.length ? `${remoteWorkers.length} independent worker(s)` : "local fallback only",
		},
		{
			label: "Tenant",
			value: `${tenantGovernance?.tenant_count ?? tenantsData?.total ?? 0} tenants`,
			detail: `${tenantGovernance?.audit_events.length ?? 0} recent audit event(s)`,
		},
		{
			label: "Policy",
			value: `${policyState?.policies.length ?? 0} overrides`,
			detail: `${policyState?.audit_events.length ?? 0} policy audit event(s)`,
		},
	]
	const proposalCounts = proposals.reduce<Record<string, number>>((accumulator, proposal) => {
		accumulator[proposal.status] = (accumulator[proposal.status] ?? 0) + 1
		return accumulator
	}, {})

	function downloadOperatorExport(path: string) {
		if (typeof window === "undefined") {
			return
		}
		window.open(path, "_blank", "noopener,noreferrer")
	}

	async function handleRegisterNode() {
		try {
			await registerNode.mutateAsync({
				node_id: nodeId.trim(),
				address: nodeAddress.trim(),
				capacity: Number.parseInt(nodeCapacity, 10) || 10,
				tags: splitTags(nodeTags),
			})
			toast.success("Execution node registered")
			setNodeId("")
			setNodeTags("")
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Failed to register node")
		}
	}

	async function handleRouteTask() {
		try {
			await routeTask.mutateAsync({
				task_id: routeTaskId.trim(),
				affinity_node: routeAffinityNode.trim() || null,
			})
			toast.success("Routing decision refreshed")
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Failed to route task")
		}
	}

	function tenantPolicy(): TenantPolicy {
		return {
			workspace_isolation: tenantTier === "enterprise" ? "dedicated" : "namespace",
			data_isolation: tenantTier === "enterprise" ? "database_level" : "row_level",
			skill_sharing: tenantTier === "free" ? "read_only" : "full",
			max_concurrent_workspaces: Number.parseInt(tenantWorkspaceLimit, 10) || 10,
			max_agents_per_workspace: Number.parseInt(tenantAgentLimit, 10) || 20,
		}
	}

	async function handleCreateTenant() {
		try {
			await createTenant.mutateAsync({
				tenant_id: tenantId.trim(),
				display_name: tenantName.trim(),
				tier: tenantTier,
				metadata: { source: "webui-operator" },
				policy: tenantPolicy(),
			})
			toast.success("Tenant registered")
			setTenantId("")
			setTenantName("")
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Failed to register tenant")
		}
	}

	async function handleTenantLimitProbe() {
		try {
			await checkTenantLimit.mutateAsync({
				tenantId: tenantLimitProbeId.trim() || "default",
				currentCount: Number.parseInt(tenantLimitProbe, 10) || 0,
			})
			toast.success("Tenant limit checked")
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Failed to check tenant limit")
		}
	}

	async function handleRecordObservation() {
		try {
			await recordObservation.mutateAsync({
				task_id: observationTaskId.trim(),
				category: observationCategory,
				severity: observationSeverity,
				summary: observationSummary.trim(),
				details: parseJsonObject(observationDetails, "Observation details"),
			})
			toast.success("Observation recorded")
			setObservationSummary("")
			setObservationDetails("{}")
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Failed to record observation")
		}
	}

	async function handleCreateProposal() {
		try {
			const payload = {
				change_type: proposalType,
				title: proposalTitle.trim(),
				description: proposalDescription.trim(),
				proposed_change: parseJsonObject(proposalNextValue, "Proposed change"),
				current_value: parseJsonObject(proposalCurrentValue, "Current value"),
				source: "webui-operator",
				tags: splitTags(proposalTags),
			} satisfies CreateEvolutionProposalRequest
			await createProposal.mutateAsync(payload)
			toast.success("Evolution proposal created")
			setProposalTitle("")
			setProposalDescription("")
			setProposalTags("")
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Failed to create proposal")
		}
	}

	return (
		<SettingsSection
			title="Operator Surfaces"
			description="Minimal operator panels backed directly by live distributed execution, monitoring, reflection, and self-evolution APIs."
		>
			<div data-testid="operator-governance-summary" className="mb-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
				{governanceCards.map((card) => (
					<div
						key={card.label}
						data-testid={`operator-governance-card-${card.label.toLowerCase()}`}
						className="rounded-xl border border-border/50 bg-background/60 p-4"
					>
						<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{card.label}</div>
						<div className="mt-2 text-xl font-semibold text-foreground">{card.value}</div>
						<div className="mt-1 text-xs text-muted-foreground">{card.detail}</div>
					</div>
				))}
			</div>
			<Tabs defaultValue="distributed" className="space-y-4">
				<TabsList variant="line" className="flex w-full flex-wrap justify-start gap-2">
					<TabsTrigger value="distributed">Distributed execution</TabsTrigger>
					<TabsTrigger value="tenants">Tenants</TabsTrigger>
					<TabsTrigger value="monitoring">Monitoring</TabsTrigger>
					<TabsTrigger value="reflection">Reflection</TabsTrigger>
					<TabsTrigger value="evolution">Self-evolution</TabsTrigger>
				</TabsList>

				<TabsContent value="distributed" className="space-y-4">
					<div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
						<Card variant="compact">
							<CardHeader>
								<CardTitle className="flex items-center gap-2">
									<NetworkIcon className="size-4" />
									Cluster registry
								</CardTitle>
								<CardDescription>Register nodes and inspect current routing capacity.</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="flex justify-end">
									<Button size="sm" variant="outline" onClick={() => void refetchNodes()}>
										<RefreshCcwIcon className="size-4" />
										Refresh
									</Button>
									<Button size="sm" variant="outline" onClick={() => void refetchDispatches()}>
										<RefreshCcwIcon className="size-4" />
										History
									</Button>
								</div>
								{executionError ? (
									<div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
										{executionError instanceof Error ? executionError.message : "Distributed execution is unavailable."}
									</div>
								) : (
									<>
										<div className="grid gap-3 sm:grid-cols-3">
											<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
												<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Nodes</div>
												<div className="mt-3 text-2xl font-semibold text-foreground">{executionNodes?.total ?? 0}</div>
											</div>
											<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
												<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Healthy</div>
												<div className="mt-3 text-2xl font-semibold text-foreground">{executionNodes?.healthy_count ?? 0}</div>
											</div>
											<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
												<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Load</div>
												<div className="mt-3 text-2xl font-semibold text-foreground">
													{executionLoading ? "..." : executionNodes?.nodes.reduce((sum, node) => sum + node.current_load, 0) ?? 0}
												</div>
											</div>
										</div>

										<div className="grid gap-3 md:grid-cols-2">
											<Input value={nodeId} onChange={(event) => setNodeId(event.target.value)} placeholder="node_id" />
											<Input value={nodeAddress} onChange={(event) => setNodeAddress(event.target.value)} placeholder="http://host:19832" />
											<Input value={nodeCapacity} onChange={(event) => setNodeCapacity(event.target.value)} placeholder="capacity" />
											<Input value={nodeTags} onChange={(event) => setNodeTags(event.target.value)} placeholder="gpu,shadow,eu-west" />
										</div>
										<Button size="sm" onClick={() => void handleRegisterNode()} disabled={registerNode.isPending || !nodeId.trim() || !nodeAddress.trim()}>
											<GitBranchPlusIcon className="size-4" />
											Register node
										</Button>

										<div className="space-y-3">
											{executionNodes?.nodes.length ? (
												executionNodes.nodes.map((node) => (
													<div key={node.node_id} className="rounded-2xl border border-border/50 bg-background/60 p-4">
														<div className="flex flex-wrap items-start justify-between gap-3">
															<div>
																<div className="text-sm font-medium text-foreground">{node.node_id}</div>
																<div className="mt-1 text-xs text-muted-foreground">{node.address}</div>
																<div className="mt-2 flex flex-wrap gap-2">
																	<Badge variant={node.is_healthy ? "default" : "destructive"}>{node.status}</Badge>
																	<Badge variant="outline">load {node.current_load}/{node.capacity}</Badge>
																	{node.tags.map((tag) => (
																		<Badge key={`${node.node_id}-${tag}`} variant="outline">{tag}</Badge>
																	))}
																</div>
															</div>
															<Button
																size="icon"
																variant="ghost"
																data-testid={`operator-node-delete-${testIdSafe(node.node_id)}`}
																onClick={() =>
																	void deregisterNode
																		.mutateAsync(node.node_id)
																		.then(() => toast.success("Node removed"))
																		.catch((error) => toast.error(error instanceof Error ? error.message : "Failed to remove node"))
																}
																disabled={deregisterNode.isPending}
															>
																<Trash2Icon className="size-4" />
															</Button>
														</div>
														<div className="mt-3 text-xs text-muted-foreground">Last heartbeat: {formatTimestamp(node.last_heartbeat)}</div>
													</div>
												))
											) : (
												<div className="text-sm text-muted-foreground">No execution nodes are registered.</div>
											)}
										</div>
									</>
								)}
							</CardContent>
						</Card>

						<Card variant="compact">
							<CardHeader>
								<CardTitle className="flex items-center gap-2">
									<RouteIcon className="size-4" />
									Routing probe
								</CardTitle>
								<CardDescription>Ask the current registry to resolve a target node for a task id.</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="grid gap-3 md:grid-cols-2">
									<Input value={routeTaskId} onChange={(event) => setRouteTaskId(event.target.value)} placeholder="task id" />
									<Input value={routeAffinityNode} onChange={(event) => setRouteAffinityNode(event.target.value)} placeholder="optional affinity node" />
								</div>
								<Button size="sm" onClick={() => void handleRouteTask()} disabled={routeTask.isPending || !routeTaskId.trim()}>
									<RouteIcon className="size-4" />
									Resolve route
								</Button>
								{routeDecision ? (
									<div className="rounded-2xl border border-border/50 bg-background/60 p-4 text-sm">
										<div className="font-medium text-foreground">Target node: {routeDecision.target_node_id}</div>
										<div className="mt-2 text-muted-foreground">Strategy: {routeDecision.strategy}</div>
										<div className="mt-1 text-muted-foreground">Reason: {routeDecision.reason}</div>
									</div>
								) : (
									<div className="text-sm text-muted-foreground">No routing decision loaded yet.</div>
								)}
								<div data-testid="operator-dispatch-history" className="space-y-2">
									<div className="text-sm font-medium text-foreground">Recent dispatches</div>
									{dispatchesError ? (
										<div className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">
											{dispatchesError instanceof Error ? dispatchesError.message : "Dispatch history is unavailable."}
										</div>
									) : dispatches.length ? (
										dispatches.slice(0, 5).map((dispatch) => (
											<div key={dispatch.dispatch_id} className="rounded-xl border border-border/50 bg-background/60 p-3 text-xs">
												<div className="flex flex-wrap items-center justify-between gap-2">
													<span className="font-medium text-foreground">{dispatch.task_id}</span>
													<Badge variant={dispatch.status === "completed" || dispatch.status === "replayed" ? "default" : "outline"}>{dispatch.status}</Badge>
												</div>
												<div className="mt-1 text-muted-foreground">
													{dispatch.target_node_id ?? "none"} · {dispatch.strategy} · {formatTimestamp(dispatch.created_at)}
												</div>
											</div>
										))
									) : (
										<div className="text-sm text-muted-foreground">No dispatch history recorded yet.</div>
									)}
								</div>
							</CardContent>
						</Card>
					</div>
				</TabsContent>

				<TabsContent value="tenants" className="space-y-4">
					<div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
						<Card variant="compact">
							<CardHeader>
								<CardTitle className="flex items-center gap-2">
									<UsersIcon className="size-4" />
									Tenant governance
								</CardTitle>
								<CardDescription>Register tenants, inspect isolation policy, and probe limits.</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="flex justify-end">
									<Button
										size="sm"
										variant="outline"
										onClick={() => {
											void refetchTenants()
											void refetchTenantGovernance()
										}}
									>
										<RefreshCcwIcon className="size-4" />
										Refresh
									</Button>
								</div>
								{tenantsError ? (
									<div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
										{tenantsError instanceof Error ? tenantsError.message : "Tenant governance is unavailable."}
									</div>
								) : (
									<>
										<div className="grid gap-3 sm:grid-cols-3">
											<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
												<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Tenants</div>
												<div className="mt-3 text-2xl font-semibold text-foreground">{tenantGovernance?.tenant_count ?? tenantsData?.total ?? 0}</div>
											</div>
											<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
												<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Enterprise</div>
												<div className="mt-3 text-2xl font-semibold text-foreground">{tenantGovernance?.enterprise_count ?? 0}</div>
											</div>
											<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
												<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Workspace cap</div>
												<div className="mt-3 text-2xl font-semibold text-foreground">{tenantGovernance?.max_concurrent_workspaces ?? 0}</div>
											</div>
										</div>

										<div className="grid gap-3 md:grid-cols-2">
											<Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="tenant id" />
											<Input value={tenantName} onChange={(event) => setTenantName(event.target.value)} placeholder="display name" />
											<select
												className="border-input dark:bg-input/30 h-9 w-full rounded-md border bg-transparent px-3 text-sm"
												title="Tenant tier"
												value={tenantTier}
												onChange={(event) => setTenantTier(event.target.value as "free" | "pro" | "enterprise")}
											>
												<option value="free">free</option>
												<option value="pro">pro</option>
												<option value="enterprise">enterprise</option>
											</select>
											<Input value={tenantWorkspaceLimit} onChange={(event) => setTenantWorkspaceLimit(event.target.value)} placeholder="workspace limit" />
											<Input value={tenantAgentLimit} onChange={(event) => setTenantAgentLimit(event.target.value)} placeholder="agent limit" />
										</div>
										<Button size="sm" onClick={() => void handleCreateTenant()} disabled={createTenant.isPending || !tenantId.trim()}>
											<UsersIcon className="size-4" />
											Register tenant
										</Button>

										<div className="grid gap-3 md:grid-cols-2">
											<Input value={tenantLimitProbeId} onChange={(event) => setTenantLimitProbeId(event.target.value)} placeholder="tenant id" />
											<Input value={tenantLimitProbe} onChange={(event) => setTenantLimitProbe(event.target.value)} placeholder="current workspace count" />
										</div>
										<Button size="sm" variant="outline" onClick={() => void handleTenantLimitProbe()} disabled={checkTenantLimit.isPending}>
											Check workspace limit
										</Button>
										{checkTenantLimit.data ? (
											<div className="rounded-2xl border border-border/50 bg-background/60 p-4 text-sm text-muted-foreground">
												<span className="font-medium text-foreground">{checkTenantLimit.data.tenant_id}</span>
												<span className="mx-2">{checkTenantLimit.data.allowed ? "allowed" : "blocked"}</span>
												<span>{checkTenantLimit.data.current_count}/{checkTenantLimit.data.limit}</span>
											</div>
										) : null}
									</>
								)}
							</CardContent>
						</Card>

						<Card variant="compact">
							<CardHeader>
								<CardTitle>Tenant registry</CardTitle>
								<CardDescription>Current in-memory tenant registry and isolation policy controls.</CardDescription>
							</CardHeader>
							<CardContent className="space-y-3">
								{tenantsData?.tenants.length ? (
									tenantsData.tenants.map((tenant) => (
										<div key={tenant.tenant_id} className="rounded-2xl border border-border/50 bg-background/60 p-4">
											<div className="flex flex-wrap items-start justify-between gap-3">
												<div>
													<div className="text-sm font-medium text-foreground">{tenant.display_name || tenant.tenant_id}</div>
													<div className="mt-1 text-xs text-muted-foreground">{tenant.tenant_id}</div>
													<div className="mt-2 flex flex-wrap gap-2">
														<Badge variant={tenant.is_enterprise ? "default" : "outline"}>{tenant.tier}</Badge>
														<Badge variant="secondary">{tenant.is_enterprise ? "enterprise" : "standard"}</Badge>
													</div>
												</div>
												<div className="flex gap-2">
													<Button
														size="sm"
														variant="outline"
														onClick={() =>
															void updateTenantPolicy
																.mutateAsync({ tenantId: tenant.tenant_id, policy: tenantPolicy() })
																.then(() => toast.success("Tenant policy updated"))
																.catch((error) => toast.error(error instanceof Error ? error.message : "Failed to update policy"))
														}
													>
														Apply form policy
													</Button>
													<Button
														size="icon"
														variant="ghost"
														disabled={tenant.tenant_id === "default" || deleteTenant.isPending}
														data-testid={`operator-tenant-delete-${testIdSafe(tenant.tenant_id)}`}
														onClick={() =>
															void deleteTenant
																.mutateAsync(tenant.tenant_id)
																.then(() => toast.success("Tenant removed"))
																.catch((error) => toast.error(error instanceof Error ? error.message : "Failed to remove tenant"))
														}
													>
														<Trash2Icon className="size-4" />
													</Button>
												</div>
											</div>
										</div>
									))
								) : (
									<div className="text-sm text-muted-foreground">No tenants registered yet.</div>
								)}

								{tenantGovernance?.audit_events.length ? (
									<div className="grid gap-2">
										{tenantGovernance.audit_events.slice(0, 5).map((event) => (
											<div key={`${event.timestamp}:${event.tenant_id}:${event.event}`} className="rounded-xl border border-border/50 bg-background/60 px-3 py-2 text-xs text-muted-foreground">
												<span className="font-medium text-foreground">{event.event}</span>
												<span className="mx-2">{event.tenant_id}</span>
												<span>{formatTimestamp(event.timestamp)}</span>
											</div>
										))}
									</div>
								) : null}
							</CardContent>
						</Card>
					</div>
				</TabsContent>

				<TabsContent value="monitoring" className="space-y-4">
					<Card variant="compact">
						<CardHeader>
							<CardTitle className="flex items-center gap-2">
								<GaugeIcon className="size-4" />
								Metrics snapshot
							</CardTitle>
							<CardDescription>Direct view over the live /api/metrics/json payload.</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							<div className="flex justify-end">
								<Button size="sm" variant="outline" onClick={() => void refetchMetrics()}>
									<RefreshCcwIcon className="size-4" />
									Refresh
								</Button>
							</div>
							{metricsError ? (
								<div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
									{metricsError instanceof Error ? metricsError.message : "Monitoring API is unavailable."}
								</div>
							) : (
								<>
									<div className="grid gap-3 sm:grid-cols-3">
										<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
											<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Metrics</div>
											<div className="mt-3 text-2xl font-semibold text-foreground">{metricsData?.count ?? 0}</div>
										</div>
										<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
											<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Task counters</div>
											<div className="mt-3 text-2xl font-semibold text-foreground">{metrics.filter((metric) => metric.name.includes("task")).length}</div>
										</div>
										<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
											<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Gauges</div>
											<div className="mt-3 text-2xl font-semibold text-foreground">{metrics.filter((metric) => metric.kind === "gauge").length}</div>
										</div>
									</div>
									{metricsLoading ? (
										<div className="text-sm text-muted-foreground">Loading metrics…</div>
									) : topMetrics.length ? (
										<div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
											{topMetrics.map((metric) => (
												<div key={metric.name} className="rounded-2xl border border-border/50 bg-background/60 p-4">
													<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{metric.kind}</div>
													<div className="mt-2 break-all text-sm font-medium text-foreground">{metric.name}</div>
													<div className="mt-3 text-2xl font-semibold text-foreground">{metric.value}</div>
												</div>
											))}
										</div>
									) : (
										<div className="text-sm text-muted-foreground">No metrics recorded yet.</div>
									)}
								</>
							)}
						</CardContent>
					</Card>
				</TabsContent>

				<TabsContent value="reflection" className="space-y-4">
					<div className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
						<Card variant="compact">
							<CardHeader>
								<CardTitle className="flex items-center gap-2">
									<BrainCircuitIcon className="size-4" />
									Reflection control
								</CardTitle>
								<CardDescription>Record observations and trigger a fresh insight derivation pass.</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="flex justify-end gap-2">
									<Button
										size="sm"
										variant="outline"
										onClick={() => {
											void refetchSummary()
											void refetchObservations()
											void refetchInsights()
										}}
									>
										<RefreshCcwIcon className="size-4" />
										Refresh
									</Button>
									<Button
										size="sm"
										onClick={() =>
											void deriveInsights
												.mutateAsync()
												.then(() => toast.success("Insights derived"))
												.catch((error) => toast.error(error instanceof Error ? error.message : "Failed to derive insights"))
										}
										disabled={deriveInsights.isPending}
									>
										<TrendingUpIcon className="size-4" />
										Derive insights
									</Button>
									<Button
										size="sm"
										variant="outline"
										onClick={() => downloadOperatorExport("/api/reflection/export?dataset=observations&format=jsonl")}
									>
										Export observations
									</Button>
									<Button
										size="sm"
										variant="outline"
										onClick={() => downloadOperatorExport("/api/reflection/export?dataset=insights&format=jsonl")}
									>
										Export insights
									</Button>
								</div>
								{summaryError || observationsError || insightsError ? (
									<div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
										{summaryError instanceof Error
											? summaryError.message
											: observationsError instanceof Error
												? observationsError.message
												: insightsError instanceof Error
													? insightsError.message
													: "Reflection APIs are unavailable."}
									</div>
								) : (
									<>
										<div className="grid gap-3 sm:grid-cols-3">
											<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
												<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Window</div>
												<div className="mt-3 text-2xl font-semibold text-foreground">{reflectionSummary?.window_size ?? 0}</div>
											</div>
											<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
												<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Success rate</div>
												<div className="mt-3 text-2xl font-semibold text-foreground">{Math.round((reflectionSummary?.success_rate ?? 0) * 100)}%</div>
											</div>
											<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
												<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Errors</div>
												<div className="mt-3 text-2xl font-semibold text-foreground">{reflectionSummary?.error_count ?? 0}</div>
											</div>
										</div>

										<div className="grid gap-3 md:grid-cols-2">
											<Input value={observationTaskId} onChange={(event) => setObservationTaskId(event.target.value)} placeholder="task id" />
											<Input value={observationSummary} onChange={(event) => setObservationSummary(event.target.value)} placeholder="observation summary" />
											<select
												className="border-input dark:bg-input/30 h-9 w-full rounded-md border bg-transparent px-3 text-sm"
												title="Observation category"
												value={observationCategory}
												onChange={(event) => setObservationCategory(event.target.value as ReflectionObservationCategory)}
											>
												<option value="outcome">outcome</option>
												<option value="performance">performance</option>
												<option value="error">error</option>
												<option value="tool_usage">tool_usage</option>
												<option value="model_quality">model_quality</option>
											</select>
											<select
												className="border-input dark:bg-input/30 h-9 w-full rounded-md border bg-transparent px-3 text-sm"
												title="Observation severity"
												value={observationSeverity}
												onChange={(event) => setObservationSeverity(event.target.value as ReflectionObservationSeverity)}
											>
												<option value="info">info</option>
												<option value="warning">warning</option>
												<option value="critical">critical</option>
											</select>
										</div>
										<Textarea value={observationDetails} onChange={(event) => setObservationDetails(event.target.value)} className="min-h-24 text-sm" placeholder='{"status":"completed"}' />
										<Button size="sm" onClick={() => void handleRecordObservation()} disabled={recordObservation.isPending || !observationTaskId.trim() || !observationSummary.trim()}>
											<ActivityIcon className="size-4" />
											Record observation
										</Button>
									</>
								)}
							</CardContent>
						</Card>

						<Card variant="compact">
							<CardHeader>
								<CardTitle>Recent observations and insights</CardTitle>
								<CardDescription>Direct feed from the reflection service caches.</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div>
									<div className="mb-2 text-sm font-medium text-foreground">Observations</div>
									{observationsLoading ? (
										<div className="text-sm text-muted-foreground">Loading observations…</div>
									) : reflectionObservations?.observations.length ? (
										<div className="grid gap-3">
											{reflectionObservations.observations.map((observation) => (
												<div key={observation.observation_id} className="rounded-2xl border border-border/50 bg-background/60 p-4">
													<div className="flex flex-wrap items-center justify-between gap-2">
														<div className="text-sm font-medium text-foreground">{observation.summary}</div>
														<div className="flex flex-wrap gap-2">
															<Badge variant="outline">{observation.category}</Badge>
															<Badge variant={observation.severity === "critical" ? "destructive" : "outline"}>{observation.severity}</Badge>
														</div>
													</div>
													<div className="mt-2 text-xs text-muted-foreground">{observation.task_id} · {formatTimestamp(observation.timestamp)}</div>
												</div>
											))}
										</div>
									) : (
										<div className="text-sm text-muted-foreground">No observations recorded yet.</div>
									)}
								</div>

								<div>
									<div className="mb-2 text-sm font-medium text-foreground">Insights</div>
									{insightsLoading ? (
										<div className="text-sm text-muted-foreground">Loading insights…</div>
									) : reflectionInsights?.insights.length ? (
										<div className="grid gap-3">
											{reflectionInsights.insights.map((insight) => (
												<div key={insight.insight_id} className="rounded-2xl border border-border/50 bg-background/60 p-4">
													<div className="flex flex-wrap items-center justify-between gap-2">
														<div className="text-sm font-medium text-foreground">{insight.description}</div>
														<Badge variant="outline">{Math.round(insight.confidence * 100)}%</Badge>
													</div>
													<div className="mt-2 text-xs text-muted-foreground">{insight.category}</div>
													<div className="mt-2 text-sm text-muted-foreground">{insight.suggested_action}</div>
												</div>
											))}
										</div>
									) : (
										<div className="text-sm text-muted-foreground">No insights derived yet.</div>
									)}
								</div>
							</CardContent>
						</Card>
					</div>
				</TabsContent>

				<TabsContent value="evolution" className="space-y-4">
					<div className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
						<Card variant="compact">
							<CardHeader>
								<CardTitle className="flex items-center gap-2">
									<GitBranchPlusIcon className="size-4" />
									Proposal intake
								</CardTitle>
								<CardDescription>Create a proposal directly against the existing self-evolution governance API.</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="grid gap-3 sm:grid-cols-3">
									<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
										<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Total</div>
										<div className="mt-3 text-2xl font-semibold text-foreground">{proposals.length}</div>
									</div>
									<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
										<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Awaiting approval</div>
										<div className="mt-3 text-2xl font-semibold text-foreground">{proposalCounts.awaiting_approval ?? 0}</div>
									</div>
									<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
										<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Promoted</div>
										<div className="mt-3 text-2xl font-semibold text-foreground">{proposalCounts.promoted ?? 0}</div>
									</div>
								</div>
								{proposalsError ? (
									<div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
										{proposalsError instanceof Error ? proposalsError.message : "Self-evolution API is unavailable."}
									</div>
								) : (
									<>
										<Input value={proposalTitle} onChange={(event) => setProposalTitle(event.target.value)} placeholder="proposal title" />
										<select
											className="border-input dark:bg-input/30 h-9 w-full rounded-md border bg-transparent px-3 text-sm"
											title="Evolution change type"
											value={proposalType}
											onChange={(event) => setProposalType(event.target.value as EvolutionChangeType)}
										>
											<option value="prompt_template">prompt_template</option>
											<option value="model_default">model_default</option>
											<option value="skill_config">skill_config</option>
											<option value="tool_config">tool_config</option>
											<option value="brain_policy">brain_policy</option>
											<option value="memory_policy">memory_policy</option>
										</select>
										<Textarea value={proposalDescription} onChange={(event) => setProposalDescription(event.target.value)} className="min-h-24 text-sm" placeholder="Describe the intended change and validation rationale." />
										<Input value={proposalTags} onChange={(event) => setProposalTags(event.target.value)} placeholder="operator,shadow,policy" />
										<div className="grid gap-3 md:grid-cols-2">
											<Textarea value={proposalCurrentValue} onChange={(event) => setProposalCurrentValue(event.target.value)} className="min-h-28 text-sm" placeholder='{"current":"value"}' />
											<Textarea value={proposalNextValue} onChange={(event) => setProposalNextValue(event.target.value)} className="min-h-28 text-sm" placeholder='{"proposed":"value"}' />
										</div>
										<Button size="sm" onClick={() => void handleCreateProposal()} disabled={createProposal.isPending || !proposalTitle.trim() || proposalDescription.trim().length < 10}>
											<GitBranchPlusIcon className="size-4" />
											Create proposal
										</Button>
									</>
								)}
							</CardContent>
						</Card>

						<Card variant="compact">
							<CardHeader>
								<CardTitle className="flex items-center gap-2">
									<CheckCircle2Icon className="size-4" />
									Proposal queue
								</CardTitle>
								<CardDescription>Latest proposals and the currently valid lifecycle actions for each status.</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="flex flex-wrap justify-end gap-2">
									<Button size="sm" variant="outline" onClick={() => void refetchProposals()}>
										<RefreshCcwIcon className="size-4" />
										Refresh
									</Button>
									<Button
										size="sm"
										variant="outline"
										onClick={() => downloadOperatorExport("/api/evolution/export?dataset=proposals&format=jsonl")}
									>
										Export proposals
									</Button>
									<Button
										size="sm"
										variant="outline"
										onClick={() => downloadOperatorExport("/api/evolution/export?dataset=audit&format=jsonl")}
									>
										Export audit
									</Button>
									<Button
										size="sm"
										variant="outline"
										onClick={() => downloadOperatorExport("/api/evolution/export?dataset=shadow_runs&format=jsonl")}
									>
										Export shadow runs
									</Button>
								</div>
								{proposalsLoading ? (
									<div className="text-sm text-muted-foreground">Loading proposals…</div>
								) : proposals.length ? (
									<div className="grid gap-3">
										{proposals.map((proposal) => (
											<div key={proposal.proposal_id} className="rounded-2xl border border-border/50 bg-background/60 p-4">
												<div className="flex flex-wrap items-start justify-between gap-3">
													<div>
														<div className="text-sm font-medium text-foreground">{proposal.title}</div>
														<div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
															<span>{proposal.change_type}</span>
															<span>{formatTimestamp(proposal.updated_at)}</span>
														</div>
													</div>
													<Badge variant={statusBadgeVariant(proposal.status)}>{proposal.status}</Badge>
												</div>
												<p className="mt-3 text-sm text-muted-foreground">{proposal.description}</p>
												{proposal.validation_notes ? (
													<p className="mt-2 text-xs text-muted-foreground">Validation: {proposal.validation_notes}</p>
												) : null}
												<div className="mt-3">
													<ProposalActionBar proposal={proposal} />
												</div>
											</div>
										))}
									</div>
								) : (
									<div className="text-sm text-muted-foreground">No proposals exist yet.</div>
								)}

								<div className="border-border/50 bg-background/40 rounded-2xl border p-4">
									<div className="mb-2 flex items-center justify-between gap-2">
										<div>
											<div className="text-sm font-medium text-foreground">Recent audit trail</div>
											<div className="text-xs text-muted-foreground">Status transitions and operator actions from self-evolution governance.</div>
										</div>
										<Button size="sm" variant="outline" onClick={() => void refetchAudit()}>
											<RefreshCcwIcon className="size-4" />
											Refresh
										</Button>
									</div>
									{auditError ? (
										<div className="text-sm text-destructive">{auditError instanceof Error ? auditError.message : "Audit trail is unavailable."}</div>
									) : auditLoading ? (
										<div className="text-sm text-muted-foreground">Loading audit trail…</div>
									) : auditEntries.length ? (
										<div className="grid gap-3">
											{auditEntries.map((entry) => (
												<div key={entry.entry_id} className="rounded-2xl border border-border/50 bg-background/60 p-3">
													<div className="flex flex-wrap items-center justify-between gap-2">
														<div className="text-sm font-medium text-foreground">{entry.action}</div>
														<Badge variant="outline">{formatTimestamp(entry.timestamp)}</Badge>
													</div>
													<div className="mt-1 text-xs text-muted-foreground">
														{entry.proposal_id} · {entry.actor}
														{entry.from_status || entry.to_status ? ` · ${entry.from_status ?? "-"} -> ${entry.to_status ?? "-"}` : ""}
													</div>
													{entry.notes ? <div className="mt-2 text-sm text-muted-foreground">{entry.notes}</div> : null}
												</div>
											))}
										</div>
									) : (
										<div className="text-sm text-muted-foreground">No audit entries recorded yet.</div>
									)}
								</div>
							</CardContent>
						</Card>
					</div>
				</TabsContent>
			</Tabs>
		</SettingsSection>
	)
}
