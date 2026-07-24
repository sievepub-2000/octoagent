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
  useRuntimeRunRecords,
} from "@/core/runtime";

import { SettingsSection } from "./settings-section";

function formatNumber(value: unknown, suffix = "") {
  if (typeof value !== "number") return "-";
  return `${value.toLocaleString()}${suffix}`;
}

function formatScalar(value: unknown, fallback = "-") {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function alertVariant(severity: string) {
  if (severity === "critical") return "destructive" as const;
  if (severity === "warning") return "outline" as const;
  return "secondary" as const;
}

export function RuntimeHealthSettingsPage() {
  const { locale, t } = useI18n();
  const copy = getSurfaceCopy(locale).runtime;
  const { health, isLoading, error, refetch } = useRuntimeLongRunningHealth();
  const { maintenance, refetch: refetchMaintenance } = useRuntimeMaintenanceStatus();
  const { runRecords, refetch: refetchRunRecords } = useRuntimeRunRecords({ limit: 5 });
  const runMaintenance = useRunRuntimeMaintenance();
  const snapshot = health?.snapshot;
  const alerts = snapshot?.alerts ?? [];
  const pools = Object.entries(snapshot?.worker_isolation?.pools ?? {});
  const runRecordSummary = runRecords?.summary ?? {};

  async function handleRunMaintenance() {
    try {
      await runMaintenance.mutateAsync();
      await refetch();
      await refetchMaintenance();
      toast.success(copy.maintenanceCompleted);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <SettingsSection
      title={copy.title}
      description={copy.description}
    >
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
                onClick={() => {
                  void refetch();
                  void refetchMaintenance();
                  void refetchRunRecords();
                }}
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
            <Card variant="compact">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <MemoryStickIcon className="size-4 text-primary" />
                  {copy.memory}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">
                {formatNumber(snapshot.memory?.available_gb, " GB")}
              </CardContent>
            </Card>
            <Card variant="compact">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <HardDriveIcon className="size-4 text-primary" />
                  {copy.diskFree}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">
                {formatNumber(snapshot.disk?.free_gb, " GB")}
              </CardContent>
            </Card>
            <Card variant="compact">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <WorkflowIcon className="size-4 text-primary" />
                  {copy.checkpoints}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">
                {formatNumber(snapshot.langgraph_state?.checkpoint_count)}
              </CardContent>
            </Card>
            <Card variant="compact">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <ActivityIcon className="size-4 text-primary" />
                  {copy.loopLatency}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">
                {formatNumber(snapshot.event_loop?.latency_ms, " ms")}
              </CardContent>
            </Card>
          </div>

          {alerts.length ? (
            <Card variant="compact">
              <CardHeader>
                <CardTitle>{copy.alerts}</CardTitle>
              </CardHeader>
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

          <div className="grid gap-3 md:grid-cols-3">
          <Card variant="compact">
            <CardHeader>
              <CardTitle>{copy.workerIsolation}</CardTitle>
              <CardAction>
                <Badge variant="outline">
                  {copy.queued} {snapshot.worker_isolation?.total_queued ?? 0}
                </Badge>
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
              <p className="break-all">{copy.lastRun}: {maintenance?.last_run ? JSON.stringify(maintenance.last_run) : copy.none}</p>
            </CardContent>
          </Card>

          <Card variant="compact">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ActivityIcon className="size-4 text-primary" />
                {copy.runRecords}
              </CardTitle>
              <CardAction>
                <Badge variant="outline">
                  {Number(runRecords?.summary?.total ?? 0).toLocaleString()} {copy.recent}
                </Badge>
              </CardAction>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-muted-foreground">
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <span>{copy.failed} {formatScalar(runRecordSummary.failed, "0")}</span>
                <span>{copy.fallback} {formatScalar(runRecordSummary.fallback_used, "0")}</span>
                <span>{copy.toolErrors} {formatScalar(runRecordSummary.tool_failures, "0")}</span>
                <span>{copy.approval} {formatScalar(runRecordSummary.approval_blocked, "0")}</span>
              </div>
              {(runRecords?.records ?? []).length > 0 ? (
                <div className="space-y-2">
                  {(runRecords?.records ?? []).map((record) => (
                    <div
                      className="rounded-xl border border-border/50 bg-background/60 p-3"
                      key={String(record.record_id ?? record.stored_at)}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-medium text-foreground">
                          {formatScalar(record.thread_id, copy.unknownThread)}
                        </span>
                        <Badge variant="secondary">
                          {formatScalar((record.final_evaluation as Record<string, unknown> | undefined)?.status, copy.unknown)}
                        </Badge>
                      </div>
                      <p className="mt-1 truncate">
                        {formatScalar((record.instruction_contract as Record<string, unknown> | undefined)?.intent, copy.general)}
                        {" · "}
                        {formatScalar((record.model as Record<string, unknown> | undefined)?.active_model, copy.modelUnknown)}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p>{copy.noRecords}</p>
              )}
            </CardContent>
          </Card>
          </div>
        </div>
      )}
    </SettingsSection>
  );
}
