"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLinkIcon, SearchIcon, WrenchIcon } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { getJSON } from "@/core/api/http";
import { useI18n } from "@/core/i18n/hooks";

interface ToolEntry {
  id: string;
  name: string;
  category: "skill" | "mcp" | "channel" | "plugin" | "hook" | "desktop";
  description?: string;
  usage?: string;
  enabled?: boolean;
  badge?: string;
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
}

interface McpConfigResponse {
  mcp_servers?: Record<string, McpServerEntry>;
  mcpServers?: Record<string, McpServerEntry>;
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

const CATEGORY_LABELS: Record<ToolEntry["category"], string> = {
  skill: "Skills",
  mcp: "MCP Servers",
  channel: "Channels",
  plugin: "Plugins",
  hook: "Hooks",
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
  "plugin",
  "hook",
  "desktop",
];

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

  const mcpServers = mcp.mcp_servers ?? mcp.mcpServers ?? {};
  for (const [name, entry] of Object.entries(mcpServers)) {
    const transport = entry?.type ?? entry?.transport ?? "stdio";
    const target = entry?.url ?? entry?.command ?? "stdio";
    const enabled = entry?.enabled !== false && entry?.disabled !== true;
    entries.push({
      id: `mcp:${name}`,
      name,
      category: "mcp",
      description: optionalText(entry?.description) ?? `Transport: ${transport} ? ${target}`,
      enabled,
      usage: `Invoke via MCP client; ensure server is enabled in Settings → MCP.`,
    });
  }

  for (const [name, ch] of Object.entries(channels.channels ?? {})) {
    entries.push({
      id: `channel:${name}`,
      name: ch?.platform_label ?? name,
      category: "channel",
      description: ch?.description,
      enabled: ch?.enabled === true && ch?.configured === true,
      usage: `Configure under Settings → Channels, then route chat through the ${name} adapter.`,
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
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<"all" | ToolEntry["category"]>("all");

  const skillsQuery = useQuery({ queryKey: ["tools-hub", "skills"], queryFn: fetchSkills });
  const mcpQuery = useQuery({ queryKey: ["tools-hub", "mcp"], queryFn: fetchMcp });
  const channelsQuery = useQuery({ queryKey: ["tools-hub", "channels"], queryFn: fetchChannels });
  const pluginsQuery = useQuery({ queryKey: ["tools-hub", "plugins"], queryFn: fetchPlugins });
  const hooksQuery = useQuery({ queryKey: ["tools-hub", "hooks"], queryFn: fetchHooks });
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
    desktopQuery.isLoading;

  const entries = useMemo(
    () =>
      normalizeEntries(
        skillsQuery.data ?? {},
        mcpQuery.data ?? {},
        channelsQuery.data ?? {},
        pluginsQuery.data ?? {},
        hooksQuery.data ?? {},
        desktopQuery.data ?? {},
      ),
    [
      skillsQuery.data,
      mcpQuery.data,
      channelsQuery.data,
      pluginsQuery.data,
      hooksQuery.data,
      desktopQuery.data,
    ],
  );

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
    "Unified catalogue of every installed skill, MCP server, channel, plugin, and hook.";

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6">
        <div className="flex items-center gap-2">
          <WrenchIcon aria-hidden="true" className="size-5 text-primary" />
          <h1 className="text-lg font-semibold text-foreground">{hubTitle}</h1>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">{hubDescription}</p>
      </header>

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
  );
}
