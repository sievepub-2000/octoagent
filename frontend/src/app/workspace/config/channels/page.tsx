"use client";

import {
  ActivityIcon,
  CheckCircleIcon,
  Edit3Icon,
  LinkIcon,
  LogOutIcon,
  RadioTowerIcon,
  RefreshCcwIcon,
  SaveIcon,
  XCircleIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ChangeEvent } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  useChannelsStatus,
  useLogoutChannel,
  useRestartChannel,
  useSetChannelEnabled,
  useUpdateChannelConfig,
} from "@/core/channels/hooks";
import type { ChannelConfigField, ChannelStatusItem } from "@/core/channels/types";
import { useI18n } from "@/core/i18n/hooks";

type ChannelDraftValue = string | boolean;

function buildDraft(channel: ChannelStatusItem): Record<string, ChannelDraftValue> {
  return Object.fromEntries(
    (channel.fields ?? []).map((field) => {
      const value = channel.config?.[field.name];
      if (field.kind === "boolean") return [field.name, value === true];
      if (field.kind === "string_list" && Array.isArray(value)) {
        return [field.name, value.filter((item): item is string => typeof item === "string").join("\n")];
      }
      return [field.name, typeof value === "string" || typeof value === "number" ? String(value) : ""];
    }),
  );
}

function connectionStatus(channel: ChannelStatusItem) {
  if (channel.running && channel.healthy) {
    return { key: "healthy" as const, className: "border-green-500/30 text-green-600", Icon: CheckCircleIcon };
  }
  if (channel.running) {
    return { key: "degraded" as const, className: "border-yellow-500/30 text-yellow-600", Icon: ActivityIcon };
  }
  return { key: "stopped" as const, className: "border-muted text-muted-foreground", Icon: XCircleIcon };
}

function PathRow({ label, value, href }: { label: string; value: string; href?: string | null }) {
  return (
    <div className="grid gap-1">
      <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">{label}</div>
      {href ? (
        <a className="inline-flex items-center gap-1 break-all font-mono text-[11px] text-primary underline underline-offset-4" href={href} rel="noreferrer" target="_blank">
          <LinkIcon className="size-3" />
          {value}
        </a>
      ) : (
        <div className="break-all font-mono text-[11px] text-foreground">{value}</div>
      )}
    </div>
  );
}

function ChannelFieldEditor({
  channelName,
  field,
  value,
  onChange,
}: {
  channelName: string;
  field: ChannelConfigField;
  value: ChannelDraftValue;
  onChange: (nextValue: ChannelDraftValue) => void;
}) {
  const inputId = `${channelName}-${field.name}`;
  if (field.kind === "boolean") {
    return (
      <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground" htmlFor={inputId}>{field.label}</label>
            {field.description ? <p className="text-xs text-muted-foreground">{field.description}</p> : null}
          </div>
          <Switch checked={value === true} id={inputId} onCheckedChange={onChange} />
        </div>
      </div>
    );
  }

  const commonProps = {
    id: inputId,
    placeholder: field.placeholder ?? undefined,
    value: typeof value === "string" ? value : "",
    onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(event.target.value),
  };
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-foreground" htmlFor={inputId}>
        {field.label}{field.required ? <span className="ml-1 text-destructive">*</span> : null}
      </label>
      {field.description ? <p className="text-xs text-muted-foreground">{field.description}</p> : null}
      {field.kind === "string_list" ? (
        <Textarea className="min-h-24 resize-y" {...commonProps} />
      ) : (
        <Input {...commonProps} type={field.kind === "secret" ? "password" : field.kind === "number" ? "number" : field.kind === "url" ? "url" : "text"} />
      )}
    </div>
  );
}

