"use client";

import {
  ActivityIcon,
  BriefcaseBusinessIcon,
  CheckCircleIcon,
  Edit3Icon,
  ExternalLinkIcon,
  FolderKanbanIcon,
  LinkIcon,
  LogOutIcon,
  MailIcon,
  MessageSquareIcon,
  PlugZapIcon,
  RadioTowerIcon,
  RefreshCcwIcon,
  SaveIcon,
  Settings2Icon,
  WrenchIcon,
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

type SoftwareInterfaceItem = {
  id: string;
  slug: string;
  name: string;
  category: string;
  description: string;
  source: string;
  auth_provider: string;
  status: string;
  supports_oauth: boolean;
};

type SoftwareInterfaceCategory = {
  id: string;
  label: string;
  count: number;
};

type SoftwareInterfaceCatalogResponse = {
  total: number;
  categories: SoftwareInterfaceCategory[];
  interfaces: SoftwareInterfaceItem[];
};

type SoftwareInterfaceConnection = {
  id: string;
  toolkit: string;
  status: string;
  createdAt?: string;
  accountEmail?: string;
  workspace?: string;
  username?: string;
};

type SoftwareInterfaceConnectionsResponse = {
  success?: boolean;
  status?: string;
  detail?: string;
  connections?: SoftwareInterfaceConnection[];
};

type SoftwareInterfaceToolsResponse = {
  success?: boolean;
  status?: string;
  detail?: string;
  tools?: Array<{
    function?: {
      name?: string;
      description?: string;
      parameters?: Record<string, unknown>;
    };
  }>;
};

type SoftwareInterfaceScopes = {
  read: boolean;
  write: boolean;
  admin: boolean;
};

type UnifiedCard =
  | { kind: "software"; id: string; category: string; item: SoftwareInterfaceItem }
  | { kind: "channel"; id: string; category: "communication"; name: string; channel: ChannelStatusItem };

const SOFTWARE_INTERFACE_CATEGORY_ICONS: Record<string, typeof MessageSquareIcon> = {
  communication: MessageSquareIcon,
  office: BriefcaseBusinessIcon,
  mail_calendar: MailIcon,
  docs_storage: FolderKanbanIcon,
  project_management: FolderKanbanIcon,
  development: PlugZapIcon,
  crm_sales: BriefcaseBusinessIcon,
  commerce_payments: BriefcaseBusinessIcon,
  social_media: MessageSquareIcon,
  automation: PlugZapIcon,
};

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

function formatSoftwareDetail(value: unknown, fallback: string): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value && typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return fallback;
    }
  }
  return fallback;
}

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
    draft[field.name] = typeof value === "string" ? value : typeof value === "number" ? String(value) : "";
  }
  return draft;
}

function connectionStatus(channel: ChannelStatusItem): {
  labelKey: "healthy" | "degraded" | "stopped";
  className: string;
  icon: typeof CheckCircleIcon;
} {
  if (channel.running === true && channel.healthy === true) {
    return { labelKey: "healthy", className: "gap-1 border-green-500/30 text-[10px] text-green-600", icon: CheckCircleIcon };
  }
  if (channel.running === true) {
    return { labelKey: "degraded", className: "gap-1 border-yellow-500/30 text-[10px] text-yellow-600", icon: ActivityIcon };
  }
  return { labelKey: "stopped", className: "gap-1 border-muted text-[10px] text-muted-foreground", icon: XCircleIcon };
}

function softwareConnectionState(connection?: SoftwareInterfaceConnection): "connected" | "pending" | "expired" | "error" | "disconnected" {
  if (!connection) return "disconnected";
  const status = connection.status.trim().toUpperCase();
  if (status === "ACTIVE" || status === "CONNECTED") return "connected";
  if (status === "PENDING" || status === "INITIATED" || status === "INITIALIZING") return "pending";
  if (status === "EXPIRED") return "expired";
  if (status === "FAILED" || status === "ERROR") return "error";
  return "disconnected";
}

