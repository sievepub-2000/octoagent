"use client";

import {
  BrainCircuitIcon,
  CirclePauseIcon,
  PlayIcon,
  RotateCcwIcon,
  SquareIcon,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  TaskWorkspaceUnifiedCard,
  type InspectorView,
} from "@/components/workspace/task-workspace-unified-card";
import { useBrainPlan } from "@/core/brain";
import { useI18n } from "@/core/i18n/hooks";
import { getWorkspaceLocaleCopy } from "@/core/i18n/workspace-copy";
import { useRuntimeCapabilities } from "@/core/runtime";
import {
  useExecuteSystemCliCommand,
  useExecuteWorkspaceCliCommand,
  useSystemExecutionCapabilities,
  useSystemExecutionPermissionPolicy,
  type SystemExecutionCliResponse,
} from "@/core/system-execution";
import {
  useApplyTaskWorkspaceBuilderAction,
  useApplyTaskWorkspaceBuilderActionBatch,
  useCompileTaskWorkspace,
  loadTaskWorkspace,
  useTaskArtifacts,
  useRunTaskWorkspace,
  useTaskAgents,
  useTaskStudioRuntime,
  useTaskWorkspace,
  useTaskWorkspaceAction,
  useTaskWorkspaceBuilderHistory,
  useTaskWorkspaceBuilderPreview,
  type TaskAgentPermissionMode,
  type TaskWorkspace,
} from "@/core/task-workspaces";

function preferredBrainMode(
  mode: TaskWorkspace["mode"],
): "plan" | "research" | "quant" | "policy" {
  if (mode === "group") return "policy";
  if (mode === "branch") return "research";
  return "plan";
}

function statusTone(status: string) {
  if (status === "running" || status === "completed") return "default";
  if (status === "paused" || status === "waiting_review") return "secondary";
  if (status === "failed" || status === "terminated") return "destructive";
  return "outline";
}

function optimisticWorkspaceStatus(
  status: TaskWorkspace["status"] | null | undefined,
  options: {
    runPending: boolean;
    pausePending: boolean;
    resumePending: boolean;
    terminatePending: boolean;
  },
): TaskWorkspace["status"] {
  if (options.terminatePending) {
    return "terminated";
  }
  if (options.pausePending) {
    return "paused";
  }
  if (options.runPending || options.resumePending) {
    return "running";
  }
  return status ?? "created";
}

