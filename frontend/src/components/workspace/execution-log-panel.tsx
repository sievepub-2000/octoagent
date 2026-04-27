"use client";

import {
  ActivityIcon,
  DownloadIcon,
  GitBranchIcon,
  Link2Icon,
  PackageIcon,
  RefreshCwIcon,
  RadioTowerIcon,
  UsersIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getBackendBaseURL } from "@/core/config";
import { useTaskStudioRuntime, useTaskStudioRuntimeEvents } from "@/core/task-workspaces";

function resolveArtifactDownloadURL(downloadURL: string) {
  if (/^https?:\/\//.test(downloadURL)) {
    return downloadURL;
  }
  return `${getBackendBaseURL()}${downloadURL}`;
}

function bindingKey(binding: {
  kind: string;
  label: string;
  source: string;
  binding_id?: string;
}) {
  return binding.binding_id ?? `${binding.kind}:${binding.label}:${binding.source}`;
}

export function ExecutionLogPanel({
  taskId,
  active,
  scrollHeightClass = "h-[520px]",
}: {
  taskId: string | null;
  active: boolean;
  scrollHeightClass?: string;
}) {
  const { studioRuntime, isLoading, refetch } = useTaskStudioRuntime(taskId, {
    enabled: taskId != null,
    refetchInterval: active ? 3000 : false,
  });
  const { studioRuntimeEvents, isLoading: eventsLoading } = useTaskStudioRuntimeEvents(taskId, 0, 12, {
    enabled: taskId != null,
    refetchInterval: active ? 3000 : false,
  });
  const artifacts = studioRuntime?.artifacts ?? [];
  const bindings = studioRuntime?.bindings;
  const channelBindings = bindings?.channels ?? studioRuntime?.channel_bindings ?? [];
  const mcpBindings = bindings?.mcp_servers ?? [];
  const skillBindings = bindings?.skills ?? [];
  const pluginBindings = bindings?.plugins ?? [];
  const activeAgents = (studioRuntime?.agents ?? []).filter((agent) =>
    ["running", "waiting_handoff", "queued"].includes(agent.status),
  );
  const handoffs = studioRuntime?.handoffs ?? [];
  const timeline = studioRuntimeEvents?.events ?? studioRuntime?.timeline ?? [];
  const nextTimelineCursor = studioRuntimeEvents?.next_cursor ?? null;
  const workflowSummary = studioRuntime?.workflow_summary;
  const checkpointSummary = studioRuntime?.checkpoints_summary;
  const readiness = studioRuntime?.readiness;
  const runtimeSummary = studioRuntime?.runtime_summary;
  const runLog = studioRuntime?.run_log ?? "";

  return (
    <Card className="min-h-0 shadow-none">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">Execution log</CardTitle>
            <CardDescription>
              Unified studio runtime snapshot with live archive output, runtime summary, agents, and channel bindings.
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Badge variant="outline">{artifacts.length} artifacts</Badge>
            <Badge variant="outline">{channelBindings.length} bindings</Badge>
            <Badge variant="outline">{handoffs.length} handoffs</Badge>
            <Badge variant={active ? "default" : "outline"}>
              {active ? "Live polling" : "Snapshot"}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs text-muted-foreground">
            {taskId ?? "No task selected"}
          </div>
          <Button
            size="sm"
            type="button"
            variant="outline"
            onClick={() => {
              void refetch();
            }}
            disabled={taskId == null}
          >
            <RefreshCwIcon className="size-4" />
            Refresh
          </Button>
        </div>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="rounded-lg border bg-muted/10 p-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <UsersIcon className="size-4" />
              Active agents
            </div>
            <div className="mt-2 text-2xl font-semibold">{activeAgents.length}</div>
            <div className="mt-1 text-xs text-muted-foreground">
              {studioRuntime ? `${studioRuntime.progress.active_agents} tracked active handles` : "Waiting for runtime snapshot"}
            </div>
          </div>
          <div className="rounded-lg border bg-muted/10 p-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <RadioTowerIcon className="size-4" />
              Channel bindings
            </div>
            <div className="mt-2 text-2xl font-semibold">{channelBindings.filter((binding) => binding.enabled).length}</div>
            <div className="mt-1 text-xs text-muted-foreground">
              {channelBindings.length > 0
                ? channelBindings.slice(0, 2).map((binding) => binding.label).join(" · ")
                : "No workflow-bound channels yet"}
            </div>
          </div>
          <div className="rounded-lg border bg-muted/10 p-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <ActivityIcon className="size-4" />
              Runtime state
            </div>
            <div className="mt-2 text-sm font-semibold">
              {runtimeSummary?.last_execution_status ?? studioRuntime?.status ?? "unknown"}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {runtimeSummary?.last_execution_target ?? runtimeSummary?.latest_query_session_id ?? "No execution target recorded yet"}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Provider proof: {runtimeSummary?.last_runtime_provider ?? "No runtime provider recorded yet"}
            </div>
            {runtimeSummary?.execution_strategy && runtimeSummary.execution_strategy !== "fixed" && (
              <div className="mt-1 text-xs text-muted-foreground">
                Execution strategy: <span className="font-medium">{runtimeSummary.execution_strategy}</span>
              </div>
            )}
          </div>
          <div className="rounded-lg border bg-muted/10 p-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <GitBranchIcon className="size-4" />
              Workflow graph
            </div>
            <div className="mt-2 text-2xl font-semibold">
              {workflowSummary?.active_cards ?? 0}/{workflowSummary?.cards_total ?? 0}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {workflowSummary?.graph_version ?? "No graph version recorded yet"}
            </div>
          </div>
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <div className="rounded-lg border bg-muted/10 p-3">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium">Workflow summary</div>
                <div className="text-xs text-muted-foreground">
                  Shared task graph and review state from the studio runtime contract.
                </div>
              </div>
              <GitBranchIcon className="size-4 text-muted-foreground" />
            </div>
            <div className="grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
              <div className="rounded-md border bg-background px-3 py-2">
                Graph version: {workflowSummary?.graph_version ?? "n/a"}
              </div>
              <div className="rounded-md border bg-background px-3 py-2">
                Review policy: {workflowSummary?.review_policy ?? "adaptive"}
              </div>
              <div className="rounded-md border bg-background px-3 py-2">
                Total cards: {workflowSummary?.cards_total ?? 0}
              </div>
              <div className="rounded-md border bg-background px-3 py-2">
                Active cards: {workflowSummary?.active_cards ?? 0}
              </div>
              <div className="rounded-md border bg-background px-3 py-2">
                Completed cards: {workflowSummary?.completed_cards ?? 0}
              </div>
              <div className="rounded-md border bg-background px-3 py-2">
                Blocked cards: {workflowSummary?.blocked_cards ?? 0}
              </div>
              <div className="rounded-md border bg-background px-3 py-2 md:col-span-2">
                Queued cards: {workflowSummary?.queued_cards ?? 0}
              </div>
            </div>
          </div>
          <div className="rounded-lg border bg-muted/10 p-3">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium">Checkpoint readiness</div>
                <div className="text-xs text-muted-foreground">
                  Unified checkpoint count and review readiness from backend truth.
                </div>
              </div>
              <ActivityIcon className="size-4 text-muted-foreground" />
            </div>
            <div className="grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
              <div className="rounded-md border bg-background px-3 py-2">
                Total checkpoints: {checkpointSummary?.total ?? 0}
              </div>
              <div className="rounded-md border bg-background px-3 py-2">
                Latest checkpoint: {checkpointSummary?.latest ?? "n/a"}
              </div>
              <div className="rounded-md border bg-background px-3 py-2 md:col-span-2">
                Ready for review: {checkpointSummary?.ready_for_review ? "yes" : "no"}
              </div>
            </div>
          </div>
        </div>
        <div className="rounded-lg border bg-muted/10 p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium">Readiness</div>
              <div className="text-xs text-muted-foreground">
                Contract-owned execution and review gates for the current task runtime.
              </div>
            </div>
            <Badge variant={readiness?.requires_review ? "secondary" : "outline"}>
              {readiness?.requires_review ? "Review required" : "Ready state"}
            </Badge>
          </div>
          <div className="grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
            <div className="rounded-md border bg-background px-3 py-2">
              Can run: {readiness?.can_run ? "yes" : "no"}
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Can resume: {readiness?.can_resume ? "yes" : "no"}
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Active handoffs: {readiness?.active_handoffs ?? 0}
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Enabled bindings: {readiness?.enabled_bindings ?? 0}
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Artifact count: {readiness?.artifact_count ?? 0}
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Completed cards: {readiness?.completed_cards ?? 0}
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Queued cards: {readiness?.queued_cards ?? 0}
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Blocked cards: {readiness?.blocked_cards ?? 0}
            </div>
          </div>
        </div>
        <div className="rounded-lg border bg-muted/10 p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium">Studio runtime summary</div>
              <div className="text-xs text-muted-foreground">
                Shared contract for future builder, widget, and SDK surfaces.
              </div>
            </div>
            <Badge variant="outline">{studioRuntime?.status ?? "idle"}</Badge>
          </div>
          <div className="grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
            <div className="rounded-md border bg-background px-3 py-2">
              Latest query session: {runtimeSummary?.latest_query_session_id ?? "n/a"}
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Runtime session: {runtimeSummary?.latest_runtime_session_id ?? "n/a"}
            </div>
              <div className="rounded-md border bg-background px-3 py-2">
                Last runtime provider: {runtimeSummary?.last_runtime_provider ?? "n/a"}
              </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Memory digest: {runtimeSummary?.project_memory_digest ?? "n/a"}
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Last result: {runtimeSummary?.last_agent_result_summary ?? "n/a"}
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Active query sessions: {runtimeSummary?.active_query_sessions ?? 0}
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Active runtime sessions: {runtimeSummary?.active_runtime_sessions ?? 0}
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Memory guard: {runtimeSummary?.memory_guard_state ?? "n/a"}
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Phase: {runtimeSummary?.current_phase ?? "n/a"}
            </div>
            <div className="rounded-md border bg-background px-3 py-2 md:col-span-2">
              Last runtime sync: {runtimeSummary?.last_runtime_sync_at ?? "n/a"}
            </div>
          </div>
        </div>
        <div className="grid gap-3 xl:grid-cols-2">
          <div className="rounded-lg border bg-muted/10 p-3">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium">Bindings</div>
                <div className="text-xs text-muted-foreground">
                  Shared contract for workflow-bound channels, MCP, skills, and plugins.
                </div>
              </div>
              <Link2Icon className="size-4 text-muted-foreground" />
            </div>
            <div className="grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
              <div className="rounded-md border bg-background px-3 py-2">
                Channels: {channelBindings.length}
              </div>
              <div className="rounded-md border bg-background px-3 py-2">
                MCP servers: {mcpBindings.length}
              </div>
              <div className="rounded-md border bg-background px-3 py-2">
                Skills: {skillBindings.length}
              </div>
              <div className="rounded-md border bg-background px-3 py-2">
                Plugins: {pluginBindings.length}
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {[...channelBindings, ...mcpBindings, ...skillBindings, ...pluginBindings].slice(0, 8).map((binding) => (
                <Badge key={bindingKey(binding)} variant={binding.enabled ? "secondary" : "outline"}>
                  {binding.label}
                </Badge>
              ))}
            </div>
          </div>
          <div className="rounded-lg border bg-muted/10 p-3">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium">Recent handoffs</div>
                <div className="text-xs text-muted-foreground">
                  Latest coordination events shaped from workflow runtime and query-session state.
                </div>
              </div>
              <UsersIcon className="size-4 text-muted-foreground" />
            </div>
            {handoffs.length === 0 ? (
              <div className="text-sm text-muted-foreground">No handoff records available yet.</div>
            ) : (
              <div className="grid gap-2">
                {handoffs.slice(0, 4).map((handoff) => (
                  <div className="rounded-md border bg-background px-3 py-2" key={handoff.handoff_id}>
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <span className="font-medium">{handoff.source_agent_id} to {handoff.target_agent_id}</span>
                      <Badge variant="outline">{handoff.status}</Badge>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {handoff.summary ?? handoff.linked_card_id ?? handoff.query_session_id ?? handoff.created_at}
                    </div>
                    <div className="mt-1 text-[11px] text-muted-foreground">
                      {handoff.runtime_session_id ?? "No runtime session linked"}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="rounded-lg border bg-muted/10 p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium">Result artifacts</div>
              <div className="text-xs text-muted-foreground">
                Download generated files from the task archive directory.
              </div>
            </div>
            <PackageIcon className="size-4 text-muted-foreground" />
          </div>
          {isLoading ? (
            <div className="text-sm text-muted-foreground">Loading artifact list…</div>
          ) : artifacts.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              No result artifacts have been saved yet.
            </div>
          ) : (
            <div className="grid gap-2">
              {artifacts.map((artifact) => (
                <div
                  className="flex items-center justify-between gap-3 rounded-md border bg-background px-3 py-2"
                  key={artifact.path}
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{artifact.name}</div>
                    <div className="truncate text-xs text-muted-foreground">
                      {artifact.path}
                    </div>
                  </div>
                  <a
                    href={resolveArtifactDownloadURL(artifact.download_url)}
                    rel="noreferrer"
                    target="_blank"
                  >
                    <Button size="sm" type="button" variant="outline">
                      <DownloadIcon className="size-4" />
                      Download
                    </Button>
                  </a>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="rounded-lg border bg-muted/10 p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium">Timeline</div>
              <div className="text-xs text-muted-foreground">
                Incremental studio runtime events from the shared events API.
              </div>
            </div>
            <ActivityIcon className="size-4 text-muted-foreground" />
          </div>
          {eventsLoading && timeline.length === 0 ? (
            <div className="text-sm text-muted-foreground">Loading timeline events…</div>
          ) : timeline.length === 0 ? (
            <div className="text-sm text-muted-foreground">No timeline events parsed yet.</div>
          ) : (
            <div className="grid gap-2">
              {timeline.slice(0, 6).map((event) => (
                <div className="rounded-md border bg-background px-3 py-2" key={event.event_id}>
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <span className="font-medium">{event.title}</span>
                    <span className="text-xs text-muted-foreground">{event.created_at}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2">
                    {event.source ? <Badge variant="outline">{event.source}</Badge> : null}
                    {event.kind ? <Badge variant="outline">{event.kind}</Badge> : null}
                    {event.agent_id ? <Badge variant="outline">agent {event.agent_id}</Badge> : null}
                    {event.card_id ? <Badge variant="outline">card {event.card_id}</Badge> : null}
                  </div>
                  {event.summary ? (
                    <div className="mt-1 text-xs text-foreground/80">{event.summary}</div>
                  ) : null}
                  {event.details.length > 0 ? (
                    <div className="mt-1 text-xs text-muted-foreground">
                      {event.details.join(" · ")}
                    </div>
                  ) : null}
                </div>
              ))}
              {nextTimelineCursor != null ? (
                <div className="text-xs text-muted-foreground">
                  More events are available via cursor {nextTimelineCursor}.
                </div>
              ) : null}
            </div>
          )}
        </div>
        <ScrollArea className={`${scrollHeightClass} rounded-lg border bg-muted/10 p-3`}>
          {isLoading ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
              <ActivityIcon className="size-5 animate-pulse" />
              Loading execution log…
            </div>
          ) : runLog.trim().length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
              <ActivityIcon className="size-5 opacity-50" />
              No execution log yet.
            </div>
          ) : (
            <pre className="whitespace-pre-wrap break-words text-xs leading-5 text-foreground">
              {runLog}
            </pre>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}