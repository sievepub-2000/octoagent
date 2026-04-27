"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangleIcon, BotIcon, BoxesIcon, CableIcon, CpuIcon, SparklesIcon, WorkflowIcon } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";

import { useAgents } from "@/core/agents/hooks";
import { useI18n } from "@/core/i18n/hooks";
import { useMCPConfig } from "@/core/mcp/hooks";
import { useModels } from "@/core/models/hooks";
import { useNotification } from "@/core/notification/hooks";
import { loadPluginCapabilities } from "@/core/plugins/api";
import { useRuntimeLongRunningHealth } from "@/core/runtime";
import { useSkills } from "@/core/skills/hooks";
import { useTaskWorkspaces } from "@/core/task-workspaces/hooks";

type StatusItem = {
  id: string;
  label: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
};

export function SystemStatusBar() {
  const { t } = useI18n();
  const notifiedAlertSignature = useRef("");
  const { models } = useModels();
  const { agents } = useAgents();
  const { workspaces } = useTaskWorkspaces();
  const { skills } = useSkills();
  const { config: mcpConfig } = useMCPConfig();
  const { health } = useRuntimeLongRunningHealth({ refetchInterval: 30_000 });
  const { showNotification } = useNotification();
  const { data: pluginData } = useQuery({
    queryKey: ["plugin-capabilities"],
    queryFn: loadPluginCapabilities,
    refetchOnWindowFocus: false,
  });
  const mcpServers = Object.values(mcpConfig?.mcp_servers ?? {});
  const runtimeAlerts = useMemo(
    () => health?.snapshot.alerts ?? [],
    [health?.snapshot.alerts],
  );
  const criticalAlerts = runtimeAlerts.filter((alert) => alert.severity === "critical");

  useEffect(() => {
    if (!runtimeAlerts.length) {
      notifiedAlertSignature.current = "";
      return;
    }
    const signature = runtimeAlerts
      .map((alert) => `${alert.severity}:${alert.code}:${String(alert.value)}`)
      .join("|");
    if (signature === notifiedAlertSignature.current) {
      return;
    }
    notifiedAlertSignature.current = signature;
    showNotification("OctoAgent runtime health alert", {
      body: runtimeAlerts.map((alert) => `${alert.severity}: ${alert.code}`).join(", "),
      tag: "octoagent-runtime-health",
    });
  }, [runtimeAlerts, showNotification]);

  const items: StatusItem[] = [
    { id: "agents", icon: BotIcon, label: t.sidebar.agents, value: agents.length },
    { id: "models", icon: CpuIcon, label: t.sidebar.models, value: models.length },
    { id: "workflows", icon: WorkflowIcon, label: t.sidebar.workflows, value: workspaces.length },
    { id: "skills", icon: SparklesIcon, label: t.sidebar.skills, value: skills.length },
    { id: "mcp", icon: CableIcon, label: t.sidebar.mcp, value: mcpServers.length },
    { id: "plugins", icon: BoxesIcon, label: t.sidebar.plugins, value: pluginData?.plugins.length ?? 0 },
    { id: "runtime-alerts", icon: AlertTriangleIcon, label: "Runtime", value: runtimeAlerts.length },
  ] as const;

  return (
    <div className="border-b border-border/60 bg-background/84 px-4 py-2.5 backdrop-blur-md">
      <div className="octo-chip flex flex-wrap items-center gap-3 rounded-[1rem] px-3 py-2">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.id}
              className="flex items-center gap-1.5"
            >
              <div className={`flex size-6 shrink-0 items-center justify-center rounded-[0.8rem] ${item.id === "runtime-alerts" && runtimeAlerts.length ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary"}`}>
                <Icon className="size-3.5" />
              </div>
              <div className="flex min-w-0 items-baseline gap-1.5">
                <div className="truncate text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                  {item.label}
                </div>
                <span className={item.id === "runtime-alerts" && criticalAlerts.length ? "text-[13px] font-semibold leading-none text-destructive" : "text-[13px] font-semibold leading-none text-foreground"}>{item.value}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
