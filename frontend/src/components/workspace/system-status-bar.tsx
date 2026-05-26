"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangleIcon, BotIcon, BoxesIcon, CableIcon, CpuIcon, SparklesIcon, WorkflowIcon } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef } from "react";

import { useAgents } from "@/core/agents/hooks";
import { getJSON } from "@/core/api/http";
import { useI18n } from "@/core/i18n/hooks";
import { useNotification } from "@/core/notification/hooks";
import { useRuntimeLongRunningHealth } from "@/core/runtime";
import { useTaskWorkspaces } from "@/core/task-workspaces/hooks";

const SystemEventsButton = dynamic(
  () => import("@/components/workspace/system-events/system-events-button").then((m) => m.SystemEventsButton),
  { ssr: false },
);

type StatusItem = {
  id: string;
  label: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
};

type ToolRegistrySummaryResponse = {
  summary?: {
    mcp_total?: number;
    skills_total?: number;
    plugins_total?: number;
  };
  runtime?: {
    total_models?: number;
  };
};

function loadToolRegistrySummary() {
  return getJSON<ToolRegistrySummaryResponse>("/api/tools/registry");
}

export function SystemStatusBar() {
  const { t } = useI18n();
  const notifiedAlertSignature = useRef("");
  const { agents } = useAgents();
  const { workspaces } = useTaskWorkspaces();
  const { health } = useRuntimeLongRunningHealth({ refetchInterval: 30_000 });
  const { showNotification } = useNotification();
  const { data: registry } = useQuery({
    queryKey: ["tool-registry-summary"],
    queryFn: loadToolRegistrySummary,
    refetchOnWindowFocus: false,
  });
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
    { id: "models", icon: CpuIcon, label: t.sidebar.models, value: registry?.runtime?.total_models ?? 0 },
    { id: "workflows", icon: WorkflowIcon, label: t.sidebar.workflows, value: workspaces.length },
    { id: "skills", icon: SparklesIcon, label: t.sidebar.skills, value: registry?.summary?.skills_total ?? 0 },
    { id: "mcp", icon: CableIcon, label: t.sidebar.mcp, value: registry?.summary?.mcp_total ?? 0 },
    { id: "plugins", icon: BoxesIcon, label: t.sidebar.plugins, value: registry?.summary?.plugins_total ?? 0 },
    { id: "runtime-alerts", icon: AlertTriangleIcon, label: t.systemEvents.runtimeAlerts, value: runtimeAlerts.length },
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
        <span aria-hidden className="mx-1 select-none text-muted-foreground/60">|</span>
        <SystemEventsButton />
      </div>
    </div>
  );
}