function ChannelQRCodeLogin({ channelName, onLoginSuccess }: { channelName: string; onLoginSuccess: () => void }) {
  const { t } = useI18n();
  const labels = t.softwareInterfaces;
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchQR = useCallback(async () => {
    setError(null);
    const response = await fetch(`/api/channels/${channelName}/qrcode`);
    if (!response.ok) {
      setError(response.status === 404 || response.status === 400 ? labels.qrUnavailable : labels.requestFailed(response.status));
      return;
    }
    const nextUrl = URL.createObjectURL(await response.blob());
    setQrUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return nextUrl;
    });
  }, [channelName, labels]);

  useEffect(() => {
    void fetchQR().catch(() => setError(labels.networkError));
  }, [fetchQR, labels.networkError]);

  useEffect(() => {
    const interval = window.setInterval(async () => {
      const response = await fetch(`/api/channels/${channelName}/identity`).catch(() => null);
      if (!response?.ok) return;
      const identity = (await response.json()) as { logged_in?: boolean };
      if (identity.logged_in) {
        window.clearInterval(interval);
        toast.success(labels.channelLoginSucceeded);
        onLoginSuccess();
      }
    }, 3000);
    return () => window.clearInterval(interval);
  }, [channelName, labels.channelLoginSucceeded, onLoginSuccess]);

  return (
    <div className="mt-6 rounded-2xl border border-border/70 bg-background/50 p-5">
      <h3 className="mb-2 text-sm font-semibold text-foreground">{labels.qrLogin}</h3>
      <p className="mb-4 text-xs text-muted-foreground">{labels.qrLoginDescription}</p>
      <div className="flex flex-col items-center gap-3">
        {error ? <div className="text-sm text-destructive">{error}</div> : null}
        {qrUrl ? <img src={qrUrl} alt={labels.qrAlt} className="size-48 rounded-md bg-white p-2 shadow-sm" /> : null}
        <Button size="sm" variant="outline" onClick={() => void fetchQR()}>{labels.refreshQr}</Button>
      </div>
    </div>
  );
}

