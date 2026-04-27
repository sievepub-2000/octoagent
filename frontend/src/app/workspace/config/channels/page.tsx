"use client";

import {
  ActivityIcon,
  CheckCircleIcon,
  Edit3Icon,
  LinkIcon,
  RadioTowerIcon,
  RefreshCcwIcon,
  SaveIcon,
  Trash2Icon,
  XCircleIcon,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  useChannelsStatus,
  useDeleteChannelConfig,
  useRestartChannel,
  useSetChannelEnabled,
  useUpdateChannelConfig,
} from "@/core/channels/hooks";
import type { ChannelConfigField, ChannelStatusItem } from "@/core/channels/types";
import { useI18n } from "@/core/i18n/hooks";

type ChannelDraftValue = string | boolean;

function buildDraft(channel: ChannelStatusItem): Record<string, ChannelDraftValue> {
  const draft: Record<string, ChannelDraftValue> = {};
  for (const field of channel.fields ?? []) {
    const value = channel.config?.[field.name];
    if (field.kind === "boolean") {
      draft[field.name] = value === true;
      continue;
    }
    if (field.kind === "string_list") {
      draft[field.name] = Array.isArray(value)
        ? value.filter((item): item is string => typeof item === "string").join("\n")
        : typeof value === "string"
          ? value
          : "";
      continue;
    }
    draft[field.name] = typeof value === "string"
      ? value
      : typeof value === "number"
        ? String(value)
        : "";
  }
  return draft;
}

function connectionStatus(channel: ChannelStatusItem): {
  label: string;
  className: string;
  icon: typeof CheckCircleIcon;
} {
  if (channel.running === true && channel.healthy === true) {
    return {
      label: "Link healthy",
      className: "gap-1 border-green-500/30 text-[10px] text-green-600",
      icon: CheckCircleIcon,
    };
  }
  if (channel.running === true) {
    return {
      label: "Link degraded",
      className: "gap-1 border-yellow-500/30 text-[10px] text-yellow-600",
      icon: ActivityIcon,
    };
  }
  return {
    label: "Link stopped",
    className: "gap-1 border-muted text-[10px] text-muted-foreground",
    icon: XCircleIcon,
  };
}

function PathRow({
  label,
  value,
  href,
}: {
  label: string;
  value: string;
  href?: string | null;
}) {
  return (
    <div className="grid gap-1">
      <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
        {label}
      </div>
      {href ? (
        <a
          className="inline-flex items-center gap-1 break-all font-mono text-[11px] text-primary underline underline-offset-4"
          href={href}
          rel="noreferrer"
          target="_blank"
        >
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
            <label className="text-sm font-medium text-foreground" htmlFor={inputId}>
              {field.label}
            </label>
            {field.description ? (
              <p className="text-xs text-muted-foreground">{field.description}</p>
            ) : null}
          </div>
          <Switch
            checked={value === true}
            id={inputId}
            onCheckedChange={(checked) => onChange(checked)}
          />
        </div>
      </div>
    );
  }

  const commonProps = {
    id: inputId,
    placeholder: field.placeholder ?? undefined,
    value: typeof value === "string" ? value : "",
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      onChange(event.target.value),
  };

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-foreground" htmlFor={inputId}>
        {field.label}
        {field.required ? <span className="ml-1 text-destructive">*</span> : null}
      </label>
      {field.description ? (
        <p className="text-xs text-muted-foreground">{field.description}</p>
      ) : null}
      {field.kind === "string_list" ? (
        <Textarea className="min-h-24 resize-y" {...commonProps} />
      ) : (
        <Input
          {...commonProps}
          type={field.kind === "secret" ? "password" : field.kind === "number" ? "number" : field.kind === "url" ? "url" : "text"}
        />
      )}
    </div>
  );
}

