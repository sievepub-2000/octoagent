"use client";

import { useQuery } from "@tanstack/react-query";
import { ActivityIcon, AlertTriangleIcon, CheckCircle2Icon, ExternalLinkIcon, PlugIcon, RefreshCwIcon, SearchIcon, ShieldAlertIcon, WaypointsIcon, WrenchIcon, XCircleIcon } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { getJSON } from "@/core/api/http";
import { useI18n } from "@/core/i18n/hooks";
import { useToolTrace } from "@/core/observation/hooks";
import type { ToolTraceEntry } from "@/core/observation/types";

const PluginsConfigPage = dynamic(() => import("@/app/workspace/config/plugins/page"), {
  ssr: false,
  loading: () => <p className="text-sm text-muted-foreground">Loading plugins…</p>,
});
const HooksSettingsPage = dynamic(
  () =>
    import("@/components/workspace/settings/hooks-settings-page").then(
      (module) => module.HooksSettingsPage,
    ),
  {
    ssr: false,
    loading: () => <p className="text-sm text-muted-foreground">Loading hooks…</p>,
  },
);

type HubTab = "tools" | "plugins" | "hooks";
type TraceFilter = "" | "subprocess_start" | "subprocess_end" | "artifact_lifecycle" | "subagent_runtime_cleanup" | "exception";

interface ToolEntry {
  id: string;
  name: string;
  category: "skill" | "mcp" | "channel" | "plugin" | "hook" | "builtin" | "desktop";
  description?: string;
  usage?: string;
  enabled?: boolean;
  badge?: string;
  status?: string;
  failureReason?: string;
  riskLevel?: string;
  parameterCount?: number;
  timeoutSeconds?: number | null;
  outputArtifacts?: string[];
}

function optionalText(value: string | null | undefined) {
  const trimmed = value?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : undefined;
}

interface SkillsResponse {
  skills?: Array<{
    name?: string;
    description?: string;
    license?: string;
    enabled?: boolean;
    category?: string;
  }>;
}

interface McpServerEntry {
  command?: string;
  url?: string;
  transport?: string;
  type?: string;
  disabled?: boolean;
  enabled?: boolean;
  description?: string;
  status?: string;
  status_reason?: string;
  failure_reason?: string;
  checked_at?: string | null;
  tool_count?: number;
  tools?: string[];
  registry_visible?: boolean;
}

interface McpConfigResponse {
  mcp_servers?: Record<string, McpServerEntry>;
  mcpServers?: Record<string, McpServerEntry>;
}

interface RegistryMcpEntry {
  name?: string;
  enabled?: boolean;
  transport?: string;
  description?: string;
  permission_scope?: string;
  status?: string;
  failure_reason?: string;
  checked_at?: string | null;
  tool_count?: number;
  tools?: string[];
  registry_visible?: boolean;
}


interface ChannelsStatusResponse {
  channels?: Record<
    string,
    {
      platform_label?: string;
      description?: string;
      enabled?: boolean;
      configured?: boolean;
    }
  >;
}

interface PluginRegistryResponse {
  entries?: Array<{
    plugin_id?: string;
    installed?: boolean;
    enabled?: boolean;
    source?: string;
  }>;
}

interface HooksListResponse {
  hooks?: Array<{
    name?: string;
    description?: string;
    enabled?: boolean;
    triggers?: Array<{ trigger?: string }>;
  }>;
}

interface DesktopControlStatusResponse {
  category?: string;
  badge?: string;
  enabled?: boolean;
  env_flag?: string;
  note?: string;
  tools?: Array<{ name?: string; description?: string }>;
}

interface ToolRegistryResponse {
  summary?: {
    mcp_total?: number;
    mcp_enabled?: number;
    skills_total?: number;
    skills_enabled?: number;
    plugins_total?: number;
    plugins_enabled?: number;
    channels_total?: number;
    channels_enabled?: number;
    builtin_tools_total?: number;
  };
  runtime?: {
    default_model?: string | null;
    total_models?: number;
    active_subagents?: number;
    max_concurrent_subagents?: number;
  };
  mcp?: RegistryMcpEntry[];
  builtin_tools?: Array<{
    name?: string;
    description?: string;
    category?: string;
    permission_scope?: string;
    parameters?: Record<string, unknown>;
    timeout_seconds?: number | null;
    output_artifacts?: string[];
    risk_level?: string;
    failure_modes?: string[];
  }>;
}

