"use client";

import {
  DownloadIcon,
  RefreshCwIcon,
  ShieldCheckIcon,
  ShieldEllipsisIcon,
  WrenchIcon,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/core/i18n/hooks";
import {
  useExportSystemGuardSnapshots,
  useRunSystemGuardRepair,
  useSystemGuardStatus,
  type SystemGuardExportResponse,
  type SystemGuardSnapshot,
} from "@/core/runtime";

import { SettingsSection } from "./settings-section";

type GuardIssue = {
  code?: string;
  severity?: string;
  message?: string;
  auto_repairable?: boolean;
  metadata?: Record<string, unknown>;
};

function formatTimestamp(value?: string) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatJson(value: unknown) {
  if (!value || (typeof value === "object" && Object.keys(value).length === 0))
    return "{}";
  return JSON.stringify(value, null, 2);
}

function snapshotIssueCount(snapshot?: SystemGuardSnapshot | null) {
  const issues = snapshot?.state?.issues;
  return Array.isArray(issues) ? issues.length : 0;
}

function snapshotIssues(snapshot?: SystemGuardSnapshot | null): GuardIssue[] {
  const issues = snapshot?.state?.issues;
  return Array.isArray(issues) ? (issues as GuardIssue[]) : [];
}

function badgeVariantForSeverity(severity?: string) {
  if (severity === "critical") return "destructive" as const;
  if (severity === "warning") return "outline" as const;
  return "secondary" as const;
}

function downloadExport(payload: SystemGuardExportResponse) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `system-guard-export-${payload.generated_at.replaceAll(":", "-")}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function SystemGuardSettingsPage() {
  const { t } = useI18n();
  const g = t.settings.systemGuard;
  const { systemGuard, isLoading, error, refetch } = useSystemGuardStatus();
  const repair = useRunSystemGuardRepair();
  const exportSnapshots = useExportSystemGuardSnapshots();

  function repairActionSummary(repairReport: unknown) {
    const builtin = (repairReport as { builtin?: { actions?: string[] } } | null)
      ?.builtin;
    const actions = builtin?.actions ?? [];
    if (!actions.length) return g.noBuiltinActions;
    return actions.join(", ");
  }

  async function handleRepair(advisoryOnly: boolean) {
    try {
      const result = await repair.mutateAsync({ advisory_only: advisoryOnly });
      toast.success(
        advisoryOnly
          ? g.advisoryGenerated
          : result.ok
            ? g.repairFinished
            : g.repairWithIssues,
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleExport() {
    try {
      const payload = await exportSnapshots.mutateAsync(20);
      downloadExport(payload);
      toast.success(g.exportDownloaded);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <SettingsSection
      title={g.title}
      description={g.description}
    >
      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-48 w-full rounded-xl" />
        </div>
      ) : error || !systemGuard ? (
        <Card variant="status" className="border-l-destructive">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <ShieldEllipsisIcon className="size-4" />
              {g.unavailable}
            </CardTitle>
            <CardDescription>
              {error instanceof Error
                ? error.message
                : g.unavailableDesc}
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="space-y-3">
          <Card variant="status" className="border-l-emerald-500/60">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheckIcon className="size-4 text-emerald-500" />
                {g.lifecycleActive}
              </CardTitle>
              <CardDescription>
                {g.namespace} {systemGuard.retention.namespace ?? "system_lifecycle"}{" "}
                · {g.snapshotCount} {systemGuard.retention.snapshot_count ?? 0} · {g.retentionLimit}{" "}
                {systemGuard.retention.retention_limit ?? g.unbounded}
              </CardDescription>
            </CardHeader>
          </Card>

          <div className="grid gap-3 md:grid-cols-2">
            <Card variant="compact">
              <CardHeader>
                <CardTitle>{g.latestSnapshot}</CardTitle>
                <CardAction>
                  <Badge variant="secondary" className="text-xs">
                    {systemGuard.latest_snapshot?.phase ?? g.noSnapshot}
                  </Badge>
                </CardAction>
              </CardHeader>
              <CardContent>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <p>
                    {g.created}{" "}
                    {formatTimestamp(
                      systemGuard.latest_snapshot?.created_at,
                    ) ?? g.unavailableValue}
                  </p>
                  <p>
                    {g.session}{" "}
                    {systemGuard.latest_snapshot?.session_id ?? g.unavailableValue}
                  </p>
                  <p>
                    {g.issues} {snapshotIssueCount(systemGuard.latest_snapshot)}
                  </p>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={repair.isPending}
                    onClick={() => handleRepair(true)}
                  >
                    <ShieldEllipsisIcon className="size-3.5" />
                    {repair.isPending ? g.running : g.advisory}
                  </Button>
                  <Button
                    size="sm"
                    disabled={repair.isPending}
                    onClick={() => handleRepair(false)}
                  >
                    <WrenchIcon className="size-3.5" />
                    {repair.isPending ? g.running : g.repair}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={exportSnapshots.isPending}
                    onClick={handleExport}
                  >
                    <DownloadIcon className="size-3.5" />
                    {exportSnapshots.isPending ? g.exporting : g.export}
                  </Button>
                </div>
                {snapshotIssues(systemGuard.latest_snapshot).length ? (
                  <div className="mt-3 space-y-1.5">
                    <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      {g.latestIssues}
                    </div>
                    {snapshotIssues(systemGuard.latest_snapshot).map(
                      (issue, index) => (
                        <div
                          key={`${issue.code ?? "issue"}-${index}`}
                          className="rounded-lg bg-muted/30 p-2.5"
                        >
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Badge
                              variant={badgeVariantForSeverity(issue.severity)}
                              className="text-[10px]"
                            >
                              {issue.severity ?? "info"}
                            </Badge>
                            <span className="text-xs font-medium">
                              {issue.code ?? "unknown_issue"}
                            </span>
                            {issue.auto_repairable ? (
                              <Badge
                                variant="secondary"
                                className="text-[10px]"
                              >
                                {g.autoRepairable}
                              </Badge>
                            ) : null}
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {issue.message ?? g.noIssueMessage}
                          </p>
                        </div>
                      ),
                    )}
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <Card variant="compact">
              <CardHeader>
                <CardTitle>{g.retentionTelemetry}</CardTitle>
                <CardAction>
                  <Badge variant="outline" className="text-xs">
                    {systemGuard.recent_snapshots.length} {g.loaded}
                  </Badge>
                </CardAction>
              </CardHeader>
              <CardContent>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <p>
                    {g.namespace}{" "}
                    {systemGuard.retention.namespace ?? "system_lifecycle"}
                  </p>
                  <p>
                    {g.snapshotCount}{" "}
                    {systemGuard.retention.snapshot_count ?? 0}
                  </p>
                  <p>
                    {g.retentionLimit}{" "}
                    {systemGuard.retention.retention_limit ?? g.unbounded}
                  </p>
                </div>
                <div className="mt-3 rounded-lg bg-muted/30 p-2.5 text-[11px] text-muted-foreground">
                  {g.retentionHelpText}
                </div>
              </CardContent>
            </Card>
          </div>

          <Card variant="compact">
            <CardHeader>
              <CardTitle>{g.recentSnapshots}</CardTitle>
              <CardAction>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={isLoading}
                  onClick={() => void refetch()}
                >
                  <RefreshCwIcon className="size-3.5" />
                  {g.refresh}
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {systemGuard.recent_snapshots.length ? (
                  systemGuard.recent_snapshots.map((snapshot) => (
                    <div
                      key={snapshot.id ?? snapshot.created_at}
                      className="rounded-lg bg-muted/20 p-2.5"
                    >
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant="secondary" className="text-[10px]">
                          {snapshot.phase ?? "unknown"}
                        </Badge>
                        <span className="text-xs font-medium">
                          {formatTimestamp(snapshot.created_at)}
                        </span>
                        <span className="text-[10px] text-muted-foreground">
                          {g.session} {snapshot.session_id ?? "n/a"}
                        </span>
                        <Badge variant="outline" className="text-[10px]">
                          {snapshotIssueCount(snapshot)} {g.issues.replace("：", "").replace(":", "")}
                        </Badge>
                      </div>
                      {snapshotIssues(snapshot).length ? (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {snapshotIssues(snapshot).map((issue, index) => (
                            <Badge
                              key={`${snapshot.id ?? snapshot.created_at}-issue-${index}`}
                              variant={badgeVariantForSeverity(issue.severity)}
                              className="text-[10px]"
                            >
                              {(issue.code ?? "issue").replaceAll("_", " ")}
                            </Badge>
                          ))}
                        </div>
                      ) : null}
                      <div className="mt-2 grid gap-2 md:grid-cols-2">
                        <div>
                          <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                            {g.metadata}
                          </div>
                          <pre className="overflow-x-auto rounded-md bg-muted/30 p-2 text-[11px]">
                            {formatJson(snapshot.metadata)}
                          </pre>
                        </div>
                        <div>
                          <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                            {g.state}
                          </div>
                          <pre className="overflow-x-auto rounded-md bg-muted/30 p-2 text-[11px]">
                            {formatJson(snapshot.state)}
                          </pre>
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-xl border border-dashed p-4 text-center text-xs text-muted-foreground">
                    {g.noSnapshotsYet}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {repair.data ? (
            <Card variant="compact">
              <CardHeader>
                <CardTitle>{g.latestRepairResult}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-2 md:grid-cols-3">
                  <div className="rounded-lg bg-muted/30 p-2.5">
                    <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      {g.outcome}
                    </div>
                    <div className="mt-1 text-xs font-medium">
                      {repair.data.ok ? g.ok : g.attentionRequired}
                    </div>
                  </div>
                  <div className="rounded-lg bg-muted/30 p-2.5">
                    <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      {g.persistedPhase}
                    </div>
                    <div className="mt-1 text-xs font-medium">
                      {typeof repair.data.persisted?.phase === "string"
                        ? repair.data.persisted.phase
                        : "n/a"}
                    </div>
                  </div>
                  <div className="rounded-lg bg-muted/30 p-2.5">
                    <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      {g.builtinActions}
                    </div>
                    <div className="mt-1 text-xs font-medium">
                      {repairActionSummary(repair.data.repair_report)}
                    </div>
                  </div>
                </div>
                <pre className="mt-2 overflow-x-auto rounded-lg bg-muted/30 p-2.5 text-[11px]">
                  {formatJson(repair.data)}
                </pre>
              </CardContent>
            </Card>
          ) : null}
        </div>
      )}
    </SettingsSection>
  );
}
