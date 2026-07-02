"use client";

import {
  CableIcon,
  CheckCircle2Icon,
  FolderKanbanIcon,
  GripVerticalIcon,
  Maximize2Icon,
  Minimize2Icon,
  RotateCcwIcon,
  TerminalIcon,
  UserRoundIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { AgentAvatar } from "@/components/brand/octo-mark";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { BrainResponse } from "@/core/brain/types";
import { useI18n } from "@/core/i18n/hooks";
import { useRuntimeCapabilities } from "@/core/runtime";
import type { RuntimeCapabilities } from "@/core/runtime/types";
import type {
  SystemExecutionCapability,
  SystemExecutionCliResponse,
  SystemExecutionPermissionPolicy,
} from "@/core/system-execution/types";
import {
  type AgentHandle,
  type TaskAgentPermissionMode,
  type TaskArtifactFile,
  type TaskCard,
  type TaskStudioRuntimeResponse,
  type TaskWorkspace,
  type TaskWorkspaceBuilderHistoryEntry,
  type TaskWorkspaceBuilderPreviewResponse,
} from "@/core/task-workspaces";
import { cn } from "@/lib/utils";

import { TaskCardDetailsPanel } from "./task-card-details-panel";
import { TaskCardGraphCanvas } from "./task-card-graph";
import { AgentTranscript } from "./task-workspace-agent-transcript";
import { EmptyState, InspectorMetric } from "./task-workspace-inspector-primitives";
import { statusTone } from "./task-workspace-status";
import { WorkflowResultCard } from "./workflow-result-card";

export type InspectorView =
  | "workflow"
  | "langgraph"
  | "alignment"
  | "card"
  | "agent"
  | "checkpoints"
  | "brain";

type TaskWorkspaceInspectorCopy = {
  template: string;
  currentPhase: string;
  missingInputs: string;
  none: string;
  addGoalForBrain: string;
  taskMode: string;
  agentCount: string;
  selectedRuntime: string;
  capabilityAlignmentTitle: string;
  capabilityAlignmentDescription: string;
  runtimeLabel: string;
  loadingRuntime: string;
  systemExecutionLabel: string;
  loadingSystemExecution: string;
  policySurfaceLabel: string;
  loadingPermissionPolicy: string;
  serverCliLabel: string;
  serverCliDescription: string;
  systemCliBlocked: string;
  policyEnforcedNote: string;
  brainCompilationLabel: string;
  compilingPlan: string;
  cardDetailsTitle: string;
  cardDetailsDescription: string;
  noCardDescription: string;
  boundAgentLabel: string;
  permissionLabel: string;
  agentRoleLabel: string;
  modelLabel: string;
  documentRoleLabel: string;
  canvasPositionLabel: string;
  branchTaskLabel: string;
  promptPreviewLabel: string;
  archiveDocumentsLabel: string;
  selectCardHint: string;
};

interface TaskWorkspaceUnifiedCardProps {
  taskId: string;
  taskWorkspace: TaskWorkspace;
  activeView?: InspectorView;
  selectedCard: TaskCard | null;
  artifacts: TaskArtifactFile[];
  agents: AgentHandle[];
  selectedAgent: AgentHandle | null;
  selectedAgentId: string | null;
  onViewChange?: (view: InspectorView) => void;
  onSelectAgent: (agentId: string) => void;
  studioRuntime: TaskStudioRuntimeResponse | null;
  runtime: RuntimeCapabilities | null | undefined;
  capability: SystemExecutionCapability | null | undefined;
  policy: SystemExecutionPermissionPolicy | null | undefined;
  defaultPermissionMode: TaskAgentPermissionMode;
  allowPrefixes: string[];
  systemCliAllowed: boolean;
  cliScope: "workspace" | "system";
  onCliScopeChange: (scope: "workspace" | "system") => void;
  cliCommand: string;
  onCliCommandChange: (command: string) => void;
  onRunCli: () => void;
  cliPending: boolean;
  cliResponse: SystemExecutionCliResponse | null;
  brainPlan: BrainResponse | null | undefined;
  brainLoading: boolean;
  builderPreview: TaskWorkspaceBuilderPreviewResponse | undefined;
  builderRevision: number;
  builderCurrentDraft: Record<string, unknown>;
  builderAppliedActionIds: string[];
  builderHistoryEntries: TaskWorkspaceBuilderHistoryEntry[];
  builderMutationPending: boolean;
  onApplyBuilderAction: (actionId: string) => void;
  onApplyAllBuilderActions: () => void;
  copy: TaskWorkspaceInspectorCopy;
}

const DEFAULT_CARD_HEIGHT = 760;
const MIN_CARD_HEIGHT = 520;
const HEIGHT_STORAGE_KEY = "octoagent.workspace.unified-card.height";
const VIEW_STORAGE_KEY = "octoagent.workspace.unified-card.view";

function metadataString(metadata: Record<string, unknown>, key: string) {
  const value = metadata[key];
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function formatJsonPreview(payload: Record<string, unknown>) {
  return JSON.stringify(payload, null, 2);
}

function clampHeight(nextHeight: number) {
  if (typeof window === "undefined") {
    return Math.max(MIN_CARD_HEIGHT, nextHeight);
  }
  return Math.max(MIN_CARD_HEIGHT, Math.min(window.innerHeight - 120, nextHeight));
}

export function TaskWorkspaceUnifiedCard({
  taskId,
  taskWorkspace,
  activeView: controlledActiveView,
  selectedCard,
  artifacts,
  agents,
  selectedAgent,
  selectedAgentId,
  onViewChange,
  onSelectAgent,
  studioRuntime,
  runtime,
  capability,
  policy,
  defaultPermissionMode,
  allowPrefixes,
  systemCliAllowed,
  cliScope,
  onCliScopeChange,
  cliCommand,
  onCliCommandChange,
  onRunCli,
  cliPending,
  cliResponse,
  brainPlan,
  brainLoading,
  builderPreview,
  builderRevision,
  builderCurrentDraft,
  builderAppliedActionIds,
  builderHistoryEntries,
  builderMutationPending,
  onApplyBuilderAction,
  onApplyAllBuilderActions,
  copy,
}: TaskWorkspaceUnifiedCardProps) {
  const { t } = useI18n();
  const [localActiveView, setLocalActiveView] = useState<InspectorView>("workflow");
  const [cardHeight, setCardHeight] = useState(DEFAULT_CARD_HEIGHT);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const resizeRef = useRef<{ startY: number; startHeight: number } | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const pointerMoveHandlerRef = useRef<((event: PointerEvent) => void) | null>(null);
  const pointerUpHandlerRef = useRef<(() => void) | null>(null);

  const { runtime: liveRuntime } = useRuntimeCapabilities();
  const effectiveRuntime = runtime ?? liveRuntime;
  const activeView = controlledActiveView ?? localActiveView;

  const updateActiveView = (view: InspectorView) => {
    if (controlledActiveView == null) {
      setLocalActiveView(view);
    }
    onViewChange?.(view);
  };

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const storedHeight = Number(window.localStorage.getItem(HEIGHT_STORAGE_KEY));
    if (Number.isFinite(storedHeight) && storedHeight > 0) {
      setCardHeight(clampHeight(storedHeight));
    }
    if (controlledActiveView != null) {
      return;
    }
    const storedView = window.localStorage.getItem(VIEW_STORAGE_KEY);
    if (
      storedView === "workflow"
      || storedView === "langgraph"
      || storedView === "alignment"
      || storedView === "card"
      || storedView === "agent"
      || storedView === "checkpoints"
      || storedView === "brain"
    ) {
      setLocalActiveView(storedView);
    }
  }, [controlledActiveView]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(HEIGHT_STORAGE_KEY, String(cardHeight));
  }, [cardHeight]);

  useEffect(() => {
    shellRef.current?.style.setProperty("--inspector-card-height", `${cardHeight}px`);
  }, [cardHeight]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(VIEW_STORAGE_KEY, activeView);
  }, [activeView]);

  useEffect(() => {
    if (!isFullscreen || typeof document === "undefined") {
      return undefined;
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isFullscreen]);

  useEffect(() => {
    return () => {
      if (typeof window === "undefined") {
        return;
      }
      if (pointerMoveHandlerRef.current) {
        window.removeEventListener("pointermove", pointerMoveHandlerRef.current);
      }
      if (pointerUpHandlerRef.current) {
        window.removeEventListener("pointerup", pointerUpHandlerRef.current);
      }
    };
  }, []);

  const bookmarkItems = useMemo(
    () => [
      {
        id: "workflow" as const,
        icon: FolderKanbanIcon,
        label: "Result",
      },
      {
        id: "langgraph" as const,
        icon: GripVerticalIcon,
        label: "Flow",
      },
      {
        id: "alignment" as const,
        icon: CableIcon,
        label: "Plan",
      },
      {
        id: "agent" as const,
        icon: UserRoundIcon,
        label: "Agent",
      },
      {
        id: "checkpoints" as const,
        icon: CheckCircle2Icon,
        label: "Check",
      },
    ],
    [],
  );

  const activeBookmark = bookmarkItems.find((item) => item.id === activeView) ?? bookmarkItems[0]!;
  const workflowSummary = studioRuntime?.workflow_summary;
  const runtimeSummary = studioRuntime?.runtime_summary;
  const checkpointSummary = studioRuntime?.checkpoints_summary;
  const readiness = studioRuntime?.readiness;
  const workflowValidationTitle = (() => {
    const [head] = taskWorkspace.name.split("::");
    return head?.trim().length ? head.trim() : taskWorkspace.name;
  })();
  const workflowValidationSubject = (() => {
    const parts = taskWorkspace.name.split("::");
    if (parts.length <= 1) {
      return null;
    }
    return parts.slice(1).join("::").trim() || null;
  })();
  const selectedRuntimeProfile = taskWorkspace.runtime_profiles.find((profile) => profile.selected);
  const activeAgentCount = studioRuntime?.agents.filter((agent) =>
    ["running", "waiting_handoff", "queued"].includes(agent.status),
  ).length ?? taskWorkspace.progress.active_agents;
  const recentTimeline = useMemo(
    () => [...(studioRuntime?.timeline ?? [])].slice(-14).reverse(),
    [studioRuntime?.timeline],
  );

  const startVerticalResize = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    if (typeof window === "undefined") {
      return;
    }

    if (pointerMoveHandlerRef.current) {
      window.removeEventListener("pointermove", pointerMoveHandlerRef.current);
    }
    if (pointerUpHandlerRef.current) {
      window.removeEventListener("pointerup", pointerUpHandlerRef.current);
    }

    resizeRef.current = {
      startY: event.clientY,
      startHeight: cardHeight,
    };

    const handlePointerMove = (moveEvent: PointerEvent) => {
      if (resizeRef.current == null) {
        return;
      }
      const nextHeight = resizeRef.current.startHeight + (moveEvent.clientY - resizeRef.current.startY);
      setCardHeight(clampHeight(nextHeight));
    };

    const handlePointerUp = () => {
      resizeRef.current = null;
      if (pointerMoveHandlerRef.current) {
        window.removeEventListener("pointermove", pointerMoveHandlerRef.current);
      }
      if (pointerUpHandlerRef.current) {
        window.removeEventListener("pointerup", pointerUpHandlerRef.current);
      }
      pointerMoveHandlerRef.current = null;
      pointerUpHandlerRef.current = null;
    };

    pointerMoveHandlerRef.current = handlePointerMove;
    pointerUpHandlerRef.current = handlePointerUp;
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp, { once: true });
  };

  const renderWorkflowOverview = () => (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div
          className="unified-flat-panel rounded-2xl border border-border/60 bg-muted/15 p-4"
          data-testid="workflow-validation-summary-card"
        >
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground/80">
            {workflowValidationTitle}
          </div>
          <div className="mt-2 break-words text-sm font-semibold text-foreground">
            {workflowValidationSubject ?? taskWorkspace.name}
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <InspectorMetric
              label="Mode"
              value={taskWorkspace.mode}
              detail={`status: ${taskWorkspace.status}`}
            />
            <InspectorMetric
              label="Provider"
              value={runtimeSummary?.last_runtime_provider ?? taskWorkspace.agent_runtime_provider}
              detail={runtimeSummary?.latest_runtime_session_id ?? "session pending"}
            />
          </div>
        </div>

        <div
          className="unified-flat-panel rounded-2xl border border-border/60 bg-muted/15 p-4"
          data-testid="workflow-topology-summary-card"
        >
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground/80">
            LangGraph workflow topology
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="text-[10px] capitalize">
              {runtimeSummary?.current_phase ?? taskWorkspace.status}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              {studioRuntime?.agents.length ?? activeAgentCount} agents
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              {studioRuntime?.handoffs.length ?? 0} live handoffs
            </Badge>
            {readiness?.requires_review ? (
              <Badge
                variant="outline"
                className="border-amber-400/60 bg-amber-500/10 text-[10px] text-amber-700 dark:text-amber-300"
              >
                review required
              </Badge>
            ) : null}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
            <span>provider: {runtimeSummary?.last_runtime_provider ?? taskWorkspace.agent_runtime_provider}</span>
            <span>session: {runtimeSummary?.latest_runtime_session_id ?? "unassigned"}</span>
            <span>graph: {runtimeSummary?.langgraph_graph_id ?? "uncompiled"}</span>
          </div>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <InspectorMetric
          label="Phase"
          value={runtimeSummary?.current_phase ?? taskWorkspace.status}
          detail={runtimeSummary?.last_execution_status ?? "No live execution yet"}
        />
        <InspectorMetric
          label="Cards"
          value={`${workflowSummary?.completed_cards ?? taskWorkspace.progress.completed_cards}/${workflowSummary?.cards_total ?? taskWorkspace.progress.total_cards}`}
          detail={`${workflowSummary?.blocked_cards ?? 0} blocked · ${workflowSummary?.queued_cards ?? 0} queued`}
        />
        <InspectorMetric
          label="Agents"
          value={activeAgentCount}
          detail={`${studioRuntime?.agents.length ?? agents.length} tracked handles`}
        />
        <InspectorMetric
          label="Handoffs"
          value={readiness?.active_handoffs ?? studioRuntime?.handoffs.length ?? 0}
          detail={`${studioRuntime?.handoffs.length ?? 0} total`}
        />
        <InspectorMetric
          label="Checkpoints"
          value={checkpointSummary?.total ?? taskWorkspace.checkpoints.length}
          detail={checkpointSummary?.ready_for_review ? "Review ready" : "No pending review gate"}
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
        <div className="unified-flat-panel rounded-2xl border border-border/60 bg-muted/15 p-4">
          <div className="text-sm font-semibold text-foreground">Runtime pulse</div>
          <div className="mt-1 text-xs text-muted-foreground">
            Keep the execution proof compact and always visible.
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <InspectorMetric
              label="Provider"
              value={runtimeSummary?.last_runtime_provider ?? taskWorkspace.agent_runtime_provider}
              detail={runtimeSummary?.last_execution_target ?? "No execution target recorded yet"}
            />
            <InspectorMetric
              label="Graph"
              value={runtimeSummary?.langgraph_graph_id ?? "uncompiled"}
              detail={runtimeSummary?.langgraph_native_runtime ? "Native runtime" : "Compat runtime"}
            />
            <InspectorMetric
              label="Bindings"
              value={readiness?.enabled_bindings ?? 0}
              detail={`${studioRuntime?.bindings.channels.length ?? 0} channels · ${studioRuntime?.bindings.mcp_servers.length ?? 0} mcp`}
            />
            <InspectorMetric
              label="Memory"
              value={runtimeSummary?.memory_guard_state ?? "unknown"}
              detail={runtimeSummary?.project_memory_updated_at ?? "No project memory refresh yet"}
            />
          </div>
        </div>

        <div className="unified-flat-panel rounded-2xl border border-border/60 bg-muted/15 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-foreground">Recent timeline</div>
              <div className="mt-1 text-xs text-muted-foreground">
                Surface the last meaningful runtime signals without forcing page jumps.
              </div>
            </div>
            <Badge variant="outline">{recentTimeline.length} events</Badge>
          </div>
          <div className="mt-4 space-y-3">
            {recentTimeline.length > 0 ? (
              recentTimeline.map((event) => (
                <div className="rounded-2xl border border-border/70 bg-muted/10 px-3 py-3" key={event.event_id}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-medium text-foreground">{event.title}</div>
                    <div className="text-[11px] text-muted-foreground">{event.created_at}</div>
                  </div>
                  {event.summary ? (
                    <div className="mt-1 text-sm text-muted-foreground">{event.summary}</div>
                  ) : null}
                  {event.details.length > 0 ? (
                    <div className="mt-2 text-xs text-muted-foreground">
                      {event.details.slice(0, 2).join(" · ")}
                    </div>
                  ) : null}
                </div>
              ))
            ) : (
              <EmptyState
                title="No timeline entries yet"
                description="Run the workflow to stream runtime events into the unified card."
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );

  const renderWorkflowView = () => (
    <div className="space-y-5" data-testid="workflow-single-layer-content">
      <WorkflowResultCard
        taskId={taskId}
        status={taskWorkspace.status}
        selectedCard={selectedCard}
        taskWorkspace={taskWorkspace}
        artifactsOverride={artifacts}
        className="unified-flat-panel rounded-2xl border-border/60 bg-transparent shadow-none"
        resultViewportClassName="max-h-[56vh]"
      />
    </div>
  );

  const renderLangGraphView = () => (
    <div className="space-y-5" data-testid="workflow-langgraph-content">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <InspectorMetric
          label="Phase"
          value={runtimeSummary?.current_phase ?? taskWorkspace.status}
          detail={runtimeSummary?.last_execution_status ?? "No live execution yet"}
        />
        <InspectorMetric
          label="Cards"
          value={`${workflowSummary?.completed_cards ?? taskWorkspace.progress.completed_cards}/${workflowSummary?.cards_total ?? taskWorkspace.progress.total_cards}`}
          detail={`${workflowSummary?.blocked_cards ?? 0} blocked · ${workflowSummary?.queued_cards ?? 0} queued`}
        />
        <InspectorMetric
          label="Agents"
          value={activeAgentCount}
          detail={`${studioRuntime?.agents.length ?? agents.length} tracked handles`}
        />
        <InspectorMetric
          label="Handoffs"
          value={readiness?.active_handoffs ?? studioRuntime?.handoffs.length ?? 0}
          detail={`${studioRuntime?.handoffs.length ?? 0} total`}
        />
        <InspectorMetric
          label="Checkpoints"
          value={checkpointSummary?.total ?? taskWorkspace.checkpoints.length}
          detail={checkpointSummary?.ready_for_review ? "Review ready" : "No pending review gate"}
        />
      </div>

      <div className="unified-flat-panel rounded-[30px] border border-border/60 bg-muted/10 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3 pb-4">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.24em] text-muted-foreground/80">
              {t.workflows.langgraphTopologyLabel}
            </div>
            <div className="mt-1 text-sm font-semibold text-foreground">
              {workflowValidationSubject ?? taskWorkspace.name}
            </div>
          </div>
          <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
            <Badge variant="outline">{runtimeSummary?.langgraph_graph_id ?? "uncompiled"}</Badge>
            <Badge variant="outline">{runtimeSummary?.latest_runtime_session_id ?? "unassigned"}</Badge>
          </div>
        </div>
        <TaskCardGraphCanvas
          agents={agents}
          cardGraph={taskWorkspace.card_graph}
          className="h-[260px] rounded-[24px] border-border/60 bg-[linear-gradient(180deg,rgba(255,251,235,0.88),rgba(255,255,255,0.94))] dark:bg-[linear-gradient(180deg,rgba(39,39,42,0.94),rgba(24,24,27,0.96))]"
          compactNodes
          preferredProvider={taskWorkspace.agent_runtime_provider}
          runtime={studioRuntime}
          selectedCardId={selectedCard?.card_id ?? null}
          showRuntimeTopologySummary={false}
        />
      </div>

      <div
        className="unified-flat-panel rounded-[28px] border border-border/60 bg-muted/10 p-4"
        data-testid="workflow-execution-log-panel"
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-foreground">{t.workflows.executionLogsTitle}</div>
            <div className="mt-1 text-xs text-muted-foreground">{t.workflows.executionLogsDescription}</div>
          </div>
          <Badge variant="outline">{recentTimeline.length}</Badge>
        </div>

        {recentTimeline.length > 0 ? (
          <ScrollArea className="mt-4 h-[240px] rounded-2xl border border-border/70 bg-background/70">
            <div className="space-y-3 p-3">
              {recentTimeline.map((event) => (
                <div key={event.event_id} className="rounded-2xl border border-border/70 bg-muted/10 px-3 py-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="text-sm font-medium text-foreground">{event.title}</div>
                      <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                        <span>{event.kind}</span>
                        {event.source ? <span>{event.source}</span> : null}
                        <span>{event.created_at}</span>
                      </div>
                    </div>
                    {event.agent_id ? <Badge variant="outline">{event.agent_id}</Badge> : null}
                  </div>
                  {event.summary ? <div className="mt-2 text-sm text-muted-foreground">{event.summary}</div> : null}
                  {event.details.length > 0 ? (
                    <pre className="mt-3 whitespace-pre-wrap rounded-2xl border border-border/70 bg-background p-3 text-xs leading-5 text-foreground">
                      {event.details.join("")}
                    </pre>
                  ) : null}
                </div>
              ))}
            </div>
          </ScrollArea>
        ) : studioRuntime?.run_log ? (
          <pre className="mt-4 whitespace-pre-wrap rounded-2xl border border-border/70 bg-background p-3 text-xs leading-5 text-foreground">
            {studioRuntime.run_log}
          </pre>
        ) : (
          <EmptyState
            title={t.workflows.executionLogsTitle}
            description={t.workflows.noExecutionLogs}
          />
        )}
      </div>

      {renderWorkflowOverview()}
    </div>
  );

  const renderAlignmentView = () => (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <InspectorMetric
          label={copy.runtimeLabel}
          value={effectiveRuntime ? `${effectiveRuntime.agent_limits.max_active_subagents_per_thread}` : copy.loadingRuntime}
          detail={effectiveRuntime ? `${effectiveRuntime.agent_limits.max_total_subagents_per_thread} delegated per thread` : null}
        />
        <InspectorMetric
          label={copy.systemExecutionLabel}
          value={capability ? capability.engine : copy.loadingSystemExecution}
          detail={capability ? `desktop=${String(capability.supports_desktop_control)}` : null}
        />
        <InspectorMetric
          label={copy.policySurfaceLabel}
          value={policy ? policy.policy_id : copy.loadingPermissionPolicy}
          detail={policy ? `default=${policy.default_effect}` : null}
        />
        <InspectorMetric
          label={copy.brainCompilationLabel}
          value={brainLoading ? copy.compilingPlan : brainPlan?.execution_contract.template ?? copy.addGoalForBrain}
          detail={brainPlan?.execution_contract.current_phase ?? null}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div className="unified-flat-panel space-y-4 rounded-2xl border border-border/60 bg-muted/15 p-4">
          <div>
            <div className="text-sm font-semibold text-foreground">{copy.capabilityAlignmentTitle}</div>
            <div className="mt-1 text-xs text-muted-foreground">{copy.capabilityAlignmentDescription}</div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <InspectorMetric
              label="Permission mode"
              value={defaultPermissionMode}
              detail={systemCliAllowed ? "System CLI available" : copy.systemCliBlocked}
            />
            <InspectorMetric
              label="Runtime proof"
              value={studioRuntime?.status ?? taskWorkspace.status}
              detail={studioRuntime?.runtime_summary.current_phase ?? "No runtime phase yet"}
            />
          </div>
          {allowPrefixes.length > 0 ? (
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground/80">Allowed prefixes</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {allowPrefixes.map((prefix) => (
                  <Badge key={prefix} variant="outline">
                    {prefix}
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="unified-flat-panel rounded-2xl border border-border/60 bg-muted/15 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-foreground">{copy.serverCliLabel}</div>
              <div className="mt-1 text-xs text-muted-foreground">{copy.serverCliDescription}</div>
            </div>
            <Badge variant={cliScope === "system" ? "default" : "secondary"}>{cliScope}</Badge>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              size="sm"
              type="button"
              variant={cliScope === "workspace" ? "default" : "outline"}
              onClick={() => onCliScopeChange("workspace")}
            >
              Workspace CLI
            </Button>
            <Button
              size="sm"
              type="button"
              variant={cliScope === "system" ? "default" : "outline"}
              onClick={() => onCliScopeChange("system")}
            >
              System CLI
            </Button>
          </div>
          <div className="mt-4 space-y-3">
            <Input
              placeholder={cliScope === "system" ? "uname -a" : "git status"}
              value={cliCommand}
              onChange={(event) => onCliCommandChange(event.target.value)}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                type="button"
                onClick={onRunCli}
                disabled={cliPending || cliCommand.trim().length === 0 || (cliScope === "system" && !systemCliAllowed)}
              >
                <TerminalIcon className="size-4" />
                Run bounded CLI
              </Button>
              <span className="text-xs text-muted-foreground">
                {cliScope === "system" && !systemCliAllowed
                  ? copy.systemCliBlocked
                  : copy.policyEnforcedNote}
              </span>
            </div>
          </div>
          {cliResponse ? (
            <div className="mt-4 rounded-2xl border border-border/70 bg-muted/10 p-3 text-xs">
              <div className="font-medium text-foreground">
                {cliResponse.result.status} · session {cliResponse.session.session_id}
              </div>
              <div className="mt-2 whitespace-pre-wrap text-muted-foreground">{cliResponse.result.detail}</div>
              {cliResponse.result.last_output ? (
                <pre className="mt-3 overflow-x-auto rounded-2xl border border-border/70 bg-background p-3 text-xs text-foreground">
                  {cliResponse.result.last_output}
                </pre>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );

  const renderCardView = () => (
    <TaskCardDetailsPanel
      agents={agents}
      artifacts={artifacts}
      copy={copy}
      selectedCard={selectedCard}
      showResultDocument={false}
      taskWorkspace={taskWorkspace}
    />
  );

  const renderAgentView = () => {
    if (agents.length === 0 || !selectedAgent) {
      return (
        <EmptyState
          title="No agent selected"
          description="Pick a card-bound agent from the graph or wait for the runtime to register handles."
        />
      );
    }

    return (
      <div className="space-y-4">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {agents.map((agent) => (
            <button
              key={agent.agent_id}
              type="button"
              onClick={() => onSelectAgent(agent.agent_id)}
              className={cn(
                "min-w-[170px] rounded-2xl border px-3 py-3 text-left transition-colors",
                agent.agent_id === selectedAgentId
                  ? "border-primary/40 bg-primary/8 shadow-[0_12px_24px_rgba(59,130,246,0.12)]"
                  : "border-border/70 bg-background/75 hover:bg-muted/20",
              )}
            >
              <div className="flex items-center gap-3">
                <AgentAvatar avatarUrl={metadataString(agent.metadata, "avatar_url")} size={34} />
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-foreground">{agent.name}</div>
                  <div className="truncate text-xs text-muted-foreground">{agent.role}</div>
                </div>
              </div>
            </button>
          ))}
        </div>

        <div className="unified-flat-panel rounded-2xl border border-border/60 bg-muted/15 p-4">
          <div className="flex items-start gap-3">
            <AgentAvatar avatarUrl={metadataString(selectedAgent.metadata, "avatar_url")} size={42} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-base font-semibold text-foreground">{selectedAgent.name}</div>
                <Badge variant={statusTone(selectedAgent.status)}>{selectedAgent.status}</Badge>
              </div>
              <div className="mt-1 text-sm text-muted-foreground">{selectedAgent.task_scope ?? selectedAgent.role}</div>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <InspectorMetric label="Role" value={selectedAgent.role} />
            <InspectorMetric label="Model" value={selectedAgent.model_name ?? "default"} />
            <InspectorMetric label="Messages" value={selectedAgent.conversation.message_count} />
            <InspectorMetric label="Linked card" value={selectedAgent.linked_card_id ?? "unbound"} />
          </div>
        </div>

        <AgentTranscript taskId={taskId} agent={selectedAgent} />
      </div>
    );
  };

  const renderCheckpointView = () => (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        <InspectorMetric label="Total" value={checkpointSummary?.total ?? taskWorkspace.checkpoints.length} />
        <InspectorMetric label="Latest" value={checkpointSummary?.latest ?? "n/a"} />
        <InspectorMetric
          label="Review gate"
          value={checkpointSummary?.ready_for_review ? "ready" : "not required"}
        />
      </div>
      <div className="space-y-3">
        {taskWorkspace.checkpoints.length > 0 ? (
          taskWorkspace.checkpoints.map((checkpoint) => (
            <div className="unified-flat-panel rounded-2xl border border-border/60 bg-muted/15 px-4 py-4" key={checkpoint.checkpoint_id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-foreground">{checkpoint.label}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{checkpoint.task_status}</div>
                </div>
                <Badge variant="outline">{checkpoint.created_at}</Badge>
              </div>
              <div className="mt-3 text-sm text-muted-foreground">
                {checkpoint.note ?? "Task workspace checkpoint saved."}
              </div>
            </div>
          ))
        ) : (
          <EmptyState
            title="No checkpoints yet"
            description="Save checkpoints to preserve task, card, and agent state in a reviewable way."
          />
        )}
      </div>
    </div>
  );

  const renderBrainView = () => (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
        <div className="unified-flat-panel rounded-2xl border border-border/60 bg-muted/15 p-4">
          <div className="text-sm font-semibold text-foreground">Brain contract</div>
          <div className="mt-1 text-xs text-muted-foreground">
            Compact planning proof that stays readable even inside a fixed inspector width.
          </div>
          {brainLoading ? (
            <div className="mt-4 text-sm text-muted-foreground">Compiling plan…</div>
          ) : brainPlan ? (
            <div className="mt-4 space-y-4">
              <div className="rounded-2xl border border-border/70 bg-muted/10 px-4 py-3">
                <div className="text-sm font-medium text-foreground">{brainPlan.decision.recommendation}</div>
                <div className="mt-2 text-sm text-muted-foreground">
                  {brainPlan.decision.rationale.join(" · ")}
                </div>
              </div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <InspectorMetric label={copy.template} value={brainPlan.execution_contract.template} />
                <InspectorMetric label={copy.currentPhase} value={brainPlan.execution_contract.current_phase} />
                <InspectorMetric label={copy.taskMode} value={taskWorkspace.mode} />
                <InspectorMetric
                  label={copy.selectedRuntime}
                  value={selectedRuntimeProfile?.label ?? copy.none}
                />
              </div>
              <div className="rounded-2xl border border-border/70 bg-muted/10 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground/80">
                  {copy.missingInputs}
                </div>
                <div className="mt-2 text-sm text-muted-foreground">
                  {brainPlan.execution_contract.missing_inputs.length > 0
                    ? brainPlan.execution_contract.missing_inputs.join(", ")
                    : copy.none}
                </div>
              </div>
            </div>
          ) : (
            <div className="mt-4 text-sm text-muted-foreground">{copy.addGoalForBrain}</div>
          )}
        </div>

        <div className="unified-flat-panel rounded-2xl border border-border/60 bg-muted/15 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-foreground">Builder actions</div>
              <div className="mt-1 text-xs text-muted-foreground">
                Apply transactional patches without leaving the inspector.
              </div>
            </div>
            <Button
              size="sm"
              type="button"
              onClick={onApplyAllBuilderActions}
              disabled={builderMutationPending || !builderPreview?.builder_action_model.auto_actions.length}
            >
              Apply all
            </Button>
          </div>
          <div className="mt-4 space-y-3">
            {builderPreview?.builder_action_model.auto_actions.length ? (
              builderPreview.builder_action_model.auto_actions.map((action) => {
                const applied = builderAppliedActionIds.includes(action.id);
                return (
                  <div className="rounded-2xl border border-border/70 bg-muted/10 px-4 py-3" key={action.id}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium text-foreground">{action.title}</span>
                          <Badge variant={applied ? "secondary" : "outline"}>{applied ? "applied" : action.status}</Badge>
                        </div>
                        <div className="mt-1 text-sm text-muted-foreground">{action.description}</div>
                      </div>
                      <Button
                        size="sm"
                        type="button"
                        variant="outline"
                        onClick={() => onApplyBuilderAction(action.id)}
                        disabled={builderMutationPending || applied || !Object.keys(action.patch).length}
                      >
                        Apply
                      </Button>
                    </div>
                  </div>
                );
              })
            ) : (
              <EmptyState
                title="No auto actions pending"
                description="Builder actions will appear here once the Brain contract proposes transactional changes."
              />
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="unified-flat-panel rounded-2xl border border-border/60 bg-muted/15 p-4">
          <div className="text-sm font-semibold text-foreground">Draft snapshot</div>
          <div className="mt-1 text-xs text-muted-foreground">revision {builderRevision}</div>
          <pre className="mt-4 max-h-[320px] overflow-auto rounded-2xl border border-border/70 bg-muted/10 p-3 text-xs text-foreground">
            {formatJsonPreview(builderCurrentDraft)}
          </pre>
        </div>
        <div className="unified-flat-panel rounded-2xl border border-border/60 bg-muted/15 p-4">
          <div className="text-sm font-semibold text-foreground">Builder history</div>
          <div className="mt-4 space-y-3">
            {builderHistoryEntries.length > 0 ? (
              builderHistoryEntries.map((entry) => (
                <div className="rounded-2xl border border-border/70 bg-muted/10 px-4 py-3" key={entry.transaction_id}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-foreground">{entry.action_title}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        revision {entry.revision} · {entry.applied_at}
                      </div>
                    </div>
                    <Badge variant="outline">{entry.action_ids.length} actions</Badge>
                  </div>
                </div>
              ))
            ) : (
              <EmptyState
                title="No builder transactions yet"
                description="Applied Brain actions will accumulate here as a compact revision trail."
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );

  const content = (() => {
    switch (activeView) {
      case "alignment":
      case "brain":
        return (
          <div className="space-y-5">
            {renderAlignmentView()}
            {renderBrainView()}
          </div>
        );
      case "langgraph":
        return renderLangGraphView();
      case "card":
      case "agent":
        return (
          <div className="space-y-5">
            {renderCardView()}
            {renderAgentView()}
          </div>
        );
      case "checkpoints":
        return renderCheckpointView();
      case "workflow":
      default:
        return renderWorkflowView();
    }
  })();

  return (
    <>
      {isFullscreen ? (
        <div
          className="fixed inset-0 z-40 bg-background/68 backdrop-blur-sm"
          onClick={() => setIsFullscreen(false)}
        />
      ) : null}
      <div
        ref={shellRef}
        className={cn(
          "relative min-h-0 [--inspector-card-height:760px]",
          isFullscreen ? "fixed inset-x-5 top-24 bottom-5 z-50" : "h-[var(--inspector-card-height)]",
        )}
      >
        <Card className="flex h-full min-h-0 flex-col overflow-hidden rounded-[30px] border-border/80 bg-card shadow-xl">
          <CardHeader className="border-b border-border/70 pb-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="text-base">{activeBookmark.label}</CardTitle>
                  <Badge variant="outline">{taskWorkspace.status}</Badge>
                  {selectedCard ? <Badge variant="secondary">{selectedCard.title}</Badge> : null}
                  {selectedAgent ? <Badge variant="secondary">{selectedAgent.name}</Badge> : null}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="icon"
                  type="button"
                  variant="ghost"
                  onClick={() => setCardHeight(DEFAULT_CARD_HEIGHT)}
                  aria-label="Reset inspector size"
                >
                  <RotateCcwIcon className="size-4" />
                </Button>
                <Button
                  size="icon"
                  type="button"
                  variant="ghost"
                  onClick={() => setIsFullscreen((current) => !current)}
                  aria-label={isFullscreen ? "Exit focus mode" : "Expand inspector"}
                >
                  {isFullscreen ? <Minimize2Icon className="size-4" /> : <Maximize2Icon className="size-4" />}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 p-0">
            <div className="flex h-full min-h-0 flex-col">
              <div className="border-b border-border/70 bg-background/80 px-3 py-2" data-testid="workflow-unified-tab-shell">
                <div
                  className="workflow-bookmark-track flex overflow-x-auto px-1 py-1"
                  aria-label="Workflow inspector tabs"
                  data-testid="workflow-unified-top-tabs"
                  tabIndex={0}
                  onWheel={(event) => {
                    if (event.deltaY !== 0 && event.deltaX === 0) {
                      event.currentTarget.scrollLeft += event.deltaY;
                    }
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "ArrowRight") {
                      event.currentTarget.scrollLeft += 120;
                    } else if (event.key === "ArrowLeft") {
                      event.currentTarget.scrollLeft -= 120;
                    }
                  }}
                >
                  {bookmarkItems.map((item, index) => {
                    const Icon = item.icon;
                    const active = item.id === activeView;
                    const tabInner = (
                      <>
                        <Icon
                          className={cn(
                            "size-4 shrink-0 transition-colors",
                            active
                              ? "text-red-600 dark:text-red-400"
                              : "text-muted-foreground",
                          )}
                          strokeWidth={active ? 2.75 : 1.75}
                        />
                        <span
                          className={cn(
                            "truncate text-[12px] font-medium",
                            active ? "text-foreground" : "text-muted-foreground",
                          )}
                        >
                          {item.label}
                        </span>
                      </>
                    );

                    return (
                      <div
                        key={item.id}
                        className={cn(
                          "workflow-bookmark-stack relative shrink-0",
                          index === 0 ? "ml-0" : "ml-1",
                        )}
                      >
                        <button
                          type="button"
                          aria-current={active ? "page" : undefined}
                          onClick={() => updateActiveView(item.id)}
                          className={cn(
                            "workflow-bookmark-tab group relative inline-flex min-h-[32px] shrink-0 items-center gap-1.5 rounded-[12px] border px-2.5 py-1.5 text-left text-xs transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                            active
                              ? "is-active border-border/80 bg-background text-foreground"
                              : "is-inactive border-transparent bg-transparent text-muted-foreground hover:border-border/70 hover:text-foreground",
                          )}
                        >
                          <span className="relative z-10 inline-flex items-center gap-2">{tabInner}</span>
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="min-h-0 flex-1 bg-background">
                <ScrollArea className="h-full">
                  <div className="p-4 sm:p-5">
                    <div
                      className="unified-single-layer-surface space-y-4"
                      data-testid="workflow-unified-main-surface"
                    >
                      {content}
                    </div>
                  </div>
                </ScrollArea>
              </div>
            </div>
          </CardContent>
          {!isFullscreen ? (
            <div className="border-t border-border/70 px-4 py-2">
              <button
                type="button"
                onPointerDown={startVerticalResize}
                className="flex w-full cursor-row-resize touch-none items-center justify-center gap-2 rounded-full border border-dashed border-border/80 bg-background/65 px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-muted/20"
                aria-label="Resize inspector height"
              >
                <GripVerticalIcon className="size-4 rotate-90" />
                Drag vertically to resize
              </button>
            </div>
          ) : null}
        </Card>
      </div>
    </>
  );
}