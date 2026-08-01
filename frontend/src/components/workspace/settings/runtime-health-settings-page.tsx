"use client";

import {
  ActivityIcon,
  AlertTriangleIcon,
  DatabaseIcon,
  HardDriveIcon,
  MemoryStickIcon,
  PlayIcon,
  RefreshCcwIcon,
  WorkflowIcon,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/core/i18n/hooks";
import { getSurfaceCopy } from "@/core/i18n/surface-copy";
import {
  useRunRuntimeMaintenance,
  useRuntimeLongRunningHealth,
  useRuntimeMaintenanceStatus,
} from "@/core/runtime";

import { SettingsSection } from "./settings-section";

function formatNumber(value: unknown, suffix = "") {
  return typeof value === "number" ? `${value.toLocaleString()}${suffix}` : "-";
}
function alertVariant(severity: string) {
  if (severity === "critical") return "destructive" as const;
  if (severity === "warning") return "outline" as const;
  return "secondary" as const;
}

export function RuntimeHealthSettingsPage() {
  const { t, locale } = useI18n();
  const copy = getSurfaceCopy(locale).runtime;
  const { health, isLoading, error, refetch } = useRuntimeLongRunningHealth();
  const { maintenance, refetch: refetchMaintenance } = useRuntimeMaintenanceStatus();
  const runMaintenance = useRunRuntimeMaintenance();
  const snapshot = health?.snapshot;
  const alerts = snapshot?.alerts ?? [];
  const pools = Object.entries(snapshot?.worker_isolation?.pools ?? {});
  const overviewCards: Array<{ label: string; value: string; icon: LucideIcon }> = [
    { label: copy.memory, value: formatNumber(snapshot?.memory?.available_gb, " GB"), icon: MemoryStickIcon },
    { label: copy.diskFree, value: formatNumber(snapshot?.disk?.free_gb, " GB"), icon: HardDriveIcon },
    { label: copy.checkpoints, value: formatNumber(snapshot?.langgraph_state?.checkpoint_count), icon: WorkflowIcon },
    { label: copy.loopLatency, value: formatNumber(snapshot?.event_loop?.latency_ms, " ms"), icon: ActivityIcon },
  ];

  async function handleRunMaintenance() {
    try {
      await runMaintenance.mutateAsync();
      await Promise.all([refetch(), refetchMaintenance()]);
      toast.success(copy.maintenanceCompleted);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <SettingsSection title={copy.title} description={copy.description}>
      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-48 w-full rounded-xl" />
        </div>
      ) : error || !snapshot ? (
        <Card variant="status" className="border-l-destructive">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangleIcon className="size-4" />
              {copy.unavailable}
            </CardTitle>
          </CardHeader>
        </Card>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-2">
              <Badge variant={alerts.length ? "outline" : "secondary"}>
                {alerts.length ? `${alerts.length} ${copy.alerts}` : copy.steady}
              </Badge>
              <Badge variant="outline">
                {copy.maintenance} {maintenance?.running ? copy.running : copy.stopped}
              </Badge>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => void Promise.all([refetch(), refetchMaintenance()])}
              >
                <RefreshCcwIcon className="size-4" />
                {t.settings.system.refresh}
              </Button>
              <Button size="sm" disabled={runMaintenance.isPending} onClick={handleRunMaintenance}>
                <PlayIcon className="size-4" />
                {runMaintenance.isPending ? copy.running : copy.runMaintenance}
              </Button>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {overviewCards.map(({ label, value, icon: Icon }) => (
              <Card variant="compact" key={label}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <Icon className="size-4 text-primary" />
                    {label}
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-2xl font-semibold">{value}</CardContent>
              </Card>
            ))}
          </div>

          {alerts.length ? (
            <Card variant="compact">
              <CardHeader><CardTitle>{copy.alerts}</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {alerts.map((alert) => (
                  <div key={alert.code} className="rounded-xl border border-border/50 bg-background/60 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={alertVariant(alert.severity)}>{alert.severity}</Badge>
                      <span className="text-sm font-medium text-foreground">{alert.code}</span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{alert.message}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          <div className="grid gap-3 md:grid-cols-2">
            <Card variant="compact">
              <CardHeader>
                <CardTitle>{copy.workerIsolation}</CardTitle>
                <CardAction>
                  <Badge variant="outline">{copy.queued} {snapshot.worker_isolation?.total_queued ?? 0}</Badge>
                </CardAction>
              </CardHeader>
              <CardContent className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                {pools.map(([name, pool]) => (
                  <div key={name} className="rounded-xl border border-border/50 bg-background/60 p-3 text-xs text-muted-foreground">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-foreground">{name}</span>
                      <Badge variant="secondary">{copy.limit} {pool.limit}</Badge>
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-2">
                      <span>{copy.active} {pool.active}</span>
                      <span>{copy.queued} {pool.queued}</span>
                      <span>{copy.done} {pool.completed}</span>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card variant="compact">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <DatabaseIcon className="size-4 text-primary" />
                  {copy.maintenance}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs text-muted-foreground">
                <p>{copy.interval}: {maintenance?.interval_seconds ?? "-"}s</p>
                <p className="break-all">
                  {copy.lastRun}: {maintenance?.last_run ? JSON.stringify(maintenance.last_run) : copy.none}
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </SettingsSection>
  );
}
