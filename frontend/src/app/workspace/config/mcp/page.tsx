"use client";

import {
  BoxesIcon,
  Edit3Icon,
  PlusIcon,
  SaveIcon,
  ServerIcon,
  Trash2Icon,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import {
  useAddMCPServer,
  useEnableMCPServer,
  useMCPConfig,
  useRemoveMCPServer,
} from "@/core/mcp/hooks";
import { env } from "@/env";

interface MCPFormState {
  name: string;
  description: string;
  type: "stdio" | "sse" | "http";
  command: string;
  args: string;
  url: string;
  env: string;
}

const EMPTY_FORM: MCPFormState = {
  name: "",
  description: "",
  type: "stdio",
  command: "",
  args: "",
  url: "",
  env: "",
};

const MARKITDOWN_PRESET: MCPFormState = {
  name: "markitdown",
  description: "Convert documents to Markdown through the repository-owned MarkItDown command.",
  type: "stdio",
  command: "/home/sieve-pub/public-workspace/octoagent/backend/.venv/bin/markitdown",
  args: "",
  url: "",
  env: "",
};

function serializeEnv(env: Record<string, unknown> | undefined): string {
  if (!env) {
    return "";
  }
  return Object.entries(env)
    .filter(([, value]) => typeof value === "string")
    .map(([key, value]) => `${key}=${value as string}`)
    .join("");
}

function parseEnv(value: string): Record<string, string> {
  return value
    .split(/\r?/)
    .map((line) => line.trim())
    .filter(Boolean)
    .reduce<Record<string, string>>((acc, line) => {
      const separatorIndex = line.indexOf("=");
      if (separatorIndex <= 0) {
        return acc;
      }
      const key = line.slice(0, separatorIndex).trim();
      const envValue = line.slice(separatorIndex + 1).trim();
      if (key) {
        acc[key] = envValue;
      }
      return acc;
    }, {});
}

export default function MCPConfigPage() {
  const { t } = useI18n();
  const { config, isLoading } = useMCPConfig();
  const { mutate: enableMCPServer } = useEnableMCPServer();
  const addServer = useAddMCPServer();
  const removeServer = useRemoveMCPServer();
  const [form, setForm] = useState<MCPFormState>(EMPTY_FORM);
  const [editingServer, setEditingServer] = useState<string | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);

  const isStatic = env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true";
  const servers = config?.mcp_servers ? Object.entries(config.mcp_servers) : [];

  function updateField<K extends keyof MCPFormState>(key: K, value: MCPFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function startEdit(serverName: string) {
    const srv = config?.mcp_servers?.[serverName];
    if (!srv) return;
    const srvAny = srv as Record<string, unknown>;
    setEditingServer(serverName);
    setForm({
      name: serverName,
      description: (srvAny.description as string) ?? "",
      type: (srvAny.type as MCPFormState["type"]) ?? "stdio",
      command: (srvAny.command as string) ?? "",
      args: Array.isArray(srvAny.args) ? (srvAny.args as string[]).join(" ") : "",
      url: (srvAny.url as string) ?? "",
      env: serializeEnv((srvAny.env as Record<string, unknown> | undefined) ?? undefined),
    });
    setIsFormOpen(true);
  }

  function resetForm() {
    setEditingServer(null);
    setForm(EMPTY_FORM);
    setIsFormOpen(false);
  }

  function applyMarkItDownPreset() {
    setEditingServer(null);
    setForm(MARKITDOWN_PRESET);
    setIsFormOpen(true);
  }

  function handleSave() {
    if (!form.name.trim()) return;
    if (form.type === "stdio" && !form.command.trim()) {
      toast.error("Command is required for stdio type.");
      return;
    }
    if (form.type !== "stdio" && !form.url.trim()) {
      toast.error("URL is required for " + form.type.toUpperCase() + " type.");
      return;
    }
    addServer.mutate(
      {
        serverName: form.name.trim(),
        server: {
          enabled: true,
          description: form.description.trim(),
          ...(form.type === "stdio"
            ? {
                type: "stdio",
                command: form.command.trim(),
                args: form.args.split(/\s+/).filter(Boolean),
                env: parseEnv(form.env),
              }
            : { type: form.type, url: form.url.trim(), env: parseEnv(form.env) }),
        },
      },
      {
        onSuccess: () => {
          toast.success(editingServer ? "Server updated." : "Server added.");
          resetForm();
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : "Failed");
        },
      },
    );
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-foreground">{t.sidebar.mcp}</h1>
          <p className="text-sm text-muted-foreground">
            Manage MCP server connections and tool integrations.
          </p>
        </div>
        <Button size="sm" onClick={() => setIsFormOpen(true)}>
          <PlusIcon className="size-4" />
          Add server
        </Button>
      </header>

      <div className="octo-panel mb-6 rounded-[1.5rem] p-5">
        <div className="grid gap-3 lg:grid-cols-2">
          <div className="rounded-[1.25rem] border border-border/60 bg-background/40 p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <ServerIcon className="size-4 text-muted-foreground" />
              Recommended preset: MarkItDown
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Adds the local document-to-Markdown entry backed by the OctoAgent main virtual environment.
            </p>
            <p className="mt-1 text-[11px] font-mono text-muted-foreground">
              /home/sieve-pub/public-workspace/octoagent/backend/.venv/bin/markitdown
            </p>
            <Button size="sm" className="mt-3" variant="outline" disabled={isStatic} onClick={applyMarkItDownPreset}>
              Use preset
            </Button>
          </div>
        </div>
      </div>

      {isFormOpen ? (
      <div className="octo-panel mb-6 rounded-[1.5rem] p-5">
        <div className="mb-3">
          <div className="text-sm font-medium text-foreground">
            {editingServer ? `Edit: ${editingServer}` : "Add MCP Server"}
          </div>
          <p className="text-xs text-muted-foreground">
            Connect a new MCP server via stdio command, SSE, or HTTP endpoint.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">Server name</span>
            <Input value={form.name} disabled={!!editingServer || isStatic} onChange={(e) => updateField("name", e.target.value)} placeholder="my-mcp-server" />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">Description</span>
            <Input value={form.description} disabled={isStatic} onChange={(e) => updateField("description", e.target.value)} placeholder="Optional description" />
          </label>
          <div className="flex items-end gap-2 md:col-span-2">
            <span className="mb-2 text-xs font-medium text-muted-foreground">Type:</span>
            {(["stdio", "sse", "http"] as const).map((tp) => (
              <Button key={tp} size="sm" variant={form.type === tp ? "default" : "outline"} disabled={isStatic} onClick={() => updateField("type", tp)}>
                {tp.toUpperCase()}
              </Button>
            ))}
          </div>
          {form.type === "stdio" ? (
            <>
              <label className="space-y-1">
                <span className="text-xs font-medium text-muted-foreground">Command</span>
                <Input value={form.command} disabled={isStatic} onChange={(e) => updateField("command", e.target.value)} placeholder="npx" />
              </label>
              <label className="space-y-1">
                <span className="text-xs font-medium text-muted-foreground">Args (space-separated)</span>
                <Input value={form.args} disabled={isStatic} onChange={(e) => updateField("args", e.target.value)} placeholder="-y @modelcontextprotocol/server-filesystem" />
              </label>
            </>
          ) : (
            <label className="space-y-1 md:col-span-2">
              <span className="text-xs font-medium text-muted-foreground">URL</span>
              <Input value={form.url} disabled={isStatic} onChange={(e) => updateField("url", e.target.value)} placeholder="http://localhost:3000/sse" />
            </label>
          )}
          <label className="space-y-1 md:col-span-2">
            <span className="text-xs font-medium text-muted-foreground">Environment variables</span>
            <Textarea
              value={form.env}
              disabled={isStatic}
              onChange={(e) => updateField("env", e.target.value)}
              placeholder={"KEY=value"}
              rows={3}
              className="font-mono text-xs"
            />
          </label>
        </div>
        <div className="mt-4 flex gap-2">
          <Button size="sm" disabled={isStatic || addServer.isPending} onClick={handleSave}>
            <SaveIcon className="size-4" />{editingServer ? "Save changes" : "Add server"}
          </Button>
          <Button size="sm" variant="outline" onClick={resetForm}>Close</Button>
        </div>
      </div>
      ) : null}

      {/* Server cards */}
      {isLoading ? (
        <div className="text-sm text-muted-foreground">{t.common.loading}</div>
      ) : servers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <BoxesIcon className="mb-3 size-10 opacity-30" />
          <p className="text-sm">No MCP servers configured yet.</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {servers.map(([name, srv]) => {
            const srvAny = srv as Record<string, unknown>;
            const srvType = (srvAny.type as string) ?? "stdio";
            const srvCmd = srvAny.command as string | undefined;
            const srvArgs = Array.isArray(srvAny.args) ? (srvAny.args as string[]).join(" ") : "";
            const srvUrl = srvAny.url as string | undefined;
            const status = srv.status ?? (srv.enabled ? "ready" : "disabled");
            const statusTone = status === "configuration_error" ? "destructive" : status === "ready" ? "default" : "secondary";
            return (
              <div key={name} className="octo-panel octo-management-card flex min-w-0 flex-col justify-between rounded-[1.5rem] p-3 transition-shadow hover:translate-y-[-1px] hover:shadow-[3px_3px_7px_var(--neu-dark-strong),_-3px_-3px_7px_var(--neu-light-strong)]">
                <div className="mb-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <ServerIcon className="size-4 shrink-0 text-muted-foreground" />
                      <h2 className="min-w-0 break-words text-sm font-medium text-foreground">{name}</h2>
                    </div>
                    <div className="octo-card-actions">
                      <Button
                        aria-label={`Edit ${name}`}
                        size="icon"
                        variant="ghost"
                        className="octo-card-action"
                        title="Edit"
                        onClick={() => startEdit(name)}
                      >
                        <Edit3Icon className="size-3.5 text-muted-foreground hover:text-primary" />
                      </Button>
                      <Button
                        aria-label={`Delete ${name}`}
                        size="icon"
                        variant="ghost"
                        className="octo-card-action"
                        title="Delete"
                        onClick={() => {
                          if (window.confirm(`Remove MCP server "${name}"?`)) {
                            removeServer.mutate({ serverName: name }, {
                              onSuccess: () => toast.success("Server removed."),
                              onError: (err) => toast.error(err instanceof Error ? err.message : "Failed"),
                            });
                          }
                        }}
                      >
                        <Trash2Icon className="size-3.5 text-muted-foreground hover:text-destructive" />
                      </Button>
                    </div>
                  </div>
                  {srv.description && (
                    <p className="mt-1 break-words line-clamp-2 text-xs text-muted-foreground">{srv.description}</p>
                  )}
                  {srv.status_reason ? (
                    <p className="mt-2 line-clamp-2 break-words text-xs text-muted-foreground">{srv.status_reason}</p>
                  ) : null}
                  <div className="mt-2 min-w-0 space-y-0.5 text-[11px] font-mono text-muted-foreground">
                    {srvCmd && <p className="truncate">cmd: {srvCmd} {srvArgs}</p>}
                    {srvUrl && <p className="truncate">url: {srvUrl}</p>}
                  </div>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                    <Badge variant="outline" className="text-[10px] uppercase">{srvType}</Badge>
                    <Badge variant={statusTone} className="text-[10px] uppercase">{status.replace("_", " ")}</Badge>
                  </div>
                  <Switch
                    aria-label={`Enable ${name}`}
                    checked={srv.enabled}
                    disabled={isStatic}
                    onCheckedChange={(checked) => enableMCPServer({ serverName: name, enabled: checked })}
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
