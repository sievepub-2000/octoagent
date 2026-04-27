"use client";

import { AlertTriangleIcon, CheckCircleIcon, DownloadCloudIcon, Loader2Icon, RefreshCwIcon } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/core/i18n/hooks";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

interface UpdateInfo {
  current_version: string;
  latest_version: string;
  has_update: boolean;
  latest_commit: string;
  latest_date: string;
  changelog: string;
}

interface AutoUpdateConfig {
  enabled: boolean;
  check_interval_hours: number;
  last_check: string;
}

type UpdateDialogState =
  | { kind: "closed" }
  | { kind: "up-to-date"; info: UpdateInfo }
  | { kind: "confirm"; info: UpdateInfo };

export function UpdateSettingsPage() {
  const { t } = useI18n();
  const u = t.settings.update;

  const [checking, setChecking] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [error, setError] = useState("");
  const [autoConfig, setAutoConfig] = useState<AutoUpdateConfig>({ enabled: false, check_interval_hours: 24, last_check: "" });
  const [updateResult, setUpdateResult] = useState<{ success: boolean; message: string } | null>(null);
  const [dialogState, setDialogState] = useState<UpdateDialogState>({ kind: "closed" });
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const waitForServiceRecovery = useCallback(async () => {
    const deadline = Date.now() + 60_000;
    while (Date.now() < deadline) {
      try {
        const response = await fetch(`${API_BASE}/api/system/version`, { cache: "no-store" });
        if (response.ok) {
          window.location.reload();
          return;
        }
      } catch {
        // Keep polling until the restarted gateway becomes reachable again.
      }

      await new Promise((resolve) => window.setTimeout(resolve, 1500));
    }

    window.location.reload();
  }, []);

  // Load auto-update config on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/system/update/auto-config`)
      .then((r) => r.json())
      .then((data) => { if (mounted.current) setAutoConfig(data); })
      .catch(() => undefined);
  }, []);

  const handleCheck = useCallback(async () => {
    setChecking(true);
    setError("");
    setUpdateResult(null);
    setDialogState({ kind: "closed" });
    try {
      const resp = await fetch(`${API_BASE}/api/system/update/check`);
      const payload = await resp.json().catch(() => null);
      if (!resp.ok) {
        throw new Error(
          payload?.detail ?? payload?.message ?? `HTTP ${resp.status}`,
        );
      }
      const data: UpdateInfo = payload;
      if (mounted.current) {
        setInfo(data);
        setDialogState(data.has_update ? { kind: "confirm", info: data } : { kind: "up-to-date", info: data });
      }
    } catch (err) {
      if (mounted.current) {
        setInfo(null);
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (mounted.current) setChecking(false);
    }
  }, []);

  const handleUpdate = useCallback(async () => {
    setUpdating(true);
    setUpdateResult(null);
    setDialogState({ kind: "closed" });
    try {
      const resp = await fetch(`${API_BASE}/api/system/update/apply`, { method: "POST" });
      const data = await resp.json();
      if (mounted.current) {
        setUpdateResult(data);
        if (data.success) {
          void waitForServiceRecovery();
        }
      }
    } catch (err) {
      if (mounted.current) setUpdateResult({ success: false, message: String(err) });
    } finally {
      if (mounted.current) setUpdating(false);
    }
  }, [waitForServiceRecovery]);

  const toggleAutoUpdate = useCallback(async (enabled: boolean) => {
    const next = { ...autoConfig, enabled };
    setAutoConfig(next);
    try {
      await fetch(`${API_BASE}/api/system/update/auto-config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(next),
      });
    } catch {
      // revert on failure
      setAutoConfig(autoConfig);
    }
  }, [autoConfig]);

  return (
    <div className="space-y-6">
      {/* Version & check */}
      <Card variant="compact">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <DownloadCloudIcon className="size-5" />
            {u.title}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <Button variant="outline" size="sm" onClick={handleCheck} disabled={checking}>
              {checking ? <Loader2Icon className="mr-2 size-4 animate-spin" /> : <RefreshCwIcon className="mr-2 size-4" />}
              {u.checkNow}
            </Button>
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          {info && (
            <div className="rounded-lg border p-4 space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">{u.currentVersion}</span>
                <code className="text-muted-foreground">{info.current_version}</code>
              </div>
              {info.has_update ? (
                <>
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{u.latestVersion}</span>
                    <code className="text-primary">{info.latest_version}</code>
                  </div>
                  {info.changelog && (
                    <p className="text-muted-foreground text-xs">{info.changelog}</p>
                  )}
                </>
              ) : (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <CheckCircleIcon className="size-4 text-green-500" />
                  {u.upToDate}
                </div>
              )}
            </div>
          )}

          {updating && !updateResult && (
            <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
              <div className="flex items-center gap-2">
                <Loader2Icon className="size-4 animate-spin text-primary" />
                <span>{u.updatingStatus}</span>
              </div>
            </div>
          )}

          {updateResult && (
            <div className={`rounded-lg border p-3 text-sm ${updateResult.success ? "border-green-500/30 bg-green-500/5" : "border-destructive/30 bg-destructive/5"}`}>
              {updateResult.success ? (
                <div className="flex items-center gap-2">
                  <CheckCircleIcon className="size-4 text-green-500" />
                  <span>{updateResult.message}</span>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-destructive">
                  <AlertTriangleIcon className="size-4" />
                  <span>{updateResult.message}</span>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={dialogState.kind !== "closed"}
        onOpenChange={(open) => {
          if (!open) {
            setDialogState({ kind: "closed" });
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {dialogState.kind === "confirm" ? u.confirmUpdateDialogTitle : u.noUpdateDialogTitle}
            </DialogTitle>
            <DialogDescription>
              {dialogState.kind === "confirm"
                ? u.confirmUpdateDialogDescription(dialogState.info.latest_version)
                : dialogState.kind === "up-to-date"
                  ? u.noUpdateDialogDescription(dialogState.info.latest_version)
                  : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            {dialogState.kind === "confirm" ? (
              <>
                <Button variant="outline" onClick={() => setDialogState({ kind: "closed" })} disabled={updating}>
                  {t.common.cancel}
                </Button>
                <Button onClick={() => void handleUpdate()} disabled={updating}>
                  {updating ? <Loader2Icon className="mr-2 size-4 animate-spin" /> : <DownloadCloudIcon className="mr-2 size-4" />}
                  {u.applyUpdate}
                </Button>
              </>
            ) : (
              <Button onClick={() => setDialogState({ kind: "closed" })}>{t.common.close}</Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Auto-update toggle */}
      <Card variant="compact">
        <CardHeader>
          <CardTitle className="text-base">{u.autoUpdate}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <p className="text-sm font-medium">{u.autoUpdateLabel}</p>
              <p className="text-xs text-muted-foreground">{u.autoUpdateDesc}</p>
            </div>
            <Switch checked={autoConfig.enabled} onCheckedChange={toggleAutoUpdate} />
          </div>
          {autoConfig.last_check && (
            <p className="text-xs text-muted-foreground">
              {u.lastCheck}: {new Date(autoConfig.last_check).toLocaleString()}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
