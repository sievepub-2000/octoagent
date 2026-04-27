"use client";

import { useQuery } from "@tanstack/react-query";
import {
	AlertTriangleIcon,
	ArrowRightIcon,
	BotIcon,
	BoxesIcon,
	CableIcon,
	CheckCircle2Icon,
	DownloadCloudIcon,
	FileTextIcon,
	RefreshCcwIcon,
	ServerIcon,
	SparklesIcon,
	WaypointsIcon,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAgents } from "@/core/agents/hooks";
import {
	useCapabilityAuditState,
	useCapabilityInventory,
	useCapabilityRuntimeState,
	useMigrateCapabilities,
} from "@/core/capabilities/hooks";
import type {
	CapabilityCategory,
	CapabilityMigrationCategorySummary,
	CapabilityMigrationResponse,
	CapabilityMigrationResult,
} from "@/core/capabilities/types";
import { useI18n } from "@/core/i18n/hooks";
import { useMCPConfig } from "@/core/mcp/hooks";
import { useModels } from "@/core/models/hooks";
import { loadPluginCapabilities } from "@/core/plugins/api";
import { useRepoHooks } from "@/core/repo-hooks/hooks";
import { useSkills } from "@/core/skills/hooks";

import { CapabilityRegistrySection } from "./capability-registry-section";
import { OperatorSurfacesSection } from "./operator-surfaces-section";

const CATEGORY_ORDER: CapabilityCategory[] = ["skills", "agents", "instructions", "hooks", "mcp"];

function renderStatusBadge(result: CapabilityMigrationResult) {
	if (result.status === "error") {
		return (
			<Badge variant="destructive" className="gap-1 text-[10px] uppercase">
				<FileTextIcon className="size-3" />
				{result.status}
			</Badge>
		);
	}
	return (
		<Badge variant="outline" className="gap-1 text-[10px] uppercase">
			<CheckCircle2Icon className="size-3" />
			{result.status}
		</Badge>
	);
}

function CategoryDelta({ summary }: { summary: CapabilityMigrationCategorySummary | null }) {
	if (!summary) {
		return <div className="mt-2 text-xs text-muted-foreground">No recent migration delta.</div>;
	}

	return (
		<div className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
			<div className="rounded-xl border border-border/50 bg-background/60 px-3 py-2">
				Installed {summary.installed_before}
				<span className="mx-1 inline-flex items-center text-muted-foreground">
					<ArrowRightIcon className="size-3" />
				</span>
				{summary.installed_after}
				<span className="ml-1 text-emerald-600">({summary.installed_delta >= 0 ? "+" : ""}{summary.installed_delta})</span>
			</div>
			<div className="rounded-xl border border-border/50 bg-background/60 px-3 py-2">
				Matched {summary.matched_before}
				<span className="mx-1 inline-flex items-center text-muted-foreground">
					<ArrowRightIcon className="size-3" />
				</span>
				{summary.matched_after}
				<span className="ml-1 text-emerald-600">({summary.matched_delta >= 0 ? "+" : ""}{summary.matched_delta})</span>
			</div>
		</div>
	);
}

function summarizeAuditDetails(details: Record<string, unknown>) {
	const summarizeValue = (value: unknown) => {
		if (typeof value === "string") {
			return value;
		}
		if (
			typeof value === "number"
			|| typeof value === "boolean"
			|| typeof value === "bigint"
		) {
			return String(value);
		}
		if (value === null || value === undefined) {
			return "";
		}
		return JSON.stringify(value);
	};

	return Object.entries(details)
		.filter(([, value]) => value !== null && value !== undefined && value !== "")
		.slice(0, 5)
		.map(([key, value]) => {
			if (Array.isArray(value)) {
				return `${key}: ${value.map((item) => summarizeValue(item)).join(", ")}`;
			}
			if (typeof value === "object") {
				return `${key}: ${JSON.stringify(value)}`;
			}
			return `${key}: ${summarizeValue(value)}`;
		});
}

