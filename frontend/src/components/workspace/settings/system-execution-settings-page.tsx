"use client";

import {
  Clock3Icon,
  CommandIcon,
  CopyIcon,
  LaptopIcon,
  PlayCircleIcon,
  SaveIcon,
  ScanSearchIcon,
  ShieldAlertIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
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
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import {
  useCreateSystemExecutionSession,
  useExecuteSystemCliCommand,
  useExecuteWorkspaceCliCommand,
  usePlanSystemExecution,
  useRuntimeDoctor,
  useSystemExecutionAudit,
  useSystemExecutionCapabilities,
  useSystemExecutionConfig,
  useSystemExecutionSession,
  useSystemExecutionSnapshot,
  useUpdateSystemExecutionConfig,
  type SystemExecutionPlanRequest,
} from "@/core/system-execution";

import { SettingsSection } from "./settings-section";

function splitCommaSeparated(input: string) {
  return input
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function SystemExecutionSettingsPage() {
  const { t } = useI18n();
  const e = t.settings.systemExecution;
  const { capability, isLoading, error } = useSystemExecutionCapabilities();
  const { config } = useSystemExecutionConfig();
  const { doctor } = useRuntimeDoctor();
  const planMutation = usePlanSystemExecution();
  const sessionMutation = useCreateSystemExecutionSession();
  const workspaceCliMutation = useExecuteWorkspaceCliCommand();
  const systemCliMutation = useExecuteSystemCliCommand();
  const updateConfigMutation = useUpdateSystemExecutionConfig();
  const [goal, setGoal] = useState("");
  const [target, setTarget] =
    useState<SystemExecutionPlanRequest["target"]>("desktop");
  const [expectedOutcome, setExpectedOutcome] = useState("");
  const [allowedAppsInput, setAllowedAppsInput] = useState("");
  const [latestRequest, setLatestRequest] = useState<SystemExecutionPlanRequest | null>(
    null,
  );
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [cliScope, setCliScope] = useState<"workspace" | "system">("workspace");
  const [cliCommand, setCliCommand] = useState("pwd");
  const [cliNote, setCliNote] = useState("");
  const [policyEditor, setPolicyEditor] = useState("");
  const { session } = useSystemExecutionSession(sessionId);
  const { snapshot } = useSystemExecutionSnapshot(sessionId);
  const { audit } = useSystemExecutionAudit(sessionId);

  useEffect(() => {
    if (config) {
      setPolicyEditor(JSON.stringify(config, null, 2));
    }
  }, [config]);

  async function handlePlan() {
    const request = {
      goal,
      target,
      require_approval: true,
      allowed_apps: splitCommaSeparated(allowedAppsInput),
      expected_outcome: expectedOutcome || undefined,
    } satisfies SystemExecutionPlanRequest;
    setLatestRequest(request);
    await planMutation.mutateAsync(request);
  }

  async function handleCreateSession() {
    if (!latestRequest) {
      return;
    }
    const session = await sessionMutation.mutateAsync(latestRequest);
    setSessionId(session.session_id);
  }

  async function handleExecuteCli() {
    try {
      const response = await (cliScope === "workspace"
        ? workspaceCliMutation.mutateAsync({ command: cliCommand, note: cliNote || undefined })
        : systemCliMutation.mutateAsync({ command: cliCommand, note: cliNote || undefined }));
      setSessionId(response.session.session_id);
      toast.success("CLI command executed.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "CLI execution failed.");
    }
  }

  async function handleSavePolicy() {
    try {
      const parsed = JSON.parse(policyEditor);
      await updateConfigMutation.mutateAsync(parsed);
      toast.success("System execution config saved.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save config.");
    }
  }

  const latestCliResult = workspaceCliMutation.data ?? systemCliMutation.data;

  return (
    <SettingsSection
      title={e.title}
      description={e.description}
    >
      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-48 w-full rounded-xl" />
        </div>
      ) : error || !capability ? (
        <Card variant="status" className="border-l-destructive">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <ShieldAlertIcon className="size-4" />
              {e.unavailable}
            </CardTitle>
            <CardDescription>
              {error instanceof Error
                ? error.message
                : e.unavailableDesc}
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="space-y-3">
          {/* Capability status */}
          <Card variant="status" className="border-l-emerald-500/60">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <LaptopIcon className="size-4 text-emerald-500" />
                {e.currentCapability}
              </CardTitle>
              <CardAction>
                <div className="flex flex-wrap gap-1.5">
                  <Badge variant={capability.enabled ? "default" : "secondary"} className="text-xs">
                    {capability.enabled ? e.enabled : e.disabled}
                  </Badge>
                  <Badge variant="outline" className="text-xs">{capability.engine}</Badge>
                </div>
              </CardAction>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-1.5">
                <Badge variant={capability.supports_desktop_control ? "default" : "secondary"} className="text-[10px]">
                  {e.desktopControl} {capability.supports_desktop_control ? e.yes : e.no}
                </Badge>
                <Badge variant={capability.supports_window_introspection ? "default" : "secondary"} className="text-[10px]">
                  {e.windowIntrospection} {capability.supports_window_introspection ? e.yes : e.no}
                </Badge>
                <Badge variant={capability.supports_file_open_handoffs ? "default" : "secondary"} className="text-[10px]">
                  {e.fileHandoff} {capability.supports_file_open_handoffs ? e.yes : e.no}
                </Badge>
                <Badge variant={capability.supports_browser_handoff ? "default" : "secondary"} className="text-[10px]">
                  {e.browserHandoff} {capability.supports_browser_handoff ? e.yes : e.no}
                </Badge>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">{capability.note}</p>
            </CardContent>
          </Card>

          {/* Dry-run planner */}
          <Card variant="compact">
            <CardHeader>
              <CardTitle>{e.dryRunPlanner}</CardTitle>
              <CardDescription>
                {e.dryRunPlannerDesc}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <div className="text-xs font-medium">{e.goal}</div>
                  <Textarea
                    className="text-sm"
                    value={goal}
                    onChange={(event) => setGoal(event.target.value)}
                    placeholder={e.goalPlaceholder}
                  />
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  <label className="space-y-1.5">
                    <span className="text-xs font-medium">{e.target}</span>
                    <select
                      className="border-input dark:bg-input/30 h-9 w-full rounded-md border bg-transparent px-3 text-sm"
                      value={target}
                      onChange={(event) =>
                        setTarget(event.target.value as SystemExecutionPlanRequest["target"])
                      }
                    >
                      <option value="desktop">desktop</option>
                      <option value="browser">browser</option>
                      <option value="filesystem">filesystem</option>
                      <option value="hybrid">hybrid</option>
                    </select>
                  </label>
                  <label className="space-y-1.5 md:col-span-2">
                    <span className="text-xs font-medium">{e.allowedApps}</span>
                    <Input
                      value={allowedAppsInput}
                      onChange={(event) => setAllowedAppsInput(event.target.value)}
                      placeholder={e.allowedAppsPlaceholder}
                    />
                  </label>
                </div>
                <div className="space-y-1.5">
                  <div className="text-xs font-medium">{e.expectedOutcome}</div>
                  <Input
                    value={expectedOutcome}
                    onChange={(event) => setExpectedOutcome(event.target.value)}
                    placeholder={e.expectedOutcomePlaceholder}
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() => void handlePlan()}
                    disabled={planMutation.isPending || goal.trim().length === 0}
                  >
                    <PlayCircleIcon className="size-3.5" />
                    {planMutation.isPending ? e.planning : e.generatePlan}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => void handleCreateSession()}
                    disabled={
                      sessionMutation.isPending ||
                      latestRequest == null ||
                      planMutation.data == null
                    }
                  >
                    <Clock3Icon className="size-3.5" />
                    {sessionMutation.isPending ? e.creating : e.createSession}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card variant="compact">
            <CardHeader>
              <CardTitle>Server CLI</CardTitle>
              <CardDescription>Execute bounded workspace_cli or system_cli commands and keep the audit trail in the same operator surface.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="grid gap-3 md:grid-cols-4">
                  <label className="space-y-1.5">
                    <span className="text-xs font-medium">Scope</span>
                    <select className="border-input dark:bg-input/30 h-9 w-full rounded-md border bg-transparent px-3 text-sm" value={cliScope} onChange={(event) => setCliScope(event.target.value as "workspace" | "system") }>
                      <option value="workspace">workspace</option>
                      <option value="system">system</option>
                    </select>
                  </label>
                  <label className="space-y-1.5 md:col-span-3">
                    <span className="text-xs font-medium">Command</span>
                    <Input value={cliCommand} onChange={(event) => setCliCommand(event.target.value)} placeholder="pwd" />
                  </label>
                </div>
                <label className="space-y-1.5">
                  <span className="text-xs font-medium">Operator note</span>
                  <Input value={cliNote} onChange={(event) => setCliNote(event.target.value)} placeholder="Optional audit note" />
                </label>
                <Button size="sm" onClick={() => void handleExecuteCli()} disabled={workspaceCliMutation.isPending || systemCliMutation.isPending || cliCommand.trim().length === 0}>
                  <CommandIcon className="size-3.5" />
                  {workspaceCliMutation.isPending || systemCliMutation.isPending ? "Executing" : "Execute CLI"}
                </Button>

                {latestCliResult ? (
                  <div className="rounded-lg bg-muted/20 p-2.5 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">Latest CLI result</span>
                      <Badge variant="outline" className="text-[10px]">{latestCliResult.result.status}</Badge>
                    </div>
                    <p className="mt-1 text-muted-foreground">{latestCliResult.result.detail}</p>
                    <pre className="mt-2 overflow-x-auto rounded bg-background/70 p-2 text-[11px]">{latestCliResult.result.last_output ?? "(no output)"}</pre>
                  </div>
                ) : null}
              </div>
            </CardContent>
          </Card>

          <Card variant="compact">
            <CardHeader>
              <CardTitle>Permission policy config</CardTitle>
              <CardDescription>Persist the system execution config, including CLI allowlist policy, directly from the operator UI.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <Textarea className="min-h-[240px] font-mono text-xs" value={policyEditor} onChange={(event) => setPolicyEditor(event.target.value)} />
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => void handleSavePolicy()} disabled={updateConfigMutation.isPending || policyEditor.trim().length === 0}><SaveIcon className="size-3.5" />{updateConfigMutation.isPending ? "Saving" : "Save config"}</Button>
                  <Button size="sm" variant="outline" onClick={() => config && setPolicyEditor(JSON.stringify(config, null, 2))}><CopyIcon className="size-3.5" />Reset editor</Button>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card variant="compact">
            <CardHeader>
              <CardTitle>Doctor / preflight</CardTitle>
              <CardDescription>Operator-facing health summary for config, setup workspace, models, CLI policy, and host tools.</CardDescription>
              <CardAction>
                {doctor ? <Badge variant={doctor.overall_status === "fail" ? "destructive" : doctor.overall_status === "warn" ? "secondary" : "default"} className="text-xs">{doctor.overall_status}</Badge> : null}
              </CardAction>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {(doctor?.checks ?? []).map((check) => (
                  <div key={check.id} className="rounded-lg bg-muted/20 p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-xs font-medium">{check.title}</div>
                      <Badge variant={check.status === "fail" ? "destructive" : check.status === "warn" ? "secondary" : "outline"} className="text-[10px]">{check.status}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{check.detail}</p>
                    {check.recommendation ? <p className="mt-1 text-[11px] text-foreground">{check.recommendation}</p> : null}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Plan error */}
          {planMutation.error ? (
            <Card variant="status" className="border-l-destructive">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-destructive">
                  <ShieldAlertIcon className="size-4" />
                  {e.planningFailed}
                </CardTitle>
                <CardDescription>{planMutation.error.message}</CardDescription>
              </CardHeader>
            </Card>
          ) : null}

          {/* Plan result */}
          {planMutation.data ? (
            <Card variant="compact">
              <CardHeader>
                <CardTitle>{e.latestPlan}</CardTitle>
                <CardAction>
                  <div className="flex gap-1.5">
                    <Badge variant="outline" className="text-xs">{planMutation.data.engine}</Badge>
                    <Badge
                      variant={planMutation.data.status === "blocked" ? "destructive" : "secondary"}
                      className="text-xs"
                    >
                      {planMutation.data.status}
                    </Badge>
                  </div>
                </CardAction>
              </CardHeader>
              <CardContent>
                {planMutation.data.missing_capabilities.length ? (
                  <div className="mb-3 flex flex-wrap gap-1.5">
                    {planMutation.data.missing_capabilities.map((item) => (
                      <Badge key={item} variant="destructive" className="text-[10px]">
                        {e.missing} {item}
                      </Badge>
                    ))}
                  </div>
                ) : null}

                <div className="space-y-2">
                  {planMutation.data.steps.map((step) => (
                    <div key={step.id} className="rounded-lg bg-muted/20 p-2.5">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-xs font-medium">{step.title}</div>
                        <Badge variant="outline" className="text-[10px]">{step.kind}</Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{step.description}</p>
                      {step.actions.length ? (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {step.actions.map((action, index) => (
                            <Badge key={`${step.id}-${action.kind}-${index}`} variant="secondary" className="text-[10px]">
                              {action.kind}
                              {action.target ? `:${action.target}` : ""}
                            </Badge>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>

                {planMutation.data.notes.length ? (
                  <div className="mt-3 rounded-lg bg-muted/30 p-2.5 text-xs text-muted-foreground">
                    {planMutation.data.notes.map((note) => (
                      <p key={note}>{note}</p>
                    ))}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          {/* Session */}
          {session ? (
            <Card variant="compact">
              <CardHeader>
                <CardTitle>{e.latestSession}</CardTitle>
                <CardAction>
                  <div className="flex gap-1.5">
                    <Badge variant="outline" className="text-xs">{session.session_id}</Badge>
                    <Badge variant="secondary" className="text-xs">{session.status}</Badge>
                  </div>
                </CardAction>
              </CardHeader>
              <CardContent>
                {snapshot ? (
                  <div className="rounded-lg bg-muted/20 p-2.5">
                    <div className="flex items-center gap-2 text-xs font-medium">
                      <ScanSearchIcon className="size-3.5" />
                      {e.snapshot}
                    </div>
                    <div className="mt-2 space-y-0.5 text-xs text-muted-foreground">
                      <p>{e.activeApp} {snapshot.active_app ?? "—"}</p>
                      <p>{e.activeWindow} {snapshot.active_window ?? "—"}</p>
                      <p>{e.focusedTarget} {snapshot.focused_target ?? "—"}</p>
                      <p>{e.timestamp} {snapshot.timestamp}</p>
                    </div>
                    <p className="mt-2 text-xs">{snapshot.screen_summary}</p>
                  </div>
                ) : null}

                <div className={snapshot ? "mt-3" : ""}>
                  <div className="text-xs font-medium">{e.auditLog}</div>
                  <div className="mt-2 space-y-1.5">
                    {(audit ?? []).length ? (
                      audit!.map((entry, index) => (
                        <div
                          key={`${entry.step_id}-${entry.action_kind}-${index}`}
                          className="rounded-lg bg-muted/20 p-2.5"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="text-xs font-medium">
                              {entry.step_id} · {entry.action_kind}
                            </div>
                            <Badge variant="outline" className="text-[10px]">{entry.status}</Badge>
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">{entry.detail}</p>
                          <p className="text-[10px] text-muted-foreground">{entry.timestamp}</p>
                        </div>
                      ))
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        {e.noAuditEntries}
                      </p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>
      )}
    </SettingsSection>
  );
}