function connectionLabel(connection?: SoftwareInterfaceConnection): string | null {
  if (!connection) return null;
  return connection.accountEmail ?? connection.workspace ?? connection.username ?? connection.id;
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
          <Switch checked={value === true} id={inputId} onCheckedChange={(checked) => onChange(checked)} />
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
        {field.label}
        {field.required ? <span className="ml-1 text-destructive">*</span> : null}
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loginInfo, setLoginInfo] = useState<{ user_id?: number; nickname?: string } | null>(null);

  const fetchQR = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`/api/channels/${channelName}/qrcode`);
      if (res.ok) {
        const blob = await res.blob();
        setQrUrl(URL.createObjectURL(blob));
      } else if (res.status === 404 || res.status === 400) {
        setError(labels.qrUnavailable);
      } else {
        setError(labels.requestFailed(res.status));
      }
    } catch {
      setError(labels.networkError);
    } finally {
      setLoading(false);
    }
  }, [channelName, labels]);

  const checkStatus = useCallback(async () => {
    try {
      const res = await fetch(`/api/channels/${channelName}/identity`);
      if (!res.ok) return false;
      const data = (await res.json()) as {
        logged_in?: boolean;
        account_id?: string | null;
        display_name?: string | null;
        info?: { user_id?: number | string; nickname?: string };
      };
      if (data.logged_in) {
        const accountId = data.info?.user_id ?? data.account_id ?? undefined;
        setLoginInfo({
          user_id: accountId ? Number(accountId) : undefined,
          nickname: data.info?.nickname ?? data.display_name ?? undefined,
        });
        return true;
      }
    } catch {
      return false;
    }
    return false;
  }, [channelName]);

  useEffect(() => {
    void (async () => {
      const loggedIn = await checkStatus();
      if (!loggedIn) void fetchQR();
    })();
  }, [checkStatus, fetchQR]);

  useEffect(() => {
    if (loginInfo) return undefined;
    const interval = setInterval(() => {
      void (async () => {
        const loggedIn = await checkStatus();
        if (loggedIn) {
          toast.success(labels.channelLoginSucceeded);
          onLoginSuccess();
        }
      })();
    }, 3000);
    return () => clearInterval(interval);
  }, [checkStatus, onLoginSuccess, loginInfo, labels]);

  return (
    <div className="mt-6 rounded-2xl border border-border/70 bg-background/50 p-5">
      <h3 className="mb-2 text-sm font-semibold text-foreground">{loginInfo ? labels.channelLoginStatus : labels.qrLogin}</h3>
      <p className="mb-4 text-xs text-muted-foreground">{loginInfo ? labels.channelLoggedIn : labels.qrLoginDescription}</p>
      <div className="flex flex-col items-center justify-center gap-4 py-4">
        {loginInfo ? (
          <div className="flex flex-col items-center gap-3">
            <CheckCircleIcon className="size-12 text-green-500" />
            <div className="text-sm font-medium text-foreground">{labels.loggedInAs(loginInfo.nickname ?? labels.unknownUser, loginInfo.user_id)}</div>
          </div>
        ) : loading ? (
          <div className="text-sm text-muted-foreground">{labels.fetchingQr}</div>
        ) : error ? (
          <div className="flex flex-col items-center gap-2">
            <div className="text-sm text-destructive">{error}</div>
            <Button size="sm" variant="outline" onClick={() => void fetchQR()}>{labels.retry}</Button>
          </div>
        ) : qrUrl ? (
          <div className="flex flex-col items-center gap-4">
            <img src={qrUrl} alt={labels.qrAlt} className="size-48 rounded-md bg-white p-2 shadow-sm" />
            <Button size="sm" variant="outline" onClick={() => void fetchQR()}>{labels.refreshQr}</Button>
          </div>
        ) : null}
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
  const logoutChannelMutation = useLogoutChannel();

  const [catalog, setCatalog] = useState<SoftwareInterfaceCatalogResponse | null>(null);
  const [connections, setConnections] = useState<SoftwareInterfaceConnection[]>([]);
  const [gatewayStatus, setGatewayStatus] = useState<Record<string, unknown> | null>(null);
  const [activeCategory, setActiveCategory] = useState<string>("communication");
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, ChannelDraftValue>>({});
  const [managingSoftware, setManagingSoftware] = useState<SoftwareInterfaceItem | null>(null);
  const [manageTools, setManageTools] = useState<SoftwareInterfaceToolsResponse | null>(null);
  const [manageLoading, setManageLoading] = useState(false);
  const [extraParams, setExtraParams] = useState("{}");
  const [scopes, setScopes] = useState<SoftwareInterfaceScopes>({ read: true, write: true, admin: false });

  const channels = useMemo(() => Object.entries(status?.channels ?? {}), [status?.channels]);
  const editingChannel = editingName ? status?.channels?.[editingName] : undefined;
  const editableFields = (editingChannel?.fields ?? []).filter((field) => field.name !== "enabled");

  const loadSoftwareInterfaces = useCallback(async () => {
    try {
      setCatalogLoading(true);
      setCatalogError(null);
      const [nextCatalog, nextConnections, nextStatus] = await Promise.all([
        requestJson<SoftwareInterfaceCatalogResponse>("/api/software-interfaces/catalog"),
        requestJson<SoftwareInterfaceConnectionsResponse>("/api/software-interfaces/connections"),
        requestJson<Record<string, unknown>>("/api/software-interfaces/status"),
      ]);
      setCatalog(nextCatalog);
      setConnections(nextConnections.connections ?? []);
      setGatewayStatus(nextStatus);
    } catch (catalogLoadError) {
      setCatalogError(catalogLoadError instanceof Error ? catalogLoadError.message : labels.catalogLoadFailed);
    } finally {
      setCatalogLoading(false);
    }
  }, [labels.catalogLoadFailed]);

  useEffect(() => {
    void loadSoftwareInterfaces();
  }, [loadSoftwareInterfaces]);

  const connectionsByToolkit = useMemo(() => {
    const map = new Map<string, SoftwareInterfaceConnection>();
    for (const connection of connections) {
      const toolkit = connection.toolkit.trim().toLowerCase();
      if (!map.has(toolkit)) map.set(toolkit, connection);
    }
    return map;
  }, [connections]);

  const categories = useMemo(() => {
    const counts = new Map<string, { id: string; label: string; count: number }>();
    for (const category of catalog?.categories ?? []) counts.set(category.id, { ...category });
    const communication = counts.get("communication") ?? { id: "communication", label: labels.categories.communication, count: 0 };
    communication.count += channels.length;
    communication.label = labels.categories.communication;
    counts.set("communication", communication);
    const ordered = ["communication", "office", "mail_calendar", "docs_storage", "project_management", "development", "crm_sales", "commerce_payments", "social_media", "automation"];
    return ordered
      .map((id) => counts.get(id) ?? { id, label: labels.categories[id as keyof typeof labels.categories] ?? id, count: 0 })
      .filter((category) => category.count > 0 || category.id === "communication");
  }, [catalog?.categories, channels.length, labels]);

  const cards = useMemo<UnifiedCard[]>(() => {
    const softwareCards = (catalog?.interfaces ?? []).map((item) => ({ kind: "software" as const, id: `software-${item.slug}`, category: item.category, item }));
    const channelCards = channels.map(([name, channel]) => ({ kind: "channel" as const, id: `channel-${name}`, category: "communication" as const, name, channel }));
    return [...channelCards, ...softwareCards];
  }, [catalog?.interfaces, channels]);

  const visibleCards = activeCategory === "all" ? cards : cards.filter((card) => card.category === activeCategory);

  async function refreshAll() {
    await Promise.all([loadSoftwareInterfaces(), refetch()]);
  }

  function startEdit(name: string, channel: ChannelStatusItem) {
    setEditingName(name);
    setManagingSoftware(null);
    setDraft(buildDraft(channel));
  }

  function cancelEdit() {
    setEditingName(null);
    setDraft({});
  }

  async function handleSaveEditingChannel() {
    if (!editingName || !editingChannel) return;
    try {
      const result = await updateChannelConfig.mutateAsync({ name: editingName, config: Object.fromEntries(Object.entries(draft)) });
      toast.success(result.message);
      cancelEdit();
    } catch (saveError) {
      toast.error(saveError instanceof Error ? saveError.message : labels.saveFailed);
    }
  }

  async function handleRestart(name: string) {
    try {
      const result = await restartChannel.mutateAsync(name);
      if (result.success) toast.success(result.message);
      else toast.error(result.message);
    } catch (restartError) {
      toast.error(restartError instanceof Error ? restartError.message : labels.restartFailed);
    }
  }

  async function handleToggleEnabled(name: string, enabled: boolean) {
    try {
      const result = await setChannelEnabled.mutateAsync({ name, enabled });
      toast.success(result.message);
    } catch (toggleError) {
      toast.error(toggleError instanceof Error ? toggleError.message : labels.switchFailed);
    }
  }

  async function handleLogoutChannel(name: string, platformLabel?: string) {
    const label = platformLabel ?? name;
    const confirmed = typeof window === "undefined" ? true : window.confirm(labels.logoutConfirm(label));
    if (!confirmed) return;
    try {
      const result = await logoutChannelMutation.mutateAsync(name);
      if (result.success) toast.success(result.message);
      else toast.warning(result.message);
      if (editingName === name) cancelEdit();
    } catch (logoutError) {
      toast.error(logoutError instanceof Error ? logoutError.message : labels.logoutFailed);
    }
  }

  async function openSoftwareManager(item: SoftwareInterfaceItem) {
    setManagingSoftware(item);
    setEditingName(null);
    setManageTools(null);
    setExtraParams("{}");
    setScopes({ read: true, write: true, admin: false });
    setManageLoading(true);
    try {
      const [toolsResponse, scopesResponse] = await Promise.all([
        requestJson<SoftwareInterfaceToolsResponse>(`/api/software-interfaces/${item.slug}/tools`),
        requestJson<SoftwareInterfaceScopes>(`/api/software-interfaces/${item.slug}/scopes`),
      ]);
      setManageTools(toolsResponse);
      if (typeof scopesResponse.read === "boolean") setScopes(scopesResponse);
    } catch (manageError) {
      toast.warning(manageError instanceof Error ? manageError.message : labels.manageLoadFailed);
    } finally {
      setManageLoading(false);
    }
  }

  async function handleAuthorizeSoftware(item: SoftwareInterfaceItem) {
    let parsedExtra: Record<string, unknown> = {};
    try {
      parsedExtra = extraParams.trim() ? (JSON.parse(extraParams) as Record<string, unknown>) : {};
    } catch {
      toast.error(labels.invalidJson);
      return;
    }
    setManageLoading(true);
    try {
      const result = await requestJson<Record<string, unknown>>(`/api/software-interfaces/${item.slug}/authorize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ extra_params: parsedExtra }),
      });
      if (result.status === "not_configured") {
        toast.warning(formatSoftwareDetail(result.detail, labels.notConfigured));
        return;
      }
      const connectUrl = typeof result.connectUrl === "string" ? result.connectUrl : typeof result.connect_url === "string" ? result.connect_url : null;
      if (connectUrl) {
        window.open(connectUrl, "_blank", "noopener,noreferrer");
        toast.success(labels.oauthOpened);
      } else {
        toast.success(labels.authorizeStarted);
      }
      await loadSoftwareInterfaces();
    } catch (authorizeError) {
      toast.error(authorizeError instanceof Error ? authorizeError.message : labels.authorizeFailed);
    } finally {
      setManageLoading(false);
    }
  }

  async function handleLogoutSoftware(item: SoftwareInterfaceItem, connectionId?: string) {
    const confirmed = typeof window === "undefined" ? true : window.confirm(labels.logoutConfirm(item.name));
    if (!confirmed) return;
    setManageLoading(true);
    try {
      const result = await requestJson<Record<string, unknown>>(`/api/software-interfaces/${item.slug}/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ connection_id: connectionId ?? null }),
      });
      if (result.status === "not_configured") toast.warning(formatSoftwareDetail(result.detail, labels.notConfigured));
      else if (result.success === false) toast.warning(formatSoftwareDetail(result.detail, labels.logoutFailed));
      else toast.success(labels.logoutSucceeded);
      await loadSoftwareInterfaces();
    } catch (logoutError) {
      toast.error(logoutError instanceof Error ? logoutError.message : labels.logoutFailed);
    } finally {
      setManageLoading(false);
    }
  }

  async function handleSaveScopes(item: SoftwareInterfaceItem) {
    setManageLoading(true);
    try {
      const result = await requestJson<Record<string, unknown>>(`/api/software-interfaces/${item.slug}/scopes`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(scopes),
      });
      if (result.status === "not_configured") toast.warning(formatSoftwareDetail(result.detail, labels.notConfigured));
      else toast.success(labels.scopesSaved);
    } catch (scopeError) {
      toast.error(scopeError instanceof Error ? scopeError.message : labels.scopesSaveFailed);
    } finally {
      setManageLoading(false);
    }
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <PlugZapIcon className="size-5 text-primary" />
              <h1 className="text-lg font-semibold text-foreground">{labels.title}</h1>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{labels.description}</p>
          </div>
          <Button size="sm" variant="outline" onClick={() => void refreshAll()}>
            <RefreshCcwIcon className="size-4" />
            {labels.refresh}
          </Button>
        </div>
      </header>

      <div className="octo-panel mb-6 rounded-[1.5rem] p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-foreground">{labels.runtimeTitle}</div>
            <p className="text-xs text-muted-foreground">{labels.runtimeDescription}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={status?.service_running ? "default" : "secondary"} className="gap-1">
              {status?.service_running ? <CheckCircleIcon className="size-3" /> : <XCircleIcon className="size-3" />}
              {status?.service_running ? labels.running : labels.stopped}
            </Badge>
            <Badge variant="outline">{labels.messagingCount(channels.length)}</Badge>
            <Badge variant={gatewayStatus?.api_key_configured ? "default" : "secondary"}>{gatewayStatus?.api_key_configured ? labels.liveGateway : labels.notConfigured}</Badge>
          </div>
        </div>
      </div>

      <section className="octo-panel mb-6 rounded-[1.5rem] p-5">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <PlugZapIcon className="size-4 text-primary" />
              {labels.catalogTitle}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{labels.catalogDescription}</p>
          </div>
          <Badge variant="outline">{labels.totalCount(cards.length)}</Badge>
        </div>

        <div className="mb-4 flex flex-wrap gap-2">
          <Button size="sm" variant={activeCategory === "all" ? "default" : "outline"} onClick={() => setActiveCategory("all")}>
            {labels.all}
            <Badge variant="secondary" className="ml-1 text-[10px]">{cards.length}</Badge>
          </Button>
          {categories.map((category) => {
            const Icon = SOFTWARE_INTERFACE_CATEGORY_ICONS[category.id] ?? PlugZapIcon;
            return (
              <Button key={category.id} size="sm" variant={activeCategory === category.id ? "default" : "outline"} onClick={() => setActiveCategory(category.id)}>
                <Icon className="size-3.5" />
                {labels.categories[category.id as keyof typeof labels.categories] ?? category.label}
                <Badge variant="secondary" className="ml-1 text-[10px]">{category.count}</Badge>
              </Button>
            );
          })}
        </div>

        {catalogLoading || isLoading ? (
          <div className="text-sm text-muted-foreground">{t.common.loading}</div>
        ) : catalogError || error ? (
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            {catalogError ?? (error instanceof Error ? error.message : labels.catalogLoadFailed)}
          </div>
        ) : visibleCards.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <ActivityIcon className="mb-3 size-10 opacity-30" />
            <p className="text-sm">{labels.empty}</p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {visibleCards.map((card) => {
              if (card.kind === "channel") {
                const statusBadge = connectionStatus(card.channel);
                const StatusIcon = statusBadge.icon;
                return (
                  <article key={card.id} className="octo-panel octo-management-card flex min-w-0 flex-col justify-between rounded-[1.5rem] p-3 transition-shadow hover:translate-y-[-1px] hover:shadow-[3px_3px_7px_var(--neu-dark-strong),_-3px_-3px_7px_var(--neu-light-strong)]">
                    <div className="mb-3 flex items-start justify-between gap-2">
                      <div className="min-w-0 space-y-1">
                        <div className="flex items-center gap-2">
                          <RadioTowerIcon className="size-4 shrink-0 text-muted-foreground" />
                          <h2 className="min-w-0 break-words text-sm font-medium text-foreground">{card.channel.platform_label ?? card.name}</h2>
                        </div>
                        <p className="line-clamp-2 text-xs text-muted-foreground">{card.channel.description ?? labels.channelDescription}</p>
                      </div>
                      <div className="octo-card-actions">
                        <Button aria-label={labels.editAria(card.channel.platform_label ?? card.name)} className="octo-card-action" onClick={() => startEdit(card.name, card.channel)} size="icon" title={labels.edit} variant="ghost">
                          <Edit3Icon className="size-3.5 text-muted-foreground hover:text-primary" />
                        </Button>
                        <Button aria-label={labels.logoutAria(card.channel.platform_label ?? card.name)} className="octo-card-action" disabled={logoutChannelMutation.isPending} onClick={() => void handleLogoutChannel(card.name, card.channel.platform_label)} size="icon" title={labels.logout} variant="ghost">
                          <LogOutIcon className="size-3.5 text-muted-foreground hover:text-destructive" />
                        </Button>
                      </div>
                    </div>

                    <div className="mt-auto flex items-end justify-between gap-3">
                      <div className="min-w-0 space-y-1.5">
                        <div className="flex flex-wrap gap-1.5">
                          <Badge variant="secondary" className="text-[10px]">{card.channel.integration_mode ?? labels.native}</Badge>
                          <Badge variant="outline" className="text-[10px]">{card.channel.transport ?? labels.unknown}</Badge>
                          <Badge variant="outline" className={statusBadge.className}>
                            <StatusIcon className="size-3" />
                            {labels.channelStatus[statusBadge.labelKey]}
                          </Badge>
                        </div>
                        <div className="line-clamp-1 text-[11px] text-muted-foreground">{card.channel.identity_supported ? labels.identityAware : labels.configOnly} · {card.channel.outbound_configured ? labels.replyRelayReady : labels.replyRelayMissing}</div>
                      </div>
                      <Switch checked={card.channel.enabled !== false} onCheckedChange={(checked) => void handleToggleEnabled(card.name, checked)} />
                    </div>
                  </article>
                );
              }

              const Icon = SOFTWARE_INTERFACE_CATEGORY_ICONS[card.item.category] ?? PlugZapIcon;
              const connection = connectionsByToolkit.get(card.item.slug);
              const state = softwareConnectionState(connection);
              return (
                <article key={card.id} className="octo-panel octo-management-card flex min-w-0 flex-col justify-between rounded-[1.5rem] p-3 transition-shadow hover:translate-y-[-1px] hover:shadow-[3px_3px_7px_var(--neu-dark-strong),_-3px_-3px_7px_var(--neu-light-strong)]">
                  <div className="mb-3 flex items-start justify-between gap-2">
                    <div className="min-w-0 space-y-1">
                      <div className="flex items-center gap-2">
                        <Icon className="size-4 shrink-0 text-muted-foreground" />
                        <h2 className="min-w-0 break-words text-sm font-medium text-foreground">{card.item.name}</h2>
                      </div>
                      <p className="line-clamp-2 text-xs text-muted-foreground">{card.item.description}</p>
                    </div>
                    <div className="octo-card-actions">
                      <Button aria-label={labels.manageAria(card.item.name)} className="octo-card-action" onClick={() => void openSoftwareManager(card.item)} size="icon" title={labels.manage} variant="ghost">
                        <Settings2Icon className="size-3.5 text-muted-foreground hover:text-primary" />
                      </Button>
                      <Button aria-label={labels.logoutAria(card.item.name)} className="octo-card-action" disabled={manageLoading} onClick={() => void handleLogoutSoftware(card.item, connection?.id)} size="icon" title={labels.logout} variant="ghost">
                        <LogOutIcon className="size-3.5 text-muted-foreground hover:text-destructive" />
                      </Button>
                    </div>
                  </div>

                  <div className="mt-auto flex items-end justify-between gap-3">
                    <div className="min-w-0 space-y-1.5">
                      <div className="flex flex-wrap gap-1.5">
                        <Badge variant="secondary" className="text-[10px]">{labels.integrationSource}</Badge>
                        <Badge variant="outline" className="text-[10px]">{card.item.auth_provider}</Badge>
                        <Badge variant={state === "connected" ? "default" : "outline"} className="text-[10px]">{labels.connectionState[state]}</Badge>
                      </div>
                      <div className="line-clamp-1 text-[11px] text-muted-foreground">{connectionLabel(connection) ?? labels.oauthManaged}</div>
                    </div>
                    <Button className="h-7 px-2 text-xs" size="sm" variant={state === "connected" ? "outline" : "default"} onClick={() => void openSoftwareManager(card.item)}>
                      <WrenchIcon className="size-3.5" />
                      {state === "connected" ? labels.manage : labels.connect}
                    </Button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {managingSoftware ? (
        <section className="octo-panel mb-6 rounded-[1.5rem] p-5">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Settings2Icon className="size-4 text-primary" />
                {labels.manageTitle(managingSoftware.name)}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{labels.manageDescription}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">{managingSoftware.slug}</Badge>
              <Badge variant="secondary">{labels.categories[managingSoftware.category as keyof typeof labels.categories] ?? managingSoftware.category}</Badge>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="rounded-2xl border border-border/70 bg-muted/10 p-4">
              <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">{labels.connections}</div>
              {connections.filter((connection) => connection.toolkit.trim().toLowerCase() === managingSoftware.slug).length === 0 ? (
                <p className="text-sm text-muted-foreground">{labels.noConnections}</p>
              ) : (
                <div className="space-y-2">
                  {connections.filter((connection) => connection.toolkit.trim().toLowerCase() === managingSoftware.slug).map((connection) => (
                    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border/70 bg-background/60 px-3 py-2" key={connection.id}>
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-foreground">{connectionLabel(connection)}</div>
                        <div className="font-mono text-[11px] text-muted-foreground">{connection.id}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-[10px]">{connection.status}</Badge>
                        <Button size="sm" variant="outline" onClick={() => void handleLogoutSoftware(managingSoftware, connection.id)}>{labels.logout}</Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="mt-4 grid gap-3">
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{labels.extraParams}</span>
                  <Textarea value={extraParams} onChange={(event) => setExtraParams(event.target.value)} rows={4} className="font-mono text-xs" placeholder={'{"subdomain":"example"}'} />
                </label>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" disabled={manageLoading} onClick={() => void handleAuthorizeSoftware(managingSoftware)}>
                    <ExternalLinkIcon className="size-3.5" />
                    {labels.connect}
                  </Button>
                  <Button size="sm" variant="outline" disabled={manageLoading} onClick={() => void openSoftwareManager(managingSoftware)}>
                    <RefreshCcwIcon className="size-3.5" />
                    {labels.refresh}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setManagingSoftware(null)}>{t.common.close}</Button>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-border/70 bg-muted/10 p-4">
              <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">{labels.scopePreferences}</div>
              <div className="space-y-3">
                {(["read", "write", "admin"] as const).map((key) => (
                  <div className="flex items-center justify-between gap-4 rounded-xl border border-border/70 bg-background/60 px-3 py-2" key={key}>
                    <div>
                      <div className="text-sm font-medium text-foreground">{labels.scopes[key]}</div>
                      <div className="text-xs text-muted-foreground">{labels.scopeDescriptions[key]}</div>
                    </div>
                    <Switch checked={scopes[key]} onCheckedChange={(checked) => setScopes((current) => ({ ...current, [key]: checked }))} />
                  </div>
                ))}
              </div>
              <Button className="mt-3" size="sm" variant="outline" disabled={manageLoading} onClick={() => void handleSaveScopes(managingSoftware)}>
                <SaveIcon className="size-3.5" />
                {labels.saveScopes}
              </Button>
            </div>
          </div>

          <div className="mt-4 rounded-2xl border border-border/70 bg-muted/10 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">{labels.actions}</div>
              <Badge variant="outline">{manageTools?.tools?.length ?? 0}</Badge>
            </div>
            {manageLoading ? (
              <div className="text-sm text-muted-foreground">{t.common.loading}</div>
            ) : manageTools?.status === "not_configured" ? (
              <div className="text-sm text-muted-foreground">{manageTools.detail ?? labels.notConfiguredDescription}</div>
            ) : manageTools?.tools?.length ? (
              <div className="grid gap-2 md:grid-cols-2">
                {manageTools.tools.slice(0, 12).map((tool) => (
                  <div className="rounded-xl border border-border/70 bg-background/60 p-3" key={tool.function?.name ?? Math.random()}>
                    <div className="font-mono text-[11px] font-semibold text-foreground">{tool.function?.name}</div>
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{tool.function?.description ?? labels.noDescription}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">{labels.noActions}</div>
            )}
          </div>
        </section>
      ) : null}

      {editingName && editingChannel ? (
        <section className="octo-panel mb-6 rounded-[1.5rem] p-5">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-foreground">{labels.editTitle(editingChannel.platform_label ?? editingName)}</div>
              <p className="text-xs text-muted-foreground">{labels.editDescription}</p>
            </div>
            <Badge variant="outline" className="text-[10px]">{editingChannel.integration_mode ?? labels.native}</Badge>
          </div>

          {editableFields.length === 0 ? (
            <div className="rounded-2xl border border-border/70 bg-muted/10 p-4 text-sm text-muted-foreground">{labels.noEditableFields}</div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {editableFields.map((field) => (
                <ChannelFieldEditor
                  channelName={editingName}
                  field={field}
                  key={field.name}
                  onChange={(nextValue) => setDraft((current) => ({ ...current, [field.name]: nextValue }))}
                  value={draft[field.name] ?? (field.kind === "boolean" ? false : "")}
                />
              ))}
            </div>
          )}

          {editingName === "qq" || editingName === "wechat" ? <ChannelQRCodeLogin channelName={editingName} onLoginSuccess={() => void refetch()} /> : null}

          <div className="mt-5 grid gap-3 rounded-2xl border border-border/70 bg-muted/10 p-4 text-xs text-muted-foreground">
            {editingChannel.config_path ? <PathRow label={labels.configPath} value={editingChannel.config_path} /> : null}
            {editingChannel.handler_path ? <PathRow label={labels.handler} value={editingChannel.handler_path} /> : null}
            {editingChannel.ingest_path ? <PathRow label={labels.ingestPath} value={editingChannel.ingest_path} /> : null}
            {editingChannel.bridge_project && editingChannel.bridge_project_url ? <PathRow href={editingChannel.bridge_project_url} label={labels.upstreamBridge} value={editingChannel.bridge_project} /> : null}
            {typeof editingChannel.outbound_configured === "boolean" ? <PathRow label={labels.outboundRelay} value={editingChannel.outbound_configured ? labels.configured : labels.notConfigured} /> : null}
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
            <Button disabled={updateChannelConfig.isPending} onClick={cancelEdit} size="sm" variant="outline">{t.common.cancel}</Button>
            <Button disabled={restartChannel.isPending} onClick={() => void handleRestart(editingName)} size="sm" variant="outline">
              <RefreshCcwIcon className="size-3.5" />
              {labels.restart}
            </Button>
            <Button disabled={updateChannelConfig.isPending} onClick={() => void handleSaveEditingChannel()} size="sm">
              <SaveIcon className="size-3.5" />
              {t.common.save}
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