function metadataString(metadata: Record<string, unknown>, key: string) {
  const value = metadata[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function inspectorViewFromTab(tab: string | null | undefined): InspectorView {
  if (tab === "agents") return "agent";
  if (tab === "brain") return "brain";
  if (tab === "checkpoints") return "checkpoints";
  return "workflow";
}

function tabFromInspectorView(view: InspectorView): string | null {
  if (view === "agent") return "agents";
  if (view === "brain") return "brain";
  if (view === "checkpoints") return "checkpoints";
  return null;
}

export function TaskWorkspaceBoardSingleCard({
  initialTab,
  taskId,
}: {
  initialTab?: string;
  taskId: string | null;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { locale } = useI18n();
  const copy = getWorkspaceLocaleCopy(locale);
  const [activeInspectorView, setActiveInspectorView] = useState<InspectorView>(
    inspectorViewFromTab(initialTab),
  );
  const [detailRefetchInterval, setDetailRefetchInterval] = useState<number | false>(3000);
  const { taskWorkspace, error, isLoading } = useTaskWorkspace(taskId, {
    refetchInterval: detailRefetchInterval,
  });
  const { agents } = useTaskAgents(taskId, { refetchInterval: detailRefetchInterval });
  const { studioRuntime } = useTaskStudioRuntime(taskId, {
    enabled: taskId != null,
    refetchInterval: detailRefetchInterval,
  });
  const { runtime } = useRuntimeCapabilities();
  const { artifacts } = useTaskArtifacts(taskId, {
    enabled: taskId != null,
    refetchInterval: detailRefetchInterval,
  });
  const { capability } = useSystemExecutionCapabilities();
  const { policy } = useSystemExecutionPermissionPolicy();
  const executeWorkspaceCli = useExecuteWorkspaceCliCommand();
  const executeSystemCli = useExecuteSystemCliCommand();
  const [fallbackTaskWorkspace, setFallbackTaskWorkspace] =
    useState<TaskWorkspace | null>(null);
  const [fallbackError, setFallbackError] = useState<string | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedCardId] = useState<string | null>(null);
  const [cliScope, setCliScope] = useState<"workspace" | "system">("workspace");
  const [cliCommand, setCliCommand] = useState("");
  const [cliResponse, setCliResponse] =
    useState<SystemExecutionCliResponse | null>(null);
  const pauseTask = useTaskWorkspaceAction(taskId ?? "", "pause");
  const resumeTask = useTaskWorkspaceAction(taskId ?? "", "resume");
  const terminateTask = useTaskWorkspaceAction(taskId ?? "", "terminate");
  const compileTask = useCompileTaskWorkspace(taskId ?? "");
  const runTask = useRunTaskWorkspace(taskId ?? "");
  const { builderPreview, refetch: refetchBuilderPreview } =
    useTaskWorkspaceBuilderPreview(taskId, {
      enabled: taskId != null && activeInspectorView === "brain",
    });
  const { builderHistory } = useTaskWorkspaceBuilderHistory(taskId, {
    enabled: taskId != null && activeInspectorView === "brain",
  });
  const applyBuilderAction = useApplyTaskWorkspaceBuilderAction(taskId ?? "");
  const applyBuilderActionBatch = useApplyTaskWorkspaceBuilderActionBatch(taskId ?? "");

  const selectedAgent =
    agents.find((agent) => agent.agent_id === selectedAgentId) ?? agents[0] ?? null;
  const effectiveTaskWorkspace = taskWorkspace ?? fallbackTaskWorkspace;
  const effectiveWorkspaceStatus = optimisticWorkspaceStatus(effectiveTaskWorkspace?.status, {
    runPending: runTask.isPending,
    pausePending: pauseTask.isPending,
    resumePending: resumeTask.isPending,
    terminatePending: terminateTask.isPending,
  });
  const selectedCard =
    effectiveTaskWorkspace?.card_graph.cards.find((card) => card.card_id === selectedCardId)
      ?? effectiveTaskWorkspace?.card_graph.cards[0]
      ?? null;
  const defaultPermissionMode =
    (metadataString(
      effectiveTaskWorkspace?.metadata ?? {},
      "default_permission_mode",
    ) as TaskAgentPermissionMode | null) ?? "workspace";
  const systemCliAllowed =
    defaultPermissionMode === "system" || defaultPermissionMode === "yolo";
  const policyShellRules = (policy?.rules ?? []).filter((rule) => rule.scope === "shell");
  const allowPrefixes = policyShellRules
    .filter((rule) => rule.effect === "allow")
    .flatMap((rule) => rule.match_prefixes)
    .slice(0, 8);
  const cliPending = executeWorkspaceCli.isPending || executeSystemCli.isPending;

  const brainPayload = useMemo(() => {
    if (!effectiveTaskWorkspace || effectiveTaskWorkspace.goal.trim().length === 0) {
      return null;
    }
    return {
      user_goal: effectiveTaskWorkspace.goal,
      constraints: [
        `task_mode:${effectiveTaskWorkspace.mode}`,
        `task_status:${effectiveTaskWorkspace.status}`,
      ],
      evidence: effectiveTaskWorkspace.summary ? [effectiveTaskWorkspace.summary] : [],
      preferred_mode: preferredBrainMode(effectiveTaskWorkspace.mode),
      factor_candidates: [],
      risk_limits: [],
      memory_hints: [],
    };
  }, [effectiveTaskWorkspace]);
  const { brainPlan, isLoading: brainLoading } = useBrainPlan(brainPayload);
  const builderCurrentDraft =
    builderPreview?.current_draft ?? builderHistory?.current_draft ?? {};
  const builderRevision = builderHistory?.revision ?? builderPreview?.revision ?? 0;
  const builderAppliedActionIds =
    builderPreview?.applied_action_ids ?? builderHistory?.applied_action_ids ?? [];
  const builderHistoryEntries = builderHistory?.history ?? builderPreview?.history ?? [];
  const builderMutationPending =
    applyBuilderAction.isPending || applyBuilderActionBatch.isPending;

  useEffect(() => {
    if (taskId == null || taskWorkspace != null || fallbackTaskWorkspace != null) {
      return;
    }

    let cancelled = false;

    void loadTaskWorkspace(taskId)
      .then((workspace) => {
        if (!cancelled) {
          setFallbackError(null);
          setFallbackTaskWorkspace(workspace);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setFallbackError(
            loadError instanceof Error ? loadError.message : "Failed to load task workspace.",
          );
          setFallbackTaskWorkspace(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [fallbackTaskWorkspace, taskId, taskWorkspace]);

  useEffect(() => {
    if (taskId == null) {
      setDetailRefetchInterval(false);
      return;
    }
    const status = effectiveTaskWorkspace?.status ?? taskWorkspace?.status ?? null;
    const nextInterval =
      status == null || status === "running" || status === "planned" || status === "waiting_review"
        ? 3000
        : false;
    setDetailRefetchInterval((current) => (current === nextInterval ? current : nextInterval));
  }, [effectiveTaskWorkspace?.status, taskId, taskWorkspace?.status]);

  useEffect(() => {
    setActiveInspectorView(inspectorViewFromTab(searchParams.get("tab")));
  }, [searchParams]);

  if (taskId == null) {
    return (
      <Card className="min-h-[320px] justify-center border-dashed shadow-none">
        <CardHeader>
          <CardTitle>No task selected</CardTitle>
          <CardDescription>
            Create a task from the top task bar to start a card-based workspace.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (isLoading || !effectiveTaskWorkspace) {
    const errorMessage =
      fallbackError ??
      (error instanceof Error ? error.message : null);
    return (
      <Card className="min-h-[320px] justify-center shadow-none">
        <CardHeader>
          <CardTitle>
            {errorMessage ? "Task workspace unavailable" : "Loading task workspace…"}
          </CardTitle>
          {errorMessage ? <CardDescription>{errorMessage}</CardDescription> : null}
        </CardHeader>
      </Card>
    );
  }

  const runServerCli = async () => {
    const command = cliCommand.trim();
    if (!command) {
      return;
    }
    const payload = {
      command,
      note: `${effectiveTaskWorkspace.name} operator CLI`,
      require_approval: cliScope === "system",
      task_id: effectiveTaskWorkspace.task_id,
      task_name: effectiveTaskWorkspace.name,
    };
    const response =
      cliScope === "system"
        ? await executeSystemCli.mutateAsync(payload)
        : await executeWorkspaceCli.mutateAsync(payload);
    setCliResponse(response);
  };

  const handleApplyBuilderAction = async (actionId: string) => {
    await applyBuilderAction.mutateAsync({ action_id: actionId });
    await refetchBuilderPreview();
  };

  const handleApplyAllBuilderActions = async () => {
    await applyBuilderActionBatch.mutateAsync({ use_apply_all_patch: true });
    await refetchBuilderPreview();
  };

  const handleInspectorViewChange = (view: InspectorView) => {
    setActiveInspectorView(view);
    const nextParams = new URLSearchParams(searchParams.toString());
    const nextTab = tabFromInspectorView(view);
    const currentTab = searchParams.get("tab");
    if ((currentTab ?? null) === nextTab) {
      return;
    }
    if (nextTab == null) {
      nextParams.delete("tab");
    } else {
      nextParams.set("tab", nextTab);
    }
    const nextQuery = nextParams.toString();
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false });
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border/70 bg-card px-3 py-2">
        <Badge variant={statusTone(effectiveWorkspaceStatus)}>
          <span data-testid="task-workspace-status">{effectiveWorkspaceStatus}</span>
        </Badge>
        <Button
          size="sm"
          variant="outline"
          data-testid="task-action-compile"
          onClick={() => compileTask.mutate()}
          disabled={compileTask.isPending}
        >
          <BrainCircuitIcon className="size-4" />
          Compile
        </Button>
        {effectiveWorkspaceStatus === "running" ? (
          <Button
            size="sm"
            variant="destructive"
            data-testid="task-action-pause"
            onClick={() => pauseTask.mutate()}
            disabled={pauseTask.isPending}
          >
            <CirclePauseIcon className="size-4" />
            Pause
          </Button>
        ) : effectiveWorkspaceStatus === "paused" || effectiveWorkspaceStatus === "waiting_review" ? (
          <Button
            size="sm"
            variant="secondary"
            data-testid="task-action-resume"
            onClick={() => resumeTask.mutate()}
            disabled={resumeTask.isPending}
          >
            <RotateCcwIcon className="size-4" />
            Resume
          </Button>
        ) : (
          <Button
            size="sm"
            data-testid="task-action-run"
            onClick={() =>
              runTask.mutate({
                auto_compile: true,
                auto_iterate: effectiveTaskWorkspace.mode !== "single",
                max_iterations: effectiveTaskWorkspace.mode === "single" ? 1 : 3,
              })
            }
            disabled={runTask.isPending}
          >
            <PlayIcon className="size-4" />
            Run
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          data-testid="task-action-terminate"
          onClick={() => terminateTask.mutate()}
        >
          <SquareIcon className="size-4" />
          Terminate
        </Button>
      </div>

      <aside className="min-h-[720px] flex-1" data-testid="workflow-runtime-sidebar">
        <TaskWorkspaceUnifiedCard
          activeView={activeInspectorView}
          agents={agents}
          allowPrefixes={allowPrefixes}
          artifacts={artifacts}
          brainLoading={brainLoading}
          brainPlan={brainPlan}
          builderAppliedActionIds={builderAppliedActionIds}
          builderCurrentDraft={builderCurrentDraft}
          builderHistoryEntries={builderHistoryEntries}
          builderMutationPending={builderMutationPending}
          builderPreview={builderPreview}
          builderRevision={builderRevision}
          capability={capability}
          cliCommand={cliCommand}
          cliPending={cliPending}
          cliResponse={cliResponse}
          cliScope={cliScope}
          copy={copy.taskWorkspace}
          defaultPermissionMode={defaultPermissionMode}
          onApplyAllBuilderActions={() => {
            void handleApplyAllBuilderActions();
          }}
          onApplyBuilderAction={(actionId) => {
            void handleApplyBuilderAction(actionId);
          }}
          onCliCommandChange={setCliCommand}
          onCliScopeChange={setCliScope}
          onRunCli={() => {
            void runServerCli();
          }}
          onSelectAgent={setSelectedAgentId}
          onViewChange={handleInspectorViewChange}
          policy={policy}
          runtime={runtime ?? null}
          selectedAgent={selectedAgent}
          selectedAgentId={selectedAgentId}
          selectedCard={selectedCard}
          studioRuntime={studioRuntime ?? null}
          systemCliAllowed={systemCliAllowed}
          taskId={effectiveTaskWorkspace.task_id}
          taskWorkspace={effectiveTaskWorkspace}
        />
      </aside>
    </div>
  );
}