const CATEGORY_LABELS: Record<ToolEntry["category"], string> = {
  skill: "Skills",
  mcp: "MCP Servers",
  channel: "Software Interfaces",
  plugin: "Plugins",
  hook: "Hooks",
  builtin: "Built-in Tools",
  desktop: "Desktop Control",
};

const DESKTOP_CATEGORY_LABEL_I18N: Record<string, string> = {
  "en-US": "Desktop Control",
  "zh-CN": "桌面控制",
  "zh-TW": "桌面控制",
  "ja": "デスクトップ制御",
  "ko": "데스크톱 제어",
};

const CATEGORY_ORDER: ToolEntry["category"][] = [
  "skill",
  "mcp",
  "channel",
  "builtin",
  "desktop",
];

const TRACE_FILTERS: Array<{ value: TraceFilter; label: string }> = [
  { value: "", label: "All" },
  { value: "subprocess_start", label: "Process start" },
  { value: "subprocess_end", label: "Process end" },
  { value: "artifact_lifecycle", label: "Lifecycle" },
  { value: "subagent_runtime_cleanup", label: "Subagent cleanup" },
  { value: "exception", label: "Exceptions" },
];

function formatTracePayloadValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") {
    return String(value);
  }
  return JSON.stringify(value);
}

function statusIcon(status?: string) {
  if (status === "pass" || status === "ready") return <CheckCircle2Icon aria-hidden="true" className="size-3.5 text-emerald-500" />;
  if (status === "fail" || status === "configuration_error") return <XCircleIcon aria-hidden="true" className="size-3.5 text-destructive" />;
  if (status === "warn" || status === "disabled") return <AlertTriangleIcon aria-hidden="true" className="size-3.5 text-amber-500" />;
  return null;
}

function riskBadgeVariant(risk?: string): "default" | "secondary" | "destructive" | "outline" {
  if (risk === "high") return "destructive";
  if (risk === "medium") return "secondary";
  return "outline";
}

function formatTracePayload(entry: ToolTraceEntry) {
  const payload = entry.payload ?? {};
  const parts: string[] = [];
  for (const key of ["cwd", "duration_ms", "exit_code", "timeout", "status", "job_id", "gc_collected"]) {
    const value = payload[key];
    if (value !== undefined && value !== null && value !== "") {
      parts.push(`${key}=${formatTracePayloadValue(value)}`);
    }
  }
  if (Array.isArray(payload.args)) {
    parts.push(`args=${payload.args.map(String).join(" ")}`);
  }
  return parts.join(" · ");
}

