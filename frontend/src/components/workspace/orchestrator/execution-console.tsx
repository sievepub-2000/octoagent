"use client";

import {
  CheckCircle2Icon,
  LoaderCircleIcon,
  RefreshCwIcon,
  ShieldAlertIcon,
  TerminalIcon,
  WavesIcon,
} from "lucide-react";
import { useMemo, useState } from "react";

import { OctoPixelMark } from "@/components/brand/octo-mark";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import { hasToolCalls } from "@/core/messages/utils";
import {
  useExecuteSystemCliCommand,
  useExecuteWorkspaceCliCommand,
  useSystemExecutionAudit,
  useSystemExecutionCapabilities,
  useSystemExecutionSession,
  useSystemExecutionSessions,
} from "@/core/system-execution/hooks";
import type { SystemExecutionCliResponse } from "@/core/system-execution/types";
import { useTaskWorkspaces } from "@/core/task-workspaces";
import { useSubtaskContext } from "@/core/tasks/context";
import { explainLastToolCall } from "@/core/tools/utils";
import { useWorkflows } from "@/core/workflows";

type ExecutionConsoleProps = {
  mode: "flash" | "thinking" | "pro" | "ultra" | undefined;
  isStreaming: boolean;
};

export function ExecutionConsole({
  mode,
  isStreaming,
}: ExecutionConsoleProps) {
  const { t } = useI18n();
  const copy = t.workspace.inspector;
  const { tasks } = useSubtaskContext();
  const { workspaces } = useTaskWorkspaces({ enabled: true });
  const { consoleTab, events, setConsoleTab } = useWorkflows();
  const { capability } = useSystemExecutionCapabilities();
  const workspaceCli = useExecuteWorkspaceCliCommand();
  const systemCli = useExecuteSystemCliCommand();
  const [terminalScope, setTerminalScope] = useState<"workspace" | "system">("workspace");
  const [command, setCommand] = useState("");
  const [note, setNote] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [lookupSessionId, setLookupSessionId] = useState("");
  const [lookupRequestId, setLookupRequestId] = useState<string | null>(null);
  const [lookupValidationMessage, setLookupValidationMessage] = useState<string | null>(null);
  const [relatedTaskId, setRelatedTaskId] = useState("");
  const [latestResponse, setLatestResponse] = useState<SystemExecutionCliResponse | null>(null);
  const {
    session,
    error: sessionError,
    refetch: refetchSession,
  } = useSystemExecutionSession(sessionId, {
    enabled: sessionId != null,
    refetchInterval: sessionId != null ? 1500 : false,
  });
  const terminalAvailable = capability?.enabled ?? false;
  const { sessions: recentSessions } = useSystemExecutionSessions(
    {
      limit: 6,
      relatedTaskId: relatedTaskId || undefined,
      target: terminalScope === "workspace" ? "workspace_cli" : "system_cli",
    },
    {
      enabled: terminalAvailable,
      refetchInterval: sessionId != null ? 1500 : 5000,
    },
  );
  const {
    audit,
    error: auditError,
    refetch: refetchAudit,
  } = useSystemExecutionAudit(sessionId, {
    enabled: sessionId != null,
    refetchInterval: sessionId != null ? 1500 : false,
  });

  const taskList = useMemo(() => Object.values(tasks), [tasks]);
  const terminalPending = workspaceCli.isPending || systemCli.isPending;
  const lookupSessionErrorActive =
    lookupRequestId != null && sessionId != null && lookupRequestId === sessionId && sessionError != null;
  const lookupErrorMessage = lookupValidationMessage ?? (
    lookupSessionErrorActive
      ? sessionError instanceof Error && /404|not found/i.test(sessionError.message)
        ? copy.sessionLookupNotFound
        : copy.sessionLookupFailed
      : null
  );
  const terminalError = workspaceCli.error ?? systemCli.error ?? (lookupSessionErrorActive ? null : sessionError) ?? auditError;

  const terminalSession = session ?? latestResponse?.session ?? null;
  const terminalResult = latestResponse?.result ?? null;
  const terminalOutput = terminalSession?.last_output ?? terminalResult?.last_output ?? null;
  const terminalExitCode = terminalSession?.last_exit_code ?? terminalResult?.last_exit_code ?? null;
  const terminalBlockedReason = terminalSession?.last_blocked_reason ?? null;
  const terminalCommands = terminalSession?.executed_commands ?? [];
  const terminalAudit = audit ?? [];
  const pollingEnabled =
    sessionId != null &&
    (latestResponse?.session.status === "running" ||
      terminalSession?.status === "ready" ||
      terminalSession?.status === "running");
  const terminalLoading = (sessionId != null && terminalSession == null) || terminalPending;

  const commandItems = taskList
    .filter((task) => task.latestMessage && hasToolCalls(task.latestMessage))
    .map((task) => ({
      id: task.id,
      label: explainLastToolCall(task.latestMessage!, t),
      state: task.status,
    }));

  const eventItems =
    events.length > 0
      ? events.map((event) => ({
          id: event.id,
          title: event.title,
          detail: event.detail ?? copy.runtimeEvent,
          state: event.level,
        }))
      : taskList.map((task) => ({
          id: task.id,
          title: task.description,
          detail:
            task.status === "completed"
              ? copy.returnedToMainAgent
              : task.status === "failed"
                ? task.error ?? copy.stepFailed
                : copy.stillRunning,
          state: task.status,
        }));

  async function handleTerminalSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextCommand = command.trim();
    if (!nextCommand || !terminalAvailable || terminalPending) {
      return;
    }

    const payload = {
      command: nextCommand,
      note: note.trim() || undefined,
    };

    const response =
      terminalScope === "workspace"
        ? await workspaceCli.mutateAsync(payload)
        : await systemCli.mutateAsync(payload);

    setLatestResponse(response);
    setSessionId(response.session.session_id);
    setLookupSessionId(response.session.session_id);
    setLookupRequestId(null);
    setLookupValidationMessage(null);
    setCommand("");
    setNote("");
  }

  function handleLookupSession() {
    const nextSessionId = lookupSessionId.trim();
    if (!nextSessionId) {
      setLookupRequestId(null);
      setLookupValidationMessage(copy.sessionLookupRequired);
      return;
    }
    setLookupValidationMessage(null);
    setLookupRequestId(nextSessionId);
    setSessionId(nextSessionId);
  }

  return (
    <Tabs
      className="flex h-full min-h-0 flex-col"
      onValueChange={(value) => setConsoleTab(value as typeof consoleTab)}
      value={consoleTab}
    >
      <TabsList className="w-full justify-start" variant="line">
        <TabsTrigger value="thinking">{copy.thinkingTab}</TabsTrigger>
        <TabsTrigger value="commands">{copy.commandsTab}</TabsTrigger>
        <TabsTrigger value="terminal">{copy.terminalTab}</TabsTrigger>
        <TabsTrigger value="events">{copy.eventsTab}</TabsTrigger>
      </TabsList>

      <TabsContent className="min-h-0 flex-1" value="thinking">
        <ScrollArea className="h-full rounded-xl border">
          <div className="space-y-3 p-4 text-sm">
            <div className="flex items-center gap-2">
              <WavesIcon className="size-4" />
              <span className="font-medium">{copy.reasoningVisibility}</span>
              <Badge variant="secondary">
                {mode === "flash" ? copy.hidden : copy.enabled}
              </Badge>
            </div>
            <p className="text-muted-foreground">
              {mode === "flash"
                ? copy.thinkingFlashDescription
                : copy.thinkingEnabledDescription}
            </p>
            <div className="rounded-lg border bg-muted/30 p-3 text-muted-foreground">
              {isStreaming
                ? copy.streamingDescription
                : copy.idleDescription}
            </div>
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent className="min-h-0 flex-1" value="commands">
        <ScrollArea className="h-full rounded-xl border">
          <div className="space-y-3 p-4 text-sm">
            {commandItems.length === 0 ? (
              <EmptyConsoleState
                description={copy.noCommandActivityDescription}
                icon={<TerminalIcon className="size-4" />}
                title={copy.noCommandActivityYet}
              />
            ) : (
              commandItems.map((item) => (
                <div
                  className="rounded-lg border bg-card px-3 py-2"
                  key={item.id}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{item.label}</span>
                    <Badge variant="secondary">{item.state}</Badge>
                  </div>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent className="min-h-0 flex-1" value="terminal">
        <ScrollArea className="h-full rounded-xl border">
          <div className="space-y-4 p-4 text-sm">
            <div className="rounded-xl border bg-card/60 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div className="rounded-lg border bg-background/80 p-2 shadow-sm">
                    <OctoPixelMark size={26} />
                  </div>
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{copy.terminalHeadline}</span>
                      <Badge variant="secondary">
                        {terminalAvailable ? copy.terminalReady : copy.terminalUnavailable}
                      </Badge>
                      {capability?.engine ? (
                        <Badge variant="outline">{capability.engine}</Badge>
                      ) : null}
                    </div>
                    <p className="max-w-2xl text-muted-foreground">
                      {capability?.note ?? copy.terminalDescription}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <TerminalIcon className="size-4" />
                  <span>
                    {copy.terminalScope}: {terminalScope === "workspace" ? copy.workspaceScope : copy.systemScope}
                  </span>
                </div>
              </div>
            </div>

            <form className="space-y-3 rounded-xl border bg-card/40 p-4" onSubmit={(event) => void handleTerminalSubmit(event)}>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  type="button"
                  variant={terminalScope === "workspace" ? "secondary" : "ghost"}
                  onClick={() => setTerminalScope("workspace")}
                >
                  {copy.workspaceScope}
                </Button>
                <Button
                  size="sm"
                  type="button"
                  variant={terminalScope === "system" ? "secondary" : "ghost"}
                  onClick={() => setTerminalScope("system")}
                >
                  {copy.systemScope}
                </Button>
              </div>

              <div className="space-y-2">
                <label className="font-medium" htmlFor="workflow-cli-command">
                  {copy.commandLabel}
                </label>
                <Input
                  disabled={!terminalAvailable || terminalPending}
                  id="workflow-cli-command"
                  onChange={(event) => setCommand(event.target.value)}
                  placeholder={copy.commandPlaceholder}
                  value={command}
                />
              </div>

              <div className="space-y-2">
                <label className="font-medium" htmlFor="workflow-cli-note">
                  {copy.noteLabel}
                </label>
                <Textarea
                  className="min-h-20 resize-y"
                  disabled={!terminalAvailable || terminalPending}
                  id="workflow-cli-note"
                  onChange={(event) => setNote(event.target.value)}
                  placeholder={copy.notePlaceholder}
                  value={note}
                />
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs text-muted-foreground">{copy.terminalRunHint}</p>
                <Button disabled={!terminalAvailable || terminalPending || command.trim().length === 0} type="submit">
                  {terminalPending ? (
                    <>
                      <LoaderCircleIcon className="size-4 animate-spin" />
                      {copy.runningCommand}
                    </>
                  ) : (
                    copy.runCommand
                  )}
                </Button>
              </div>
            </form>

            <div className="grid gap-3 rounded-xl border bg-card/40 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div className="space-y-2">
                <label className="font-medium" htmlFor="workflow-cli-task-filter">
                  {copy.taskFilterLabel}
                </label>
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  id="workflow-cli-task-filter"
                  onChange={(event) => setRelatedTaskId(event.target.value)}
                  value={relatedTaskId}
                >
                  <option value="">{copy.allTasks}</option>
                  {workspaces.map((workspace) => (
                    <option key={workspace.task_id} value={workspace.task_id}>
                      {workspace.name} · {workspace.task_id}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <label className="font-medium" htmlFor="workflow-cli-session-lookup">
                  {copy.sessionLookupLabel}
                </label>
                <div className="flex gap-2">
                  <Input
                    id="workflow-cli-session-lookup"
                    onChange={(event) => setLookupSessionId(event.target.value)}
                    placeholder={copy.sessionLookupPlaceholder}
                    value={lookupSessionId}
                  />
                  <Button type="button" variant="outline" onClick={handleLookupSession}>
                    {copy.sessionLookupButton}
                  </Button>
                </div>
                {lookupErrorMessage ? (
                  <p className="text-xs text-destructive">{lookupErrorMessage}</p>
                ) : null}
              </div>
            </div>

            {recentSessions.length > 0 ? (
              <div className="rounded-xl border bg-card/40 p-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div className="font-medium">{copy.recentSessions}</div>
                  <Badge variant="outline">{recentSessions.length}</Badge>
                </div>
                <div className="grid gap-2">
                  {recentSessions.map((item) => {
                    const active = item.session_id === sessionId;
                    const sessionCommand =
                      item.last_command ?? item.requested_commands[0] ?? copy.runtimeEvent;
                    return (
                      <button
                        className="flex items-center justify-between gap-3 rounded-lg border bg-background/60 px-3 py-2 text-left transition hover:bg-background"
                        key={item.session_id}
                        onClick={() => {
                          setSessionId(item.session_id);
                          setLookupSessionId(item.session_id);
                          setLookupRequestId(null);
                          setLookupValidationMessage(null);
                        }}
                        type="button"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <Badge variant={active ? "secondary" : "outline"}>
                              {item.target === "workspace_cli" ? copy.workspaceScope : copy.systemScope}
                            </Badge>
                            <span className="truncate font-mono text-xs">{sessionCommand}</span>
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            {item.related_task_name
                              ? `${item.related_task_name} · ${item.session_id}`
                              : item.session_id}
                          </div>
                        </div>
                        <div className="flex flex-col items-end gap-1 text-xs">
                          <Badge variant="outline">{item.status}</Badge>
                          {item.last_exit_code != null ? <span>{copy.exitCode}: {item.last_exit_code}</span> : null}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}

            {terminalError ? (
              <div className="flex items-start gap-3 rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm">
                <ShieldAlertIcon className="mt-0.5 size-4 text-destructive" />
                <div>
                  <div className="font-medium text-destructive">{copy.terminalRequestFailed}</div>
                  <p className="text-muted-foreground">
                    {terminalError instanceof Error ? terminalError.message : copy.stepFailed}
                  </p>
                </div>
              </div>
            ) : null}

            {terminalSession ? (
              <div className="grid gap-3 lg:grid-cols-[1.5fr_1fr]">
                <div className="space-y-3 rounded-xl border bg-card/40 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="font-medium">{copy.latestOutput}</div>
                    <div className="flex flex-wrap items-center gap-2">
                      {pollingEnabled ? (
                        <Badge variant="secondary">{copy.liveSync}</Badge>
                      ) : null}
                      <Badge variant="outline">{terminalSession.status}</Badge>
                      <Badge variant="secondary">{terminalSession.target}</Badge>
                      {terminalExitCode != null ? (
                        <Badge variant="outline">
                          {copy.exitCode}: {terminalExitCode}
                        </Badge>
                      ) : null}
                      <Button
                        className="h-7 px-2"
                        onClick={() => {
                          void Promise.all([refetchSession(), refetchAudit()]);
                        }}
                        size="sm"
                        type="button"
                        variant="ghost"
                      >
                        <RefreshCwIcon className="size-3.5" />
                        {copy.refreshSession}
                      </Button>
                    </div>
                  </div>

                  <div className="rounded-lg border bg-slate-950 px-3 py-3 font-mono text-xs leading-6 text-slate-100">
                    {terminalSession.last_command ? (
                      <div className="mb-2 text-slate-400">$ {terminalSession.last_command}</div>
                    ) : null}
                    {terminalOutput ? (
                      <pre className="overflow-x-auto whitespace-pre-wrap">{terminalOutput}</pre>
                    ) : (
                      <div className="text-slate-400">
                        {terminalLoading ? copy.loadingTerminalOutput : copy.noTerminalOutputYet}
                      </div>
                    )}
                  </div>

                  {terminalBlockedReason ? (
                    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-amber-100">
                      <span className="font-medium">{copy.blockedReason}: </span>
                      <span>{terminalBlockedReason}</span>
                    </div>
                  ) : null}
                </div>

                <div className="space-y-3 rounded-xl border bg-card/40 p-4">
                  <div>
                    <div className="font-medium">{copy.latestSession}</div>
                    <p className="mt-1 break-all text-xs text-muted-foreground">
                      {terminalSession.session_id}
                    </p>
                    {terminalSession.updated_at ? (
                      <p className="mt-1 text-xs text-muted-foreground">
                        {copy.lastUpdated}: {formatTimestamp(terminalSession.updated_at)}
                      </p>
                    ) : null}
                  </div>

                  <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2 lg:grid-cols-1">
                    <div>
                      <span className="font-medium text-foreground">{copy.completedSteps}: </span>
                      {terminalSession.completed_step_ids.length}
                    </div>
                    <div>
                      <span className="font-medium text-foreground">{copy.pendingSteps}: </span>
                      {terminalSession.pending_step_ids.length}
                    </div>
                    <div>
                      <span className="font-medium text-foreground">{copy.recoveryAvailable}: </span>
                      {terminalSession.recovery_available ? copy.enabled : copy.hidden}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="font-medium">{copy.recentCommands}</div>
                    {terminalCommands.length === 0 ? (
                      <p className="text-muted-foreground">{copy.noCommandActivityDescription}</p>
                    ) : (
                      terminalCommands.slice(-4).reverse().map((item, index) => (
                        <div className="rounded-lg border bg-background/60 px-3 py-2 font-mono text-xs" key={`${item}-${index}`}>
                          {item}
                        </div>
                      ))
                    )}
                  </div>

                  <div className="space-y-2">
                    <div className="font-medium">{copy.auditTrail}</div>
                    {terminalAudit.length === 0 ? (
                      <p className="text-muted-foreground">{copy.noTerminalAuditYet}</p>
                    ) : (
                      terminalAudit.slice(-4).reverse().map((entry) => (
                        <div className="rounded-lg border bg-background/60 px-3 py-2" key={`${entry.step_id}-${entry.timestamp}`}>
                          <div className="flex items-center justify-between gap-2 text-xs">
                            <span className="font-medium">{entry.action_kind}</span>
                            <Badge variant="outline">{entry.status}</Badge>
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">{entry.detail}</p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <EmptyConsoleState
                description={copy.noTerminalOutputDescription}
                icon={<OctoPixelMark size={20} />}
                title={copy.noTerminalOutputYet}
              />
            )}
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent className="min-h-0 flex-1" value="events">
        <ScrollArea className="h-full rounded-xl border">
          <div className="space-y-3 p-4 text-sm">
            {eventItems.length === 0 ? (
              <EmptyConsoleState
                description={copy.noRuntimeEventsDescription}
                icon={<CheckCircle2Icon className="size-4" />}
                title={copy.noRuntimeEventsYet}
              />
            ) : (
              eventItems.map((item) => (
                <div
                  className="rounded-lg border bg-card px-3 py-2"
                  key={item.id}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium">{item.title}</span>
                    <Badge variant="secondary">{item.state}</Badge>
                  </div>
                  <p className="mt-1 text-muted-foreground">{item.detail}</p>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </TabsContent>
    </Tabs>
  );
}

function formatTimestamp(value: string) {
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return new Date(parsed).toLocaleString();
}

function EmptyConsoleState({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="flex h-full min-h-[160px] flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-4 py-8 text-center">
      <div className="text-muted-foreground">{icon}</div>
      <div className="font-medium">{title}</div>
      <p className="max-w-md text-muted-foreground">{description}</p>
    </div>
  );
}
