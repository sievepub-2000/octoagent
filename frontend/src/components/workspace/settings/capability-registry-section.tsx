"use client";

import { AlertTriangleIcon, CommandIcon, DownloadIcon, FileTextIcon, RefreshCcwIcon, ShieldIcon, SparklesIcon, UploadIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useCapabilityCompatPreview,
  useCapabilityPolicies,
  useCapabilityRegistry,
  useExportCapabilityPolicies,
  useImportCapabilityPolicies,
  useUpdateCapabilityCompatSettings,
  useUpdateCapabilityPolicy,
  useUpdateCapabilityState,
} from "@/core/capabilities/hooks";
import type {
  CapabilityCompatPreviewItem,
  CapabilityCompatTrustLevel,
  CapabilityPolicyDecision,
  CapabilityRegistryItem,
  UnifiedCapabilityKind,
} from "@/core/capabilities/types";
import { useI18n } from "@/core/i18n/hooks";

const KIND_ORDER: Array<UnifiedCapabilityKind | "all"> = [
  "all",
  "skill",
  "command",
  "agent_persona",
  "reference",
  "hook",
  "channel",
  "mcp_server",
  "plugin",
];

const POLICY_DECISIONS: CapabilityPolicyDecision[] = ["inherit", "allow", "audit_only", "deny"];

function CapabilityKindLabel({ kind }: { kind: UnifiedCapabilityKind | "all" }) {
  const { t } = useI18n();
  const labels: Record<UnifiedCapabilityKind | "all", string> = {
    all: t.common.all,
    skill: t.settings.system.kindSkill,
    command: t.settings.system.kindCommand,
    agent_persona: t.settings.system.kindAgentPersona,
    reference: t.settings.system.kindReference,
    hook: t.settings.system.kindHook,
    channel: "Channel",
    mcp_server: t.settings.system.kindMcpServer,
    plugin: t.settings.system.kindPlugin,
  };
  return <>{labels[kind]}</>;
}

function resolveCompatItem(
  item: CapabilityRegistryItem,
  compatMap: Map<string, CapabilityCompatPreviewItem>,
) {
  return compatMap.get(item.capability_id) ?? null;
}

function renderBlockerLabel(blocker: string, t: ReturnType<typeof useI18n>["t"]) {
  if (blocker === "compat_disabled") {
    return t.settings.system.compatImportDisabled;
  }
  if (blocker === "trust_required") {
    return t.settings.system.blockedByTrust;
  }
  if (blocker === "name_conflict") {
    return t.settings.system.blockedByConflict;
  }
  return blocker;
}