export default function ChannelsConfigPage() {
  const { t } = useI18n();
  const labels = t.softwareInterfaces;
  const { status, isLoading, error, refetch } = useChannelsStatus();
  const restartChannel = useRestartChannel();
  const updateChannelConfig = useUpdateChannelConfig();
  const setChannelEnabled = useSetChannelEnabled();
  const logoutChannel = useLogoutChannel();
  const [editingName, setEditingName] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, ChannelDraftValue>>({});

  const channels = useMemo(() => Object.entries(status?.channels ?? {}), [status?.channels]);
  const editingChannel = editingName ? status?.channels?.[editingName] : undefined;
  const editableFields = (editingChannel?.fields ?? []).filter((field) => field.name !== "enabled");

  function startEdit(name: string, channel: ChannelStatusItem) {
    setEditingName(name);
    setDraft(buildDraft(channel));
  }

  async function handleSave() {
    if (!editingName) return;
    try {
      const result = await updateChannelConfig.mutateAsync({ name: editingName, config: draft });
      toast.success(result.message);
      setEditingName(null);
    } catch (caught) {
      toast.error(caught instanceof Error ? caught.message : labels.saveFailed);
    }
  }

  async function handleLogout(name: string, label: string) {
    if (typeof window !== "undefined" && !window.confirm(labels.logoutConfirm(label))) return;
    try {
      const result = await logoutChannel.mutateAsync(name);
      result.success ? toast.success(result.message) : toast.warning(result.message);
    } catch (caught) {
      toast.error(caught instanceof Error ? caught.message : labels.logoutFailed);
    }
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <RadioTowerIcon className="size-5 text-primary" />
            <h1 className="text-lg font-semibold text-foreground">{labels.title}</h1>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{labels.description}</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => void refetch()}>
          <RefreshCcwIcon className="size-4" />{labels.refresh}
        </Button>
      </header>

      <section className="octo-panel mb-6 rounded-[1.5rem] p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-foreground">{labels.runtimeTitle}</div>
            <p className="text-xs text-muted-foreground">{labels.runtimeDescription}</p>
          </div>
          <div className="flex gap-2">
            <Badge variant={status?.service_running ? "default" : "secondary"}>
              {status?.service_running ? labels.running : labels.stopped}
            </Badge>
            <Badge variant="outline">{labels.messagingCount(channels.length)}</Badge>
          </div>
        </div>

        {isLoading ? (
          <div className="text-sm text-muted-foreground">{t.common.loading}</div>
        ) : error ? (
          <div className="text-sm text-destructive">{error instanceof Error ? error.message : labels.catalogLoadFailed}</div>
        ) : channels.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">{labels.empty}</div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {channels.map(([name, channel]) => {
              const current = connectionStatus(channel);
              const StatusIcon = current.Icon;
              return (
                <article key={name} className="octo-panel octo-management-card flex min-w-0 flex-col justify-between rounded-[1.5rem] p-3">
                  <div className="mb-3 flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h2 className="break-words text-sm font-medium text-foreground">{channel.platform_label ?? name}</h2>
                      <p className="line-clamp-2 text-xs text-muted-foreground">{channel.description ?? labels.channelDescription}</p>
                    </div>
                    <div className="octo-card-actions">
                      <Button className="octo-card-action" size="icon" variant="ghost" onClick={() => startEdit(name, channel)} aria-label={labels.editAria(channel.platform_label ?? name)}>
                        <Edit3Icon className="size-3.5" />
                      </Button>
                      <Button className="octo-card-action" size="icon" variant="ghost" onClick={() => void handleLogout(name, channel.platform_label ?? name)} aria-label={labels.logoutAria(channel.platform_label ?? name)}>
                        <LogOutIcon className="size-3.5" />
                      </Button>
                    </div>
                  </div>
                  <div className="mt-auto flex items-end justify-between gap-3">
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="secondary" className="text-[10px]">{channel.integration_mode ?? labels.native}</Badge>
                      <Badge variant="outline" className={`gap-1 text-[10px] ${current.className}`}>
                        <StatusIcon className="size-3" />{labels.channelStatus[current.key]}
                      </Badge>
                    </div>
                    <Switch checked={channel.enabled !== false} onCheckedChange={(checked) => void setChannelEnabled.mutateAsync({ name, enabled: checked })} />
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {editingName && editingChannel ? (
        <section className="octo-panel mb-6 rounded-[1.5rem] p-5">
          <div className="mb-4">
            <div className="text-sm font-medium text-foreground">{labels.editTitle(editingChannel.platform_label ?? editingName)}</div>
            <p className="text-xs text-muted-foreground">{labels.editDescription}</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {editableFields.map((field) => (
              <ChannelFieldEditor
                channelName={editingName}
                field={field}
                key={field.name}
                value={draft[field.name] ?? (field.kind === "boolean" ? false : "")}
                onChange={(value) => setDraft((current) => ({ ...current, [field.name]: value }))}
              />
            ))}
          </div>
          {editingName === "qq" || editingName === "wechat" ? <ChannelQRCodeLogin channelName={editingName} onLoginSuccess={() => void refetch()} /> : null}
          <div className="mt-5 grid gap-3 rounded-2xl border border-border/70 bg-muted/10 p-4 text-xs text-muted-foreground">
            {editingChannel.config_path ? <PathRow label={labels.configPath} value={editingChannel.config_path} /> : null}
            {editingChannel.handler_path ? <PathRow label={labels.handler} value={editingChannel.handler_path} /> : null}
            {editingChannel.ingest_path ? <PathRow label={labels.ingestPath} value={editingChannel.ingest_path} /> : null}
            {editingChannel.bridge_project && editingChannel.bridge_project_url ? <PathRow href={editingChannel.bridge_project_url} label={labels.upstreamBridge} value={editingChannel.bridge_project} /> : null}
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button size="sm" variant="outline" onClick={() => setEditingName(null)}>{t.common.cancel}</Button>
            <Button size="sm" variant="outline" onClick={() => void restartChannel.mutateAsync(editingName)}>
              <RefreshCcwIcon className="size-3.5" />{labels.restart}
            </Button>
            <Button size="sm" onClick={() => void handleSave()}>
              <SaveIcon className="size-3.5" />{t.common.save}
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