export default function ChannelsConfigPage() {
  const { t } = useI18n();
  const { status, isLoading, error, refetch } = useChannelsStatus();
  const restartChannel = useRestartChannel();
  const updateChannelConfig = useUpdateChannelConfig();
  const setChannelEnabled = useSetChannelEnabled();
  const deleteChannelConfigMutation = useDeleteChannelConfig();
  const channels = Object.entries(status?.channels ?? {});
  const [editingName, setEditingName] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, ChannelDraftValue>>({});
  const editingChannel = editingName ? status?.channels?.[editingName] : undefined;
  const editableFields = (editingChannel?.fields ?? []).filter((field) => field.name !== "enabled");

  async function handleRestart(name: string) {
    try {
      const result = await restartChannel.mutateAsync(name);
      if (result.success) { toast.success(result.message); }
      else { toast.error(result.message); }
    } catch (restartError) {
      toast.error(restartError instanceof Error ? restartError.message : "Failed to restart channel.");
    }
  }

  async function handleSave(name: string, draft: Record<string, ChannelDraftValue>) {
    try {
      const payload = Object.fromEntries(Object.entries(draft));
      const result = await updateChannelConfig.mutateAsync({ name, config: payload });
      toast.success(result.message);
    } catch (saveError) {
      toast.error(saveError instanceof Error ? saveError.message : "Failed to save channel configuration.");
    }
  }

  function startEdit(name: string, channel: ChannelStatusItem) {
    setEditingName(name);
    setDraft(buildDraft(channel));
  }

  function cancelEdit() {
    setEditingName(null);
    setDraft({});
  }

  async function handleSaveEditingChannel() {
    if (!editingName || !editingChannel) {
      return;
    }
    await handleSave(editingName, draft);
    cancelEdit();
  }

  async function handleToggleEnabled(name: string, enabled: boolean) {
    try {
      const result = await setChannelEnabled.mutateAsync({ name, enabled });
      toast.success(result.message);
    } catch (toggleError) {
      toast.error(toggleError instanceof Error ? toggleError.message : "Failed to update channel switch.");
    }
  }

  async function handleDeleteConfig(name: string, platformLabel?: string) {
    const label = platformLabel ?? name;
    const confirmed = typeof window === "undefined"
      ? true
      : window.confirm(
          `Remove the stored configuration for "${label}"?\n\nThis clears credentials in config.yaml and restarts the channel service. The channel definition itself is preserved and can be re-configured later.`,
        );
    if (!confirmed) {
      return;
    }
    try {
      const result = await deleteChannelConfigMutation.mutateAsync(name);
      toast.success(result.message);
      if (editingName === name) {
        cancelEdit();
      }
    } catch (deleteError) {
      toast.error(
        deleteError instanceof Error
          ? deleteError.message
          : "Failed to remove channel configuration.",
      );
    }
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <RadioTowerIcon className="size-5 text-primary" />
              <h1 className="text-lg font-semibold text-foreground">Channels</h1>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Configure each messaging connector with its real runtime parameters and path hints.
            </p>
          </div>
          <Button size="sm" variant="outline" onClick={() => void refetch()}>
            <RefreshCcwIcon className="size-4" />Refresh
          </Button>
        </div>
      </header>

      {/* Service status card */}
      <div className="octo-panel mb-6 rounded-[1.5rem] p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">Service Status</div>
            <p className="text-xs text-muted-foreground">
              Channel connector service runtime overview.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant={status?.service_running ? "default" : "secondary"} className="gap-1">
              {status?.service_running ? <><CheckCircleIcon className="size-3" /> Running</> : <><XCircleIcon className="size-3" /> Stopped</>}
            </Badge>
            <Badge variant="outline">{channels.length} channel{channels.length === 1 ? "" : "s"}</Badge>
          </div>
        </div>
      </div>

      {editingName && editingChannel ? (
        <section className="octo-panel mb-6 rounded-[1.5rem] p-5">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-foreground">
                Edit channel: {editingChannel.platform_label ?? editingName}
              </div>
              <p className="text-xs text-muted-foreground">
                Configure runtime fields for this channel. Changes are persisted to config.yaml.
              </p>
            </div>
            <Badge variant="outline" className="text-[10px]">
              {editingChannel.integration_mode ?? "native"}
            </Badge>
          </div>

          {editableFields.length === 0 ? (
            <div className="rounded-2xl border border-border/70 bg-muted/10 p-4 text-sm text-muted-foreground">
              No editable configuration fields are available for this channel.
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {editableFields.map((field) => (
                <ChannelFieldEditor
                  channelName={editingName}
                  field={field}
                  key={field.name}
                  onChange={(nextValue) => {
                    setDraft((current) => ({
                      ...current,
                      [field.name]: nextValue,
                    }));
                  }}
                  value={draft[field.name] ?? (field.kind === "boolean" ? false : "")}
                />
              ))}
            </div>
          )}

          <div className="mt-5 grid gap-3 rounded-2xl border border-border/70 bg-muted/10 p-4 text-xs text-muted-foreground">
            {editingChannel.config_path ? <PathRow label="Config Path" value={editingChannel.config_path} /> : null}
            {editingChannel.handler_path ? <PathRow label="Handler" value={editingChannel.handler_path} /> : null}
            {editingChannel.ingest_path ? <PathRow label="Ingest Path" value={editingChannel.ingest_path} /> : null}
            {editingChannel.bridge_project && editingChannel.bridge_project_url ? (
              <PathRow
                href={editingChannel.bridge_project_url}
                label="Upstream Bridge"
                value={editingChannel.bridge_project}
              />
            ) : null}
            {typeof editingChannel.outbound_configured === "boolean" ? (
              <PathRow
                label="Outbound Relay"
                value={editingChannel.outbound_configured ? "configured" : "not configured"}
              />
            ) : null}
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
            <Button
              disabled={updateChannelConfig.isPending}
              onClick={cancelEdit}
              size="sm"
              variant="outline"
            >
              Cancel
            </Button>
            <Button
              disabled={restartChannel.isPending}
              onClick={() => void handleRestart(editingName)}
              size="sm"
              variant="outline"
            >
              <RefreshCcwIcon className="size-3.5" />
              Restart
            </Button>
            <Button
              disabled={updateChannelConfig.isPending}
              onClick={() => void handleSaveEditingChannel()}
              size="sm"
            >
              <SaveIcon className="size-3.5" />
              Save
            </Button>
          </div>
        </section>
      ) : null}

      {/* Channel cards */}
      {isLoading ? (
        <div className="text-sm text-muted-foreground">{t.common.loading}</div>
      ) : error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {error instanceof Error ? error.message : "Failed to load channels status."}
        </div>
      ) : channels.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <ActivityIcon className="mb-3 size-10 opacity-30" />
          <p className="text-sm">No channel connectors are configured.</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {channels.map(([name, channel]) => {
            const statusBadge = connectionStatus(channel);
            const StatusIcon = statusBadge.icon;
            return (
              <article
                className="octo-panel flex min-w-0 flex-col justify-between rounded-[1.5rem] p-4 transition-shadow hover:translate-y-[-1px] hover:shadow-[3px_3px_7px_var(--neu-dark-strong),_-3px_-3px_7px_var(--neu-light-strong)]"
                key={name}
              >
                <div className="mb-3 flex items-start justify-between gap-2">
                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <RadioTowerIcon className="size-4 shrink-0 text-muted-foreground" />
                      <h2 className="min-w-0 break-words text-sm font-medium text-foreground">
                        {channel.platform_label ?? name}
                      </h2>
                    </div>
                    <p className="line-clamp-2 text-xs text-muted-foreground">
                      {channel.description ?? "Connector configuration"}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Button
                      aria-label={`Edit ${channel.platform_label ?? name}`}
                      className="size-7"
                      onClick={() => startEdit(name, channel)}
                      size="icon"
                      title="Edit configuration"
                      variant="ghost"
                    >
                      <Edit3Icon className="size-3.5 text-muted-foreground hover:text-primary" />
                    </Button>
                    <Button
                      aria-label={`Remove configuration for ${channel.platform_label ?? name}`}
                      className="size-7"
                      disabled={deleteChannelConfigMutation.isPending}
                      onClick={() => void handleDeleteConfig(name, channel.platform_label)}
                      size="icon"
                      title="Remove stored configuration"
                      variant="ghost"
                    >
                      <Trash2Icon className="size-3.5 text-muted-foreground hover:text-destructive" />
                    </Button>
                  </div>
                </div>

                <div className="mt-auto flex items-end justify-between gap-3">
                  <div className="min-w-0 space-y-1.5">
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="secondary" className="text-[10px]">
                        {channel.integration_mode ?? "native"}
                      </Badge>
                      <Badge variant="outline" className="text-[10px]">
                        {channel.transport ?? "unknown"}
                      </Badge>
                      <Badge variant="outline" className={statusBadge.className}>
                        <StatusIcon className="size-3" />
                        {statusBadge.label}
                      </Badge>
                    </div>
                    {channel.bridge_project && channel.bridge_project_url ? (
                      <a
                        className="inline-flex items-center gap-1 text-[11px] text-primary underline underline-offset-4"
                        href={channel.bridge_project_url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        <LinkIcon className="size-3" />
                        {channel.bridge_project}
                      </a>
                    ) : null}
                  </div>

                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <span className="text-[11px] text-muted-foreground">Enabled</span>
                    <Switch
                      aria-label={`Enable ${channel.platform_label ?? name}`}
                      checked={channel.enabled === true}
                      disabled={setChannelEnabled.isPending}
                      onCheckedChange={(checked) => {
                        void handleToggleEnabled(name, checked);
                      }}
                    />
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
