"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BoxesIcon,
  CheckCircleIcon,
  DownloadIcon,
  PlusIcon,
  PlugIcon,
  Trash2Icon,
  XCircleIcon,
} from "lucide-react";
import { useMemo, useState, useEffect } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/core/i18n/hooks";
import {
  disablePlugin,
  enablePlugin,
  installPlugin,
  loadPluginCapabilities,
  loadPluginRegistry,
  uninstallPlugin,
} from "@/core/plugins/api";
import type { PluginRegistryEntry } from "@/core/plugins/types";

export default function PluginsConfigPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<string>("all");
  const [mounted, setMounted] = useState(false);
  const [installId, setInstallId] = useState("");
  const [isInstallOpen, setIsInstallOpen] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  const { data: capData, isLoading: capLoading } = useQuery({
    queryKey: ["plugin-capabilities"],
    queryFn: () => loadPluginCapabilities(),
  });

  const { data: regData, isLoading: regLoading } = useQuery({
    queryKey: ["plugin-registry"],
    queryFn: () => loadPluginRegistry(),
  });

  const { mutate: togglePlugin } = useMutation({
    mutationFn: async ({ pluginId, enabled }: { pluginId: string; enabled: boolean }) => {
      if (enabled) { await enablePlugin(pluginId); } else { await disablePlugin(pluginId); }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["plugin-capabilities"] });
      void queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      void queryClient.invalidateQueries({ queryKey: ["tools-hub"] });
    },
  });

  const { mutate: removePlugin } = useMutation({
    mutationFn: async ({ pluginId }: { pluginId: string }) => { await uninstallPlugin(pluginId); },
    onSuccess: () => {
      toast.success("Plugin uninstalled.");
      void queryClient.invalidateQueries({ queryKey: ["plugin-capabilities"] });
      void queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      void queryClient.invalidateQueries({ queryKey: ["tools-hub"] });
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Failed to uninstall plugin.");
    },
  });

  const installMut = useMutation({
    mutationFn: async (pluginId: string) => {
      await installPlugin({ plugin_id: pluginId, enable_after_install: true });
    },
    onSuccess: () => {
      toast.success("Plugin installed.");
      setInstallId("");
      setIsInstallOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["plugin-capabilities"] });
      void queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      void queryClient.invalidateQueries({ queryKey: ["tools-hub"] });
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Failed to install plugin.");
    },
  });

  const registryMap = useMemo(() => {
    const map: Record<string, PluginRegistryEntry> = {};
    for (const e of regData?.entries ?? []) { map[e.plugin_id] = e; }
    return map;
  }, [regData?.entries]);

  const filteredPlugins = useMemo(() => {
    const plugins = capData?.plugins ?? [];
    if (filter === "all") return plugins;
    return plugins.filter((p) => p.category === filter);
  }, [capData?.plugins, filter]);

  const isLoading = capLoading || regLoading;

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <PlugIcon className="size-5 text-primary" />
              <h1 className="text-lg font-semibold text-foreground">{t.sidebar.plugins}</h1>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{t.sidebar.pluginsDesc}</p>
          </div>
          <Button size="sm" onClick={() => setIsInstallOpen(true)}>
            <PlusIcon className="size-4" />
            Add plugin
          </Button>
        </div>
      </header>

      {isInstallOpen ? (
      <div className="octo-panel mb-6 rounded-[1.5rem] p-5">
        <div className="mb-3">
          <div className="text-sm font-medium text-foreground">Install Plugin</div>
          <p className="text-xs text-muted-foreground">
            Install a plugin by its identifier from the registry.
          </p>
        </div>
        <div className="flex gap-3">
          <label className="flex-1 space-y-1">
            <span className="text-xs font-medium text-muted-foreground">Plugin ID</span>
            <Input value={installId} onChange={(e) => setInstallId(e.target.value)} placeholder="e.g. code-review" />
          </label>
        </div>
        <div className="mt-4">
          <Button size="sm" disabled={!installId.trim() || installMut.isPending} onClick={() => installMut.mutate(installId.trim())}>
            <DownloadIcon className="size-4" />Install
          </Button>
          <Button size="sm" variant="outline" className="ml-2" onClick={() => setIsInstallOpen(false)}>
            Close
          </Button>
        </div>
      </div>
      ) : null}

      {mounted && (
        <div aria-label="Plugin category" className="mb-4 flex flex-wrap gap-2" role="group">
          {([
            ["all", t.sidebar.allPlugins],
            ["engineering", t.sidebar.engineering],
            ["review", t.sidebar.review],
            ["runtime", t.sidebar.runtime],
            ["integration", t.sidebar.integration],
          ] as const).map(([value, label]) => (
            <Button
              aria-pressed={filter === value}
              key={value}
              onClick={() => setFilter(value)}
              size="sm"
              type="button"
              variant={filter === value ? "default" : "outline"}
            >
              {label}
            </Button>
          ))}
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t.common.loading}</p>
      ) : filteredPlugins.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <BoxesIcon className="mb-3 size-10 opacity-30" />
          <p className="text-sm">{t.sidebar.noPlugins}</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filteredPlugins.map((plugin) => {
            const entry = registryMap[plugin.plugin_id];
            return (
              <div key={plugin.plugin_id} className="octo-panel octo-management-card flex min-w-0 flex-col justify-between rounded-[1.5rem] p-3 transition-shadow hover:translate-y-[-1px] hover:shadow-[3px_3px_7px_var(--neu-dark-strong),_-3px_-3px_7px_var(--neu-light-strong)]">
                <div className="mb-3">
                  <div className="flex items-start justify-between gap-2">
                    <h2 className="min-w-0 break-words text-sm font-medium text-foreground">{plugin.display_name}</h2>
                    <div className="octo-card-actions">
                      {entry?.installed ? (
                        <Button
                          aria-label={`Delete ${plugin.display_name}`}
                          size="icon"
                          variant="ghost"
                          className="octo-card-action"
                          title="Delete"
                          onClick={() => {
                            if (window.confirm(`Uninstall plugin "${plugin.display_name}"?`)) {
                              removePlugin({ pluginId: plugin.plugin_id });
                            }
                          }}
                        >
                          <Trash2Icon className="size-3.5 text-muted-foreground hover:text-destructive" />
                        </Button>
                      ) : null}
                    </div>
                  </div>
                  <p className="mt-1 break-words line-clamp-3 text-xs text-muted-foreground">{plugin.manifest?.description ?? ""}</p>
                  {plugin.manifest?.commands && plugin.manifest.commands.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {plugin.manifest.commands.map((cmd) => (
                        <Badge key={cmd.command_id} variant="secondary" className="max-w-full break-all text-[10px]">{cmd.title}</Badge>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge variant="outline" className="text-[10px]">{plugin.category}</Badge>
                    <Badge
                      variant="outline"
                      className={plugin.enabled ? "gap-1 border-green-500/30 text-[10px] text-green-600" : "gap-1 border-muted text-[10px] text-muted-foreground"}
                    >
                      {plugin.enabled ? <><CheckCircleIcon className="size-3" /> Active</> : <><XCircleIcon className="size-3" /> Off</>}
                    </Badge>
                    {entry?.installed ? (
                      <Badge variant="secondary" className="text-[10px]">v{entry.installed_version}</Badge>
                    ) : null}
                  </div>
                  <Switch
                    aria-label={`Enable ${plugin.display_name}`}
                    checked={plugin.enabled}
                    onCheckedChange={(checked) => togglePlugin({ pluginId: plugin.plugin_id, enabled: checked })}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