export function SystemSettingsPage() {
	const { t } = useI18n();
	const { models } = useModels();
	const { agents } = useAgents();
	const { skills } = useSkills();
	const { hooks } = useRepoHooks();
	const { config: mcpConfig } = useMCPConfig();
	const { data: pluginData } = useQuery({
		queryKey: ["plugin-capabilities"],
		queryFn: loadPluginCapabilities,
		refetchOnWindowFocus: false,
	});
	const { inventory, isLoading, error, refetch } = useCapabilityInventory();
	const { runtimeState, refetch: refetchRuntimeState } = useCapabilityRuntimeState();
	const { auditState, refetch: refetchAuditState } = useCapabilityAuditState();
	const migrateCapabilities = useMigrateCapabilities();
	const [latestMigration, setLatestMigration] = useState<CapabilityMigrationResponse | null>(null);

	function formatTimestamp(value: string | null | undefined) {
		if (!value) {
			return "-";
		}
		const parsed = new Date(value);
		return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
	}

	const runtimeCards = [
		{ id: "models", icon: ServerIcon, label: t.sidebar.models, value: models.length },
		{ id: "agents", icon: BotIcon, label: t.sidebar.agents, value: agents.length },
		{ id: "skills", icon: SparklesIcon, label: t.sidebar.skills, value: skills.length },
		{ id: "hooks", icon: WaypointsIcon, label: t.settings.sections.hooks, value: hooks.length },
		{ id: "mcp", icon: CableIcon, label: t.sidebar.mcp, value: Object.keys(mcpConfig?.mcp_servers ?? {}).length },
		{ id: "plugins", icon: BoxesIcon, label: t.sidebar.plugins, value: pluginData?.plugins.length ?? 0 },
	];

	const categoryLabels: Record<CapabilityCategory, string> = {
		skills: t.sidebar.skills,
		agents: t.sidebar.agents,
		instructions: "Instructions",
		hooks: t.settings.sections.hooks,
		mcp: t.sidebar.mcp,
	};

	const latestResults = latestMigration?.results ?? [];
	const latestSummary = latestMigration?.summary ?? null;
	const latestSuccessResults = latestResults.filter((result) => result.status !== "error");
	const latestErrorResults = latestResults.filter((result) => result.status === "error");

	const repoCards = inventory
		? CATEGORY_ORDER.map((category) => ({
				category,
				label: categoryLabels[category],
				source: inventory.source[category].length,
				installed: inventory.installed[category].length,
				matched: inventory.matched[category].length,
				summary: latestSummary?.categories[category] ?? null,
			}))
		: [];

	const summaryCards = latestSummary
		? [
				{ id: "changed", label: "Changed", value: latestSummary.changed_count, tone: "text-foreground" },
				{ id: "matched", label: "Alignment delta", value: latestSummary.matched_delta, tone: latestSummary.matched_delta > 0 ? "text-emerald-600" : "text-muted-foreground" },
				{ id: "pending", label: "Still pending", value: latestSummary.pending_after, tone: latestSummary.pending_after === 0 ? "text-emerald-600" : "text-amber-600" },
				{ id: "errors", label: "Errors", value: latestSummary.error_count, tone: latestSummary.error_count > 0 ? "text-destructive" : "text-muted-foreground" },
			]
		: [];

	async function handleMigrate(categories?: CapabilityCategory[]) {
		try {
			const response = await migrateCapabilities.mutateAsync(categories);
			setLatestMigration(response);
			toast.success(
				`Migration finished: ${response.summary.changed_count} changed, ${response.summary.error_count} failed, ${response.summary.pending_after} still pending.`,
			);
		} catch (migrationError) {
			toast.error(migrationError instanceof Error ? migrationError.message : "Capability migration failed.");
		}
	}

	return (
		<div className="flex h-full flex-col overflow-y-auto p-6">
			<header className="mb-6 flex items-start justify-between gap-3">
				<div>
					<h1 className="text-lg font-semibold text-foreground">{t.settings.system.title}</h1>
					<p className="mt-1 text-sm text-muted-foreground">{t.settings.system.description}</p>
				</div>
				<div className="flex gap-2">
					<Button size="sm" variant="outline" onClick={() => {
						void refetch();
						void refetchRuntimeState();
						void refetchAuditState();
					}}>
						<RefreshCcwIcon className="size-4" />
						{t.settings.system.refresh}
					</Button>
					<Button size="sm" onClick={() => void handleMigrate()} disabled={migrateCapabilities.isPending}>
						<DownloadCloudIcon className="size-4" />
						{migrateCapabilities.isPending ? t.settings.system.migrating : t.settings.system.migrateAll}
					</Button>
				</div>
			</header>

			<div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
				<Card variant="compact">
					<CardHeader>
						<CardTitle>{t.settings.system.runtimeOverview}</CardTitle>
						<CardDescription>{t.workspace.settingsAndMore}</CardDescription>
					</CardHeader>
					<CardContent className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
						{runtimeCards.map((card) => {
							const Icon = card.icon;
							return (
								<div key={card.id} className="rounded-2xl border border-border/50 bg-background/60 p-4">
									<div className="flex items-center gap-2 text-primary">
										<Icon className="size-4" />
										<span className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{card.label}</span>
									</div>
									<div className="mt-3 text-2xl font-semibold text-foreground">{card.value}</div>
								</div>
							);
						})}
					</CardContent>
				</Card>

				<Card variant="compact">
					<CardHeader>
						<CardTitle>{t.settings.system.repoOverview}</CardTitle>
						<CardDescription>{inventory?.target_root}</CardDescription>
					</CardHeader>
					<CardContent className="space-y-3">
						{isLoading ? (
							<div className="text-sm text-muted-foreground">{t.common.loading}</div>
						) : error ? (
							<div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
								{error instanceof Error ? error.message : t.settings.system.sourceUnavailable}
							</div>
						) : (
							repoCards.map((card) => (
								<div key={card.category} className="rounded-2xl border border-border/50 bg-background/60 p-4">
									<div className="flex items-center justify-between gap-3">
										<div className="min-w-0 flex-1">
											<div className="text-sm font-medium text-foreground">{card.label}</div>
											<div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
												<span>{t.settings.system.sourceInventory}: {card.source}</span>
												<span>{t.settings.system.installedInventory}: {card.installed}</span>
												<span>{t.settings.system.matchedInventory}: {card.matched}</span>
											</div>
											<CategoryDelta summary={card.summary} />
										</div>
										<Button size="sm" variant="outline" onClick={() => void handleMigrate([card.category])} disabled={migrateCapabilities.isPending}>
											{card.label}
										</Button>
									</div>
								</div>
							))
						)}
					</CardContent>
				</Card>
			</div>

				<div className="mt-4 grid gap-4 xl:grid-cols-[1fr_1fr]">
					<Card variant="compact">
						<CardHeader>
							<CardTitle>{t.settings.system.capabilityRuntime}</CardTitle>
							<CardDescription>{runtimeState?.target_root ?? inventory?.target_root}</CardDescription>
						</CardHeader>
						<CardContent className="space-y-3">
							<div className="flex flex-wrap gap-2">
								<Badge variant="outline">{runtimeState?.cache_state === "warm" ? t.settings.system.cacheWarm : t.settings.system.cacheCold}</Badge>
								<Badge variant={runtimeState?.listeners_registered ? "default" : "outline"}>
									{t.settings.system.listenersActive}
								</Badge>
							</div>
							<div className="grid gap-3 sm:grid-cols-2">
								<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
									<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Source</div>
									<div className="mt-3 text-2xl font-semibold text-foreground">{runtimeState?.total_source_items ?? 0}</div>
								</div>
								<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
									<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Matched</div>
									<div className="mt-3 text-2xl font-semibold text-foreground">{runtimeState?.total_matched_items ?? 0}</div>
								</div>
								<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
									<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{t.settings.system.lastInventoryBuild}</div>
									<div className="mt-3 text-sm font-medium text-foreground">{formatTimestamp(runtimeState?.last_inventory_built_at)}</div>
								</div>
								<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
									<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{t.settings.system.lastMigrationAt}</div>
									<div className="mt-3 text-sm font-medium text-foreground">{formatTimestamp(runtimeState?.last_migration_at)}</div>
								</div>
							</div>
							<div className="grid gap-3 sm:grid-cols-2">
								<div className="rounded-2xl border border-border/50 bg-background/60 p-4 text-sm text-muted-foreground">
									Hooks: {runtimeState?.hook_runtime.total_hooks ?? 0} / {runtimeState?.hook_runtime.enabled_hooks ?? 0}
								</div>
								<div className="rounded-2xl border border-border/50 bg-background/60 p-4 text-sm text-muted-foreground">
									Webhooks: {runtimeState?.hook_runtime.total_webhooks ?? 0} / {runtimeState?.hook_runtime.enabled_webhooks ?? 0}
								</div>
							</div>
						</CardContent>
					</Card>

					<Card variant="compact">
						<CardHeader>
							<CardTitle>{t.settings.system.capabilityAudit}</CardTitle>
							<CardDescription>{t.settings.system.auditTrail}</CardDescription>
						</CardHeader>
						<CardContent className="space-y-3">
							<div className="grid gap-3 sm:grid-cols-3">
								<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
									<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Events</div>
									<div className="mt-3 text-2xl font-semibold text-foreground">{auditState?.event_count ?? 0}</div>
								</div>
								<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
									<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Changed</div>
									<div className="mt-3 text-2xl font-semibold text-foreground">{auditState?.last_migration_summary?.changed_count ?? latestSummary?.changed_count ?? 0}</div>
								</div>
								<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
									<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Errors</div>
									<div className="mt-3 text-2xl font-semibold text-foreground">{auditState?.last_migration_summary?.error_count ?? latestSummary?.error_count ?? 0}</div>
								</div>
							</div>
							{!auditState || auditState.recent_events.length === 0 ? (
								<div className="text-sm text-muted-foreground">{t.settings.system.noAuditEntries}</div>
							) : (
								<div className="grid gap-3">
									{auditState.recent_events.map((entry) => (
										<div key={`${entry.event}:${entry.created_at}`} className="rounded-2xl border border-border/50 bg-background/60 p-4">
											<div className="flex items-start justify-between gap-3">
												<div>
													<div className="text-sm font-medium text-foreground">{entry.event}</div>
													<div className="mt-1 text-xs text-muted-foreground">{formatTimestamp(entry.created_at)}</div>
												</div>
												<Badge variant="outline" className="text-[10px] uppercase">{Object.keys(entry.details ?? {}).length} fields</Badge>
											</div>
											{summarizeAuditDetails(entry.details ?? {}).length ? (
												<div className="mt-3 flex flex-wrap gap-1.5">
													{summarizeAuditDetails(entry.details ?? {}).map((detail) => (
														<Badge key={`${entry.event}:${detail}`} variant="secondary" className="text-[10px]">
															{detail}
														</Badge>
													))}
												</div>
											) : null}
										</div>
									))}
								</div>
							)}
						</CardContent>
					</Card>
				</div>

					<CapabilityRegistrySection />

			<OperatorSurfacesSection />

			<Card variant="compact" className="mt-4">
				<CardHeader>
					<CardTitle>{t.settings.system.lastRun}</CardTitle>
					<CardDescription>{inventory?.source_root}</CardDescription>
				</CardHeader>
				<CardContent>
					{!latestMigration || latestResults.length === 0 ? (
						<div className="text-sm text-muted-foreground">{t.settings.system.noResults}</div>
					) : (
						<div className="space-y-4">
							<div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
								{summaryCards.map((card) => (
									<div key={card.id} className="rounded-2xl border border-border/50 bg-background/60 p-4">
										<div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{card.label}</div>
										<div className={`mt-3 text-2xl font-semibold ${card.tone}`}>{card.value}</div>
									</div>
								))}
							</div>

							<div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
								{CATEGORY_ORDER.map((category) => {
									const summary = latestSummary?.categories[category] ?? null;
									if (!summary) {
										return null;
									}
									return (
										<div key={category} className="rounded-2xl border border-border/50 bg-background/60 p-4">
											<div className="flex items-start justify-between gap-3">
												<div>
													<div className="text-sm font-medium text-foreground">{categoryLabels[category]}</div>
													<div className="mt-1 text-xs text-muted-foreground">
														Pending {summary.pending_before}
														<span className="mx-1 inline-flex items-center">
															<ArrowRightIcon className="size-3" />
														</span>
														{summary.pending_after}
													</div>
												</div>
												<Badge variant={summary.error_count > 0 ? "destructive" : "outline"} className="text-[10px] uppercase">
													{summary.error_count > 0 ? `${summary.error_count} errors` : `${summary.matched_delta >= 0 ? "+" : ""}${summary.matched_delta} aligned`}
												</Badge>
											</div>
											<div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
												<div className="rounded-xl border border-border/50 bg-background/60 px-3 py-2">Installed: {summary.installed_count}</div>
												<div className="rounded-xl border border-border/50 bg-background/60 px-3 py-2">Updated: {summary.updated_count}</div>
												<div className="rounded-xl border border-border/50 bg-background/60 px-3 py-2">Skipped: {summary.skipped_count}</div>
												<div className="rounded-xl border border-border/50 bg-background/60 px-3 py-2">Source total: {summary.source_total}</div>
											</div>
											<CategoryDelta summary={summary} />
										</div>
									);
								})}
							</div>

							<div className="grid gap-3 lg:grid-cols-2">
								<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
									<div className="flex items-center gap-2 text-sm font-medium text-foreground">
										<AlertTriangleIcon className="size-4 text-destructive" />
										Needs attention
									</div>
									{latestErrorResults.length === 0 ? (
										<div className="mt-3 text-sm text-muted-foreground">No failed migration items.</div>
									) : (
										<div className="mt-3 grid gap-3">
											{latestErrorResults.map((result) => (
												<div key={`${result.category}:${result.name}`} className="rounded-2xl border border-destructive/20 bg-destructive/5 p-4">
													<div className="flex items-start justify-between gap-3">
														<div>
															<div className="text-sm font-medium text-foreground">{result.name}</div>
															<p className="mt-1 text-xs text-muted-foreground">{result.message}</p>
														</div>
														{renderStatusBadge(result)}
													</div>
												</div>
											))}
										</div>
									)}
								</div>

								<div className="rounded-2xl border border-border/50 bg-background/60 p-4">
									<div className="flex items-center gap-2 text-sm font-medium text-foreground">
										<CheckCircle2Icon className="size-4 text-emerald-600" />
										Successful and no-op items
									</div>
									{latestSuccessResults.length === 0 ? (
										<div className="mt-3 text-sm text-muted-foreground">No successful migration items yet.</div>
									) : (
										<div className="mt-3 grid gap-3">
											{latestSuccessResults.map((result) => (
												<div key={`${result.category}:${result.name}`} className="rounded-2xl border border-border/50 bg-background/60 p-4">
													<div className="flex items-start justify-between gap-3">
														<div>
															<div className="text-sm font-medium text-foreground">{result.name}</div>
															<p className="mt-1 text-xs text-muted-foreground">{result.message}</p>
														</div>
														{renderStatusBadge(result)}
													</div>
												</div>
											))}
										</div>
									)}
								</div>
							</div>
						</div>
					)}
				</CardContent>
			</Card>
		</div>
	);
}