function ToolTracePanel() {
  const [filter, setFilter] = useState<TraceFilter>("");
  const traceQuery = useToolTrace({ limit: 80, event: filter || null });
  const entries = traceQuery.entries;

  return (
    <section className="mb-5 rounded-lg border border-border bg-card p-3 shadow-sm" aria-labelledby="tools-trace-title">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ActivityIcon aria-hidden="true" className="size-4 text-primary" />
          <h2 id="tools-trace-title" className="text-sm font-semibold text-foreground">Runtime trace</h2>
          <Badge variant="outline">{traceQuery.response?.count ?? entries.length}</Badge>
          {traceQuery.response?.truncated ? <Badge variant="secondary">tail</Badge> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Trace event filter"
            className="h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground"
            onChange={(event) => setFilter(event.target.value as TraceFilter)}
            value={filter}
          >
            {TRACE_FILTERS.map((item) => (
              <option key={item.value || "all"} value={item.value}>{item.label}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void traceQuery.refetch()}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2 text-xs text-foreground transition hover:bg-muted"
          >
            <RefreshCwIcon aria-hidden="true" className={`size-3.5 ${traceQuery.isFetching ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>
      {traceQuery.isLoading ? (
        <p className="text-sm text-muted-foreground">Loading trace…</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">No trace entries.</p>
      ) : (
        <ol className="max-h-72 space-y-1 overflow-y-auto pr-1">
          {entries.map((entry, index) => {
            const payloadText = formatTracePayload(entry);
            return (
              <li key={`${entry.ts ?? "trace"}-${entry.event}-${index}`} className="rounded-md border border-border bg-background px-2 py-1.5">
                <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs">
                  <span className="font-mono text-muted-foreground">{entry.ts ?? "-"}</span>
                  <Badge variant="outline">{entry.event}</Badge>
                  {entry.tool ? <Badge variant="secondary">{entry.tool}</Badge> : null}
                </div>
                {payloadText ? <p className="mt-1 truncate text-xs text-muted-foreground" title={payloadText}>{payloadText}</p> : null}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

async function fetchToolRegistry(): Promise<ToolRegistryResponse> {
  try {
    return await getJSON<ToolRegistryResponse>("/api/tools/registry");
  } catch {
    return {};
  }
}

async function fetchSkills(): Promise<SkillsResponse> {
  try {
    return await getJSON<SkillsResponse>("/api/skills");
  } catch {
    return {};
  }
}

async function fetchMcp(): Promise<McpConfigResponse> {
  try {
    return await getJSON<McpConfigResponse>("/api/mcp/config");
  } catch {
    return {};
  }
}

async function fetchChannels(): Promise<ChannelsStatusResponse> {
  try {
    return await getJSON<ChannelsStatusResponse>("/api/channels/");
  } catch {
    return {};
  }
}

async function fetchPlugins(): Promise<PluginRegistryResponse> {
  try {
    return await getJSON<PluginRegistryResponse>("/api/plugins/registry");
  } catch {
    return {};
  }
}

async function fetchHooks(): Promise<HooksListResponse> {
  try {
    return await getJSON<HooksListResponse>("/api/hooks");
  } catch {
    return {};
  }
}

async function fetchDesktopControl(): Promise<DesktopControlStatusResponse> {
  try {
    return await getJSON<DesktopControlStatusResponse>("/api/tools/desktop-control/status");
  } catch {
    return {};
  }
}

function normalizeEntries(
  skills: SkillsResponse,
  mcp: McpConfigResponse,
  channels: ChannelsStatusResponse,
  plugins: PluginRegistryResponse,
  hooks: HooksListResponse,
  registry: ToolRegistryResponse,
  desktop: DesktopControlStatusResponse,
): ToolEntry[] {
  const entries: ToolEntry[] = [];

  for (const skill of skills.skills ?? []) {
    if (!skill?.name) continue;
    entries.push({
      id: `skill:${skill.name}`,
      name: skill.name,
      category: "skill",
      description: optionalText(skill.description),
      enabled: skill.enabled !== false,
      usage: `Load the skill file at skills/${skill.category ?? "custom"}/${skill.name}/SKILL.md then follow its workflow.`,
    });
  }

  const registryMcp = new Map((registry.mcp ?? []).filter((item) => item?.name).map((item) => [item.name!, item]));
  const mcpServers = mcp.mcp_servers ?? mcp.mcpServers ?? {};
  for (const [name, entry] of Object.entries(mcpServers)) {
    const transport = entry?.type ?? entry?.transport ?? "stdio";
    const target = entry?.url ?? entry?.command ?? "stdio";
    const enabled = entry?.enabled !== false && entry?.disabled !== true;
    const registryEntry = registryMcp.get(name);
    const status = registryEntry?.status ?? entry?.status;
    const failureReason = registryEntry?.failure_reason ?? entry?.status_reason;
    entries.push({
      id: `mcp:${name}`,
      name,
      category: "mcp",
      description: optionalText(entry?.description) ?? `Transport: ${transport} -> ${target}`,
      enabled,
      badge: status,
      status,
      failureReason,
      parameterCount: registryEntry?.tool_count,
      usage: `Smoke: ${status ?? "unknown"}; tools: ${registryEntry?.tool_count ?? 0}; registry visible: ${registryEntry?.registry_visible !== false}. ${failureReason ?? ""}`,
    });
  }

  for (const [name, ch] of Object.entries(channels.channels ?? {})) {
    entries.push({
      id: `channel:${name}`,
      name: ch?.platform_label ?? name,
      category: "channel",
      description: ch?.description,
      enabled: ch?.enabled === true && ch?.configured === true,
      usage: `Configure under Settings → Software Interfaces, then route chat through the ${name} adapter.`,
    });
  }

  for (const plugin of plugins.entries ?? []) {
    if (!plugin?.plugin_id) continue;
    entries.push({
      id: `plugin:${plugin.plugin_id}`,
      name: plugin.plugin_id,
      category: "plugin",
      description: plugin.source ? `Source: ${plugin.source}` : undefined,
      enabled: plugin.installed !== false && plugin.enabled !== false,
      usage: `Invoked automatically by the plugin runtime; manage under Settings → Plugins.`,
    });
  }

  for (const hook of hooks.hooks ?? []) {
    if (!hook?.name) continue;
    const triggers = (hook.triggers ?? [])
      .map((t) => t?.trigger)
      .filter(Boolean)
      .join(", ");
    entries.push({
      id: `hook:${hook.name}`,
      name: hook.name,
      category: "hook",
      description: triggers ? `Triggers: ${triggers}` : hook.description,
      enabled: hook.enabled !== false,
      usage: `Fires automatically on matching triggers; review definitions in the hooks registry.`,
    });
  }

  for (const tool of registry.builtin_tools ?? []) {
    if (!tool?.name) continue;
    const scope = tool.permission_scope ?? "sandbox";
    const parameterCount = Object.keys(tool.parameters ?? {}).length;
    entries.push({
      id: `builtin:${tool.name}`,
      name: tool.name,
      category: "builtin",
      description: optionalText(tool.description) ?? `Category: ${tool.category ?? "builtin"}`,
      enabled: true,
      badge: scope,
      riskLevel: tool.risk_level ?? "low",
      parameterCount,
      timeoutSeconds: tool.timeout_seconds ?? null,
      outputArtifacts: tool.output_artifacts ?? [],
      usage: `Permission: ${scope}; risk: ${tool.risk_level ?? "low"}; parameters: ${parameterCount}; timeout: ${tool.timeout_seconds ?? "runtime default"}; artifacts: ${(tool.output_artifacts ?? []).join(", ") || "none"}.`,
    });
  }

  const desktopEnabled = desktop.enabled === true;
  const desktopBadge = desktop.badge ?? "stub";
  const envFlag = desktop.env_flag ?? "BYTEBOT_COMPAT_ENABLED";
  const desktopNote =
    desktop.note ??
    "Observation-only stub. Returns not_implemented payloads for desktop actions.";
  for (const tool of desktop.tools ?? []) {
    if (!tool?.name) continue;
    entries.push({
      id: `desktop:${tool.name}`,
      name: tool.name,
      category: "desktop",
      description: tool.description ?? desktopNote,
      enabled: desktopEnabled,
      badge: desktopBadge,
      usage: `${desktopNote} Mount controlled by env ${envFlag} (default off). Use /api/browser-runtime/* for real automation.`,
    });
  }

  return entries;
}

export default function ToolsHubPage() {
  const { t, locale } = useI18n();
  const categoryLabel = useCallback(
    (cat: ToolEntry["category"]) =>
      cat === "desktop"
        ? DESKTOP_CATEGORY_LABEL_I18N[locale] ?? CATEGORY_LABELS.desktop
        : CATEGORY_LABELS[cat],
    [locale],
  );
  const [tab, setTab] = useState<HubTab>("tools");
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<"all" | ToolEntry["category"]>("all");

  const skillsQuery = useQuery({ queryKey: ["tools-hub", "skills"], queryFn: fetchSkills });
  const mcpQuery = useQuery({ queryKey: ["tools-hub", "mcp"], queryFn: fetchMcp });
  const channelsQuery = useQuery({ queryKey: ["tools-hub", "channels"], queryFn: fetchChannels });
  const pluginsQuery = useQuery({ queryKey: ["tools-hub", "plugins"], queryFn: fetchPlugins });
  const hooksQuery = useQuery({ queryKey: ["tools-hub", "hooks"], queryFn: fetchHooks });
  const registryQuery = useQuery({ queryKey: ["tools-hub", "registry"], queryFn: fetchToolRegistry });
  const desktopQuery = useQuery({
    queryKey: ["tools-hub", "desktop-control"],
    queryFn: fetchDesktopControl,
  });

  const isLoading =
    skillsQuery.isLoading ||
    mcpQuery.isLoading ||
    channelsQuery.isLoading ||
    pluginsQuery.isLoading ||
    hooksQuery.isLoading ||
    registryQuery.isLoading ||
    desktopQuery.isLoading;

  const entries = useMemo(
    () =>
      normalizeEntries(
        skillsQuery.data ?? {},
        mcpQuery.data ?? {},
        channelsQuery.data ?? {},
        pluginsQuery.data ?? {},
        hooksQuery.data ?? {},
        registryQuery.data ?? {},
        desktopQuery.data ?? {},
      ),
    [
      skillsQuery.data,
      mcpQuery.data,
      channelsQuery.data,
      pluginsQuery.data,
      hooksQuery.data,
      registryQuery.data,
      desktopQuery.data,
    ],
  );

  const registrySummary = registryQuery.data?.summary;
  const runtimeSummary = registryQuery.data?.runtime;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return entries.filter((entry) => {
      if (activeCategory !== "all" && entry.category !== activeCategory) return false;
      if (!q) return true;
      return (
        entry.name.toLowerCase().includes(q) ||
        (entry.description?.toLowerCase().includes(q) ?? false)
      );
    });
  }, [entries, query, activeCategory]);

  const grouped = useMemo(() => {
    const map: Record<string, ToolEntry[]> = {};
    for (const entry of filtered) {
      const bucket = categoryLabel(entry.category);
      map[bucket] ??= [];
      map[bucket].push(entry);
    }
    return map;
  }, [filtered, categoryLabel]);

  const totalByCategory = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const entry of entries) counts[entry.category] = (counts[entry.category] ?? 0) + 1;
    return counts;
  }, [entries]);

  const hubTitle = t.settings?.tools?.title ?? "Tools Hub";
  const hubDescription =
    t.settings?.tools?.description ??
    "Unified catalogue of every installed skill, MCP server, software interface, plugin, and hook.";

  const tabDefs: { id: HubTab; label: string; icon: typeof WrenchIcon }[] = [
    { id: "tools", label: "Tools", icon: WrenchIcon },
    { id: "plugins", label: "Plugins", icon: PlugIcon },
    { id: "hooks", label: "Hooks", icon: WaypointsIcon },
  ];

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="border-b border-border bg-background px-6 pt-4">
        <header className="mb-3">
          <div className="flex items-center gap-2">
            <WrenchIcon aria-hidden="true" className="size-5 text-primary" />
            <h1 className="text-lg font-semibold text-foreground">{hubTitle}</h1>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{hubDescription}</p>
        </header>
        <div role="tablist" aria-label="Tools Hub Sections" className="-mb-px flex flex-wrap gap-1">
          {tabDefs.map(({ id, label, icon: Icon }) => {
            const active = tab === id;
            return (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setTab(id)}
                className={`flex items-center gap-1.5 rounded-t-md border border-b-0 px-3 py-1.5 text-sm transition ${
                  active
                    ? "border-border bg-background font-medium text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                <Icon className="size-3.5" aria-hidden="true" />
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {tab === "plugins" ? (
        <PluginsConfigPage />
      ) : tab === "hooks" ? (
        <HooksSettingsPage />
      ) : (
      <div className="p-6">
      <ToolTracePanel />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <SearchIcon aria-hidden="true" className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Search tools"
            className="pl-9"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search tools by name or description"
            type="search"
            value={query}
          />
        </div>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by category">
          <button
            type="button"
            onClick={() => setActiveCategory("all")}
            className={`rounded-md border px-2.5 py-1 text-xs transition ${
              activeCategory === "all"
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-background text-foreground hover:bg-muted"
            }`}
          >
            All ({entries.length})
          </button>
          {CATEGORY_ORDER.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setActiveCategory(cat)}
              className={`rounded-md border px-2.5 py-1 text-xs transition ${
                activeCategory === cat
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-background text-foreground hover:bg-muted"
              }`}
            >
              {categoryLabel(cat)} ({totalByCategory[cat] ?? 0})
            </button>
          ))}
        </div>
      </div>

      {registrySummary ? (
        <div className="mb-4 flex flex-wrap gap-2 text-xs text-muted-foreground" aria-label="Tool registry summary">
          <Badge variant="outline">MCP {registrySummary.mcp_enabled ?? 0}/{registrySummary.mcp_total ?? 0}</Badge>
          <Badge variant="outline">Skills {registrySummary.skills_enabled ?? 0}/{registrySummary.skills_total ?? 0}</Badge>
          <Badge variant="outline">Plugins {registrySummary.plugins_enabled ?? 0}/{registrySummary.plugins_total ?? 0}</Badge>
          <Badge variant="outline">Built-ins {registrySummary.builtin_tools_total ?? 0}</Badge>
          {runtimeSummary?.default_model ? (
            <Badge variant="secondary">Model {runtimeSummary.default_model}</Badge>
          ) : null}
        </div>
      ) : null}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading tools…</p>
      ) : Object.keys(grouped).length === 0 ? (
        <p className="text-sm text-muted-foreground">No tools match the current filter.</p>
      ) : (
        <div className="space-y-6">
          {CATEGORY_ORDER.map((cat) => {
            const label = categoryLabel(cat);
            const items = grouped[label];
            if (!items?.length) return null;
            return (
              <section key={cat} aria-labelledby={`tools-${cat}`}>
                <h2
                  id={`tools-${cat}`}
                  className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground"
                >
                  {label}
                  <Badge variant="outline">{items.length}</Badge>
                </h2>
                <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                  {items.map((entry) => (
                    <li
                      key={entry.id}
                      data-testid={`tools-hub-item-${entry.id}`}
                      className="rounded-lg border border-border bg-card p-3 shadow-sm"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-foreground" title={entry.name}>
                            {entry.name}
                          </p>
                          {entry.description ? (
                            <p className="mt-0.5 line-clamp-3 text-xs text-muted-foreground">
                              {entry.description}
                            </p>
                          ) : null}
                        </div>
                        <div className="flex flex-col items-end gap-1">
                          {entry.status ? (
                            <span className="flex items-center gap-1 text-xs text-muted-foreground">
                              {statusIcon(entry.status)}
                              {entry.status}
                            </span>
                          ) : null}
                          {entry.riskLevel ? (
                            <Badge variant={riskBadgeVariant(entry.riskLevel)} className="uppercase tracking-wide">
                              <ShieldAlertIcon aria-hidden="true" className="mr-1 size-3" />
                              {entry.riskLevel}
                            </Badge>
                          ) : null}
                          {entry.badge ? (
                            <Badge variant="outline" className="uppercase tracking-wide">
                              {entry.badge}
                            </Badge>
                          ) : null}
                          {entry.enabled === false ? (
                            <Badge variant="secondary">disabled</Badge>
                          ) : (
                            <Badge variant="default">enabled</Badge>
                          )}
                        </div>
                      </div>
                      {entry.failureReason ? (
                        <p className="mt-2 flex items-start gap-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs text-amber-700 dark:text-amber-300">
                          <AlertTriangleIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
                          {entry.failureReason}
                        </p>
                      ) : null}
                      {(entry.parameterCount !== undefined || entry.timeoutSeconds || entry.outputArtifacts?.length) ? (
                        <div className="mt-2 flex flex-wrap gap-1 text-xs text-muted-foreground">
                          {entry.parameterCount !== undefined ? <Badge variant="outline">params {entry.parameterCount}</Badge> : null}
                          {entry.timeoutSeconds ? <Badge variant="outline">timeout {entry.timeoutSeconds}s</Badge> : null}
                          {entry.outputArtifacts?.length ? <Badge variant="outline">artifacts</Badge> : null}
                        </div>
                      ) : null}
                      {entry.usage ? (
                        <details className="mt-2">
                          <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                            How to use
                          </summary>
                          <p className="mt-1 text-xs text-muted-foreground">{entry.usage}</p>
                        </details>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}

      <footer className="mt-6 flex items-center gap-1 text-xs text-muted-foreground">
        <ExternalLinkIcon aria-hidden="true" className="size-3.5" />
        Detailed docs live in <code>project_docs/TOOLS_CATALOG.md</code>.
      </footer>
      </div>
      )}
    </div>
  );
}