export function CapabilityRegistrySection() {
  const { t } = useI18n();
  const { registry, isLoading, error, refetch } = useCapabilityRegistry();
  const {
    compatPreview,
    isLoading: compatLoading,
    error: compatError,
    refetch: refetchCompat,
  } = useCapabilityCompatPreview();
  const {
    policyState,
    isLoading: policyLoading,
    error: policyError,
    refetch: refetchPolicies,
  } = useCapabilityPolicies();
  const updateCapability = useUpdateCapabilityState();
  const updateCompatSettings = useUpdateCapabilityCompatSettings();
  const updatePolicy = useUpdateCapabilityPolicy();
  const exportPolicies = useExportCapabilityPolicies();
  const importPolicies = useImportCapabilityPolicies();
  const [filter, setFilter] = useState<UnifiedCapabilityKind | "all">("all");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [policyImportText, setPolicyImportText] = useState("");
  const compatMap = useMemo(
    () => new Map((compatPreview?.items ?? []).map((item) => [item.capability_id, item])),
    [compatPreview],
  );
  const policyMap = useMemo(
    () => new Map((policyState?.policies ?? []).map((item) => [item.capability_id, item])),
    [policyState],
  );

  const filteredItems = useMemo(() => {
    const items = registry?.items ?? [];
    if (filter === "all") {
      return items;
    }
    return items.filter((item) => item.kind === filter);
  }, [filter, registry?.items]);

  async function handleToggle(item: CapabilityRegistryItem) {
    const nextEnabled = !(item.configured_enabled ?? item.enabled);
    setPendingId(item.capability_id);
    try {
      const updated = await updateCapability.mutateAsync({
        capabilityId: item.capability_id,
        enabled: nextEnabled,
      });
      toast.success(
        `${updated.display_name}: ${updated.configured_enabled ? t.settings.system.configuredOn : t.settings.system.configuredOff}`,
      );
    } catch (toggleError) {
      toast.error(toggleError instanceof Error ? toggleError.message : t.settings.system.toggleFailed);
    } finally {
      setPendingId(null);
    }
  }

  async function handleCompatEnabled(enabled: boolean) {
    try {
      await updateCompatSettings.mutateAsync({ enabled });
      toast.success(enabled ? t.settings.system.compatImportEnabled : t.settings.system.compatImportDisabled);
    } catch (compatSettingsError) {
      toast.error(
        compatSettingsError instanceof Error ? compatSettingsError.message : t.settings.system.toggleFailed,
      );
    }
  }

  async function handleTrustLevel(trustLevel: CapabilityCompatTrustLevel) {
    try {
      await updateCompatSettings.mutateAsync({ trustLevel });
      toast.success(
        trustLevel === "trusted"
          ? t.settings.system.trustTrusted
          : t.settings.system.trustUntrusted,
      );
    } catch (compatSettingsError) {
      toast.error(
        compatSettingsError instanceof Error ? compatSettingsError.message : t.settings.system.toggleFailed,
      );
    }
  }

  async function handlePolicyDecision(item: CapabilityRegistryItem, decision: CapabilityPolicyDecision) {
    setPendingId(item.capability_id);
    try {
      await updatePolicy.mutateAsync({
        capabilityId: item.capability_id,
        decision,
        reason: decision === "inherit" ? "operator reset to inherited binding" : `operator selected ${decision}`,
        operator: "webui",
      });
      toast.success(`${item.display_name}: policy ${decision}`);
    } catch (policyUpdateError) {
      toast.error(policyUpdateError instanceof Error ? policyUpdateError.message : t.settings.system.toggleFailed);
    } finally {
      setPendingId(null);
    }
  }

  async function handleExportPolicies() {
    try {
      const payload = await exportPolicies.mutateAsync();
      setPolicyImportText(JSON.stringify(payload, null, 2));
      toast.success("Capability policy export loaded.");
    } catch (exportError) {
      toast.error(exportError instanceof Error ? exportError.message : "Policy export failed.");
    }
  }

  async function handleImportPolicies() {
    try {
      const payload = JSON.parse(policyImportText);
      await importPolicies.mutateAsync({
        payload,
        operator: "webui",
        reason: "webui_policy_import",
      });
      toast.success("Capability policy import completed.");
    } catch (importError) {
      toast.error(importError instanceof Error ? importError.message : "Policy import failed.");
    }
  }

  const blockedCompatItems = (compatPreview?.items ?? []).filter(
    (item) => item.activation_blockers.length > 0 || item.conflicts.length > 0,
  );

  return (
    <div className="mt-4 grid gap-4">
      <Card variant="compact">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>{t.settings.system.compatPreviewTitle}</CardTitle>
              <CardDescription>{t.settings.system.compatPreviewDescription}</CardDescription>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                void refetch();
                void refetchCompat();
                void refetchPolicies();
              }}
            >
              <RefreshCcwIcon className="size-4" />
              {t.settings.system.refresh}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {compatLoading ? (
            <div className="text-sm text-muted-foreground">{t.common.loading}</div>
          ) : compatError ? (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              {compatError instanceof Error ? compatError.message : t.settings.system.sourceUnavailable}
            </div>
          ) : !compatPreview?.source_root ? (
            <div className="rounded-xl border border-border/50 bg-background/60 p-4 text-sm text-muted-foreground">
              {t.settings.system.compatSourceUnavailable}
            </div>
          ) : (
            <>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl border border-border/50 bg-background/60 p-4">
                  <div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{t.settings.system.compatImportLabel}</div>
                  <div className="mt-3 flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-foreground">
                      {compatPreview.enabled ? t.settings.system.compatImportEnabled : t.settings.system.compatImportDisabled}
                    </span>
                    <Switch
                      checked={compatPreview.enabled}
                      onCheckedChange={(checked) => void handleCompatEnabled(checked)}
                    />
                  </div>
                </div>
                <div className="rounded-2xl border border-border/50 bg-background/60 p-4">
                  <div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{t.settings.system.trustLevelLabel}</div>
                  <div className="mt-3 flex gap-2">
                    {(["untrusted", "trusted"] as const).map((level) => (
                      <Button
                        key={level}
                        size="sm"
                        variant={compatPreview.trust_level === level ? "default" : "outline"}
                        onClick={() => void handleTrustLevel(level)}
                      >
                        <ShieldIcon className="size-4" />
                        {level === "trusted" ? t.settings.system.trustTrusted : t.settings.system.trustUntrusted}
                      </Button>
                    ))}
                  </div>
                </div>
                <div className="rounded-2xl border border-border/50 bg-background/60 p-4">
                  <div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{t.settings.system.conflictsLabel}</div>
                  <div className="mt-3 text-2xl font-semibold text-foreground">{compatPreview.conflict_count}</div>
                </div>
                <div className="rounded-2xl border border-border/50 bg-background/60 p-4">
                  <div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{t.settings.system.blockedItemsLabel}</div>
                  <div className="mt-3 text-2xl font-semibold text-foreground">{compatPreview.blocked_count}</div>
                </div>
              </div>

              <div className="rounded-2xl border border-border/50 bg-background/60 p-4 text-sm text-muted-foreground">
                <span className="font-medium text-foreground">{t.settings.system.sourcePathLabel}</span>
                <span className="ml-2 break-all">{compatPreview.source_root}</span>
              </div>

              {blockedCompatItems.length > 0 ? (
                <div className="grid gap-3 xl:grid-cols-2">
                  {blockedCompatItems.slice(0, 6).map((item) => (
                    <div key={item.capability_id} className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium text-foreground">{item.display_name}</div>
                          <p className="mt-1 text-xs text-muted-foreground">{item.source}</p>
                        </div>
                        <Badge variant="outline" className="text-[10px] uppercase">
                          <CapabilityKindLabel kind={item.kind} />
                        </Badge>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {item.activation_blockers.map((blocker) => (
                          <Badge key={`${item.capability_id}:${blocker}`} variant="secondary" className="text-[10px]">
                            {renderBlockerLabel(blocker, t)}
                          </Badge>
                        ))}
                        {item.conflicts.map((conflict) => (
                          <Badge key={`${item.capability_id}:${conflict.capability_id}`} variant="outline" className="text-[10px]">
                            {conflict.name}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>

      <Card variant="compact">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>Operator Policy</CardTitle>
              <CardDescription>Auditable capability allow, deny, and audit-only overlay.</CardDescription>
            </div>
            <Badge variant="outline">
              {policyState?.summary.policy_count ?? 0} policies
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {policyLoading ? (
            <div className="text-sm text-muted-foreground">{t.common.loading}</div>
          ) : policyError ? (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              {policyError instanceof Error ? policyError.message : "Policy state unavailable."}
            </div>
          ) : (
            <>
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-2xl border border-border/50 bg-background/60 p-4">
                  <div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Policy File</div>
                  <p className="mt-2 break-all text-xs text-muted-foreground">{policyState?.policy_path}</p>
                </div>
                <div className="rounded-2xl border border-border/50 bg-background/60 p-4">
                  <div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Audit Events</div>
                  <div className="mt-3 text-2xl font-semibold text-foreground">
                    {policyState?.summary.audit_event_count ?? policyState?.audit_events.length ?? 0}
                  </div>
                </div>
                <div className="rounded-2xl border border-border/50 bg-background/60 p-4">
                  <div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Deny Blocks</div>
                  <div className="mt-3 text-2xl font-semibold text-foreground">
                    {(policyState?.policies ?? []).filter((policy) => policy.decision === "deny").length}
                  </div>
                </div>
              </div>

              {(policyState?.audit_events ?? []).length > 0 ? (
                <div className="grid gap-2">
                  {(policyState?.audit_events ?? []).slice(0, 5).map((event) => (
                    <div key={`${event.created_at}:${event.capability_id}:${event.decision}`} className="rounded-xl border border-border/50 bg-background/60 px-3 py-2 text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{event.capability_id}</span>
                      <span className="mx-2">{event.decision}</span>
                      <span>{event.reason}</span>
                    </div>
                  ))}
                </div>
              ) : null}

              <div className="rounded-2xl border border-border/50 bg-background/60 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-medium text-foreground">Import / Export</div>
                    <p className="mt-1 text-xs text-muted-foreground">Signed JSON policy state for release review and operator handoff.</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" onClick={() => void handleExportPolicies()} disabled={exportPolicies.isPending}>
                      <DownloadIcon className="size-4" />
                      Export
                    </Button>
                    <Button size="sm" onClick={() => void handleImportPolicies()} disabled={importPolicies.isPending || !policyImportText.trim()}>
                      <UploadIcon className="size-4" />
                      Import
                    </Button>
                  </div>
                </div>
                <textarea
                  className="mt-3 min-h-32 w-full rounded-xl border border-border/70 bg-background/70 p-3 font-mono text-xs text-foreground outline-hidden focus:border-primary"
                  value={policyImportText}
                  onChange={(event) => setPolicyImportText(event.target.value)}
                  placeholder='{"version":"capability-operator-policy-v1","state":{"policies":{},"audit_events":[]}}'
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card variant="compact">
        <CardHeader>
          <CardTitle>{t.settings.system.registryTitle}</CardTitle>
          <CardDescription>{t.settings.system.registryDescription}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Tabs value={filter} onValueChange={(value) => setFilter(value as UnifiedCapabilityKind | "all")}> 
            <TabsList variant="line" className="flex flex-wrap">
              {KIND_ORDER.map((kind) => (
                <TabsTrigger key={kind} value={kind}>
                  <CapabilityKindLabel kind={kind} />
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          {isLoading ? (
            <div className="text-sm text-muted-foreground">{t.common.loading}</div>
          ) : error ? (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              {error instanceof Error ? error.message : t.settings.system.sourceUnavailable}
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="rounded-xl border border-border/50 bg-background/60 p-4 text-sm text-muted-foreground">
              {t.settings.system.registryEmpty}
            </div>
          ) : (
            <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
              {filteredItems.map((item) => {
                const compatItem = resolveCompatItem(item, compatMap);
                const linkedSkills = Array.isArray(item.metadata.linked_skills)
                  ? (item.metadata.linked_skills as string[])
                  : [];
                const configuredEnabled = item.configured_enabled ?? item.enabled;
                const effectiveEnabled = compatItem?.projected_enabled ?? item.enabled;
                const operatorPolicy = policyMap.get(item.capability_id);
                const policyDecision = operatorPolicy?.decision ?? "inherit";
                return (
                  <div key={item.capability_id} className="octo-panel flex flex-col justify-between rounded-[1.5rem] p-4">
                    <div className="space-y-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            {item.kind === "command" ? <CommandIcon className="size-4 text-primary" /> : <SparklesIcon className="size-4 text-primary" />}
                            <h3 className="truncate text-sm font-medium text-foreground">{item.display_name}</h3>
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">{item.description || item.source}</p>
                        </div>
                        <Badge variant="outline" className="text-[10px] uppercase">
                          <CapabilityKindLabel kind={item.kind} />
                        </Badge>
                      </div>

                      <div className="flex flex-wrap gap-1.5 text-[10px]">
                        <Badge variant={effectiveEnabled ? "default" : "outline"}>
                          {effectiveEnabled ? t.settings.system.effectiveOn : t.settings.system.effectiveOff}
                        </Badge>
                        <Badge variant="secondary">
                          {configuredEnabled ? t.settings.system.configuredOn : t.settings.system.configuredOff}
                        </Badge>
                        <Badge variant="outline">{item.provider}</Badge>
                      </div>

                      <div className="rounded-xl border border-border/50 bg-background/60 p-3 text-xs text-muted-foreground">
                        <div className="flex items-center gap-2 text-foreground">
                          <FileTextIcon className="size-3.5" />
                          <span>{t.settings.system.sourcePathLabel}</span>
                        </div>
                        <p className="mt-1 break-all">{item.source}</p>
                      </div>

                      {linkedSkills.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5">
                          <span className="text-xs text-muted-foreground">{t.settings.system.linkedSkillsLabel}</span>
                          {linkedSkills.map((linkedSkill) => (
                            <Badge key={`${item.capability_id}:${linkedSkill}`} variant="secondary" className="text-[10px]">
                              {linkedSkill}
                            </Badge>
                          ))}
                        </div>
                      ) : null}

                      {(compatItem?.activation_blockers.length || item.activation_blockers.length) ? (
                        <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-300">
                          <div className="flex items-center gap-2 font-medium">
                            <AlertTriangleIcon className="size-3.5" />
                            <span>{t.settings.system.activationBlocked}</span>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {(compatItem?.activation_blockers ?? item.activation_blockers).map((blocker) => (
                              <Badge key={`${item.capability_id}:${blocker}`} variant="outline" className="text-[10px]">
                                {renderBlockerLabel(blocker, t)}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      ) : null}

                      <div className="rounded-xl border border-border/50 bg-background/60 p-3">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-xs font-medium text-foreground">Operator policy</span>
                          <Badge variant={policyDecision === "deny" ? "destructive" : "outline"} className="text-[10px] uppercase">
                            {policyDecision}
                          </Badge>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {POLICY_DECISIONS.map((decision) => (
                            <Button
                              key={`${item.capability_id}:${decision}`}
                              size="sm"
                              variant={policyDecision === decision ? "default" : "outline"}
                              disabled={pendingId === item.capability_id}
                              onClick={() => void handlePolicyDecision(item, decision)}
                            >
                              {decision}
                            </Button>
                          ))}
                        </div>
                        {operatorPolicy?.reason ? (
                          <p className="mt-2 text-xs text-muted-foreground">{operatorPolicy.reason}</p>
                        ) : null}
                      </div>
                    </div>

                    <div className="mt-4 flex items-center justify-between gap-3">
                      <span className="text-xs text-muted-foreground">
                        {item.configurable ? t.settings.system.toggleSupported : t.settings.system.toggleUnsupported}
                      </span>
                      <Switch
                        checked={configuredEnabled}
                        disabled={!item.configurable || pendingId === item.capability_id}
                        onCheckedChange={() => void handleToggle(item)}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
