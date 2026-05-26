"use client";

import {
  ArrowRightIcon,
  BrainCircuitIcon,
  CirclePauseIcon,
  GitBranchPlusIcon,
  PlayIcon,
  RotateCcwIcon,
  SquareIcon,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { getAPIClient } from "@/core/api";
import { useI18n } from "@/core/i18n/hooks";
import { getWorkspaceLocaleCopy } from "@/core/i18n/workspace-copy";
import {
  useCompileTaskWorkspace,
  useCreateTaskWorkspace,
  useRunTaskWorkspace,
  useTaskWorkspace,
  useTaskWorkspaceAction,
  useTaskWorkspaces,
  useUpdateTaskCardGraph,
  type AgentHandleStatus,
  type TaskExecutionMode,
  type TaskWorkspace,
  type TaskWorkspaceStatus,
  type TaskWorkspaceSummary,
} from "@/core/task-workspaces";
import type { AgentThreadState } from "@/core/threads";
import { createWorkflowEvent, useWorkflows } from "@/core/workflows";
import { cn } from "@/lib/utils";

import { TaskCardGraphCanvas } from "../task-card-graph";

type TaskWorkspaceRuntimeProps = {
  focus: "plan" | "graph";
  threadId: string;
  threadState: AgentThreadState;
};

function statusTone(status: TaskWorkspaceStatus | AgentHandleStatus) {
  if (status === "running" || status === "completed") {
    return "default" as const;
  }
  if (status === "paused" || status === "waiting_review") {
    return "secondary" as const;
  }
  if (status === "failed" || status === "terminated") {
    return "destructive" as const;
  }
  return "outline" as const;
}

function localizedModeLabel(locale: string, mode: TaskExecutionMode) {
  if (locale === "zh-CN") {
    return mode === "single" ? "单任务" : mode === "branch" ? "分支协作" : "群组协作";
  }
  if (locale === "zh-TW") {
    return mode === "single" ? "單任務" : mode === "branch" ? "分支協作" : "群組協作";
  }
  if (locale === "ja") {
    return mode === "single" ? "単独実行" : mode === "branch" ? "分岐協調" : "グループ協調";
  }
  if (locale === "ko") {
    return mode === "single" ? "단일 실행" : mode === "branch" ? "브랜치 협업" : "그룹 협업";
  }
  return mode === "single" ? "Single" : mode === "branch" ? "Branch" : "Group";
}

function localizedStatusLabel(locale: string, status: TaskWorkspaceStatus | AgentHandleStatus) {
  if (locale === "zh-CN") {
    return {
      created: "已创建",
      planned: "已规划",
      running: "运行中",
      paused: "已暂停",
      waiting_review: "等待审查",
      completed: "已完成",
      failed: "已失败",
      terminated: "已终止",
      configured: "已配置",
      waiting_handoff: "等待交接",
      blocked: "已阻塞",
    }[status] ?? status;
  }
  if (locale === "zh-TW") {
    return {
      created: "已建立",
      planned: "已規劃",
      running: "執行中",
      paused: "已暫停",
      waiting_review: "等待審查",
      completed: "已完成",
      failed: "已失敗",
      terminated: "已終止",
      configured: "已配置",
      waiting_handoff: "等待交接",
      blocked: "已阻塞",
    }[status] ?? status;
  }
  if (locale === "ja") {
    return {
      created: "作成済み",
      planned: "計画済み",
      running: "実行中",
      paused: "一時停止中",
      waiting_review: "レビュー待ち",
      completed: "完了",
      failed: "失敗",
      terminated: "終了",
      configured: "設定済み",
      waiting_handoff: "引き継ぎ待ち",
      blocked: "ブロック中",
    }[status] ?? status;
  }
  if (locale === "ko") {
    return {
      created: "생성됨",
      planned: "계획됨",
      running: "실행 중",
      paused: "일시 중지됨",
      waiting_review: "검토 대기",
      completed: "완료됨",
      failed: "실패함",
      terminated: "종료됨",
      configured: "구성됨",
      waiting_handoff: "인계 대기",
      blocked: "차단됨",
    }[status] ?? status;
  }
  return status;
}

function taskProgressLabel(locale: string, task: TaskWorkspace | TaskWorkspaceSummary) {
  if (task.progress.total_cards === 0) {
    if (locale === "zh-CN") return "暂无卡片";
    if (locale === "zh-TW") return "暫無卡片";
    if (locale === "ja") return "カードなし";
    if (locale === "ko") return "카드 없음";
    return "No cards";
  }
  if (locale === "zh-CN") {
    return `已完成 ${task.progress.completed_cards}/${task.progress.total_cards} 张卡片`;
  }
  if (locale === "zh-TW") {
    return `已完成 ${task.progress.completed_cards}/${task.progress.total_cards} 張卡片`;
  }
  if (locale === "ja") {
    return `${task.progress.completed_cards}/${task.progress.total_cards} 枚のカード完了`;
  }
  if (locale === "ko") {
    return `카드 ${task.progress.completed_cards}/${task.progress.total_cards} 완료`;
  }
  return `${task.progress.completed_cards}/${task.progress.total_cards} cards`;
}

function actionLabel(locale: string, action: "compile" | "run" | "pause" | "resume" | "terminate") {
  const table = {
    "zh-CN": {
      compile: "编译",
      run: "运行",
      pause: "暂停",
      resume: "继续",
      terminate: "终止",
    },
    "zh-TW": {
      compile: "編譯",
      run: "執行",
      pause: "暫停",
      resume: "繼續",
      terminate: "終止",
    },
    ja: {
      compile: "コンパイル",
      run: "実行",
      pause: "一時停止",
      resume: "再開",
      terminate: "終了",
    },
    ko: {
      compile: "컴파일",
      run: "실행",
      pause: "일시 중지",
      resume: "재개",
      terminate: "종료",
    },
  } as const;
  return table[locale as keyof typeof table]?.[action] ?? {
    compile: "Compile",
    run: "Run",
    pause: "Pause",
    resume: "Resume",
    terminate: "Terminate",
  }[action];
}

function optimisticWorkspaceStatus(
  status: TaskWorkspaceStatus | null | undefined,
  options: {
    runPending: boolean;
    pausePending: boolean;
    resumePending: boolean;
    terminatePending: boolean;
  },
): TaskWorkspaceStatus {
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

function extractMessageText(content: unknown): string {
  if (typeof content === "string") {
    return content.trim();
  }
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") {
          return part;
        }
        if (
          part
          && typeof part === "object"
          && "text" in part
          && typeof (part as { text?: unknown }).text === "string"
        ) {
          return (part as { text: string }).text;
        }
        return "";
      })
      .join("\n")
      .trim();
  }
  return "";
}

function extractMessageRole(message: unknown): string {
  if (!(message && typeof message === "object")) {
    return "";
  }
  const candidate = message as { type?: unknown; role?: unknown };
  if (typeof candidate.type === "string") {
    return candidate.type;
  }
  if (typeof candidate.role === "string") {
    return candidate.role;
  }
  return "";
}

function textOrFallback(value: string | null | undefined, fallback: string): string {
  return value?.trim() ? value : fallback;
}

function deriveSeedGoal(threadState: AgentThreadState): string {
  for (const message of [...(threadState.messages ?? [])].reverse()) {
    const role = extractMessageRole(message);
    if (role !== "human" && role !== "user") {
      continue;
    }
    const content = extractMessageText(
      message && typeof message === "object"
        ? (message as { content?: unknown }).content
        : null,
    );
    if (content) {
      return content;
    }
  }
  const title = threadState.title?.trim();
  return title && title.length > 0 ? title : "";
}

function deriveSeedName(threadState: AgentThreadState): string {
  const title = threadState.title?.trim();
  if (title) {
    return title.slice(0, 72);
  }
  return "Workflow from chat";
}

function orderWorkspaces(
  workspaces: TaskWorkspaceSummary[],
  linkedTaskIds: string[],
) {
  if (linkedTaskIds.length === 0) {
    return workspaces;
  }
  const linkedSet = new Set(linkedTaskIds);
  const linked = workspaces.filter((workspace) => linkedSet.has(workspace.task_id));
  const rest = workspaces.filter((workspace) => !linkedSet.has(workspace.task_id));
  return [...linked, ...rest];
}

export function TaskWorkspaceRuntime({
  focus,
  threadId,
  threadState,
}: TaskWorkspaceRuntimeProps) {
  const { locale } = useI18n();
  const copy = getWorkspaceLocaleCopy(locale);
  const runtimeCopy = copy.taskRuntime;
  const {
    workflowCompiledDetail,
    workflowCompiledTitle,
    workflowGraphUpdatedDetail,
    workflowGraphUpdatedTitle,
    workflowPausedDetail,
    workflowPausedTitle,
    workflowResumedDetail,
    workflowResumedTitle,
    workflowStartedDetail,
    workflowStartedTitle,
    workflowTerminatedDetail,
    workflowTerminatedTitle,
  } = runtimeCopy;
  const { appendEvent } = useWorkflows();
  const { workspaces, isLoading: workspacesLoading, refetch: refetchWorkspaces } =
    useTaskWorkspaces();
  const linkedTaskIds = useMemo(
    () =>
      Array.isArray(threadState.task_workspace_ids)
        ? threadState.task_workspace_ids.filter(
            (taskId): taskId is string =>
              typeof taskId === "string" && taskId.trim().length > 0,
          )
        : [],
    [threadState.task_workspace_ids],
  );
  const orderedWorkspaces = useMemo(
    () => {
      const relevantTaskIds = new Set(linkedTaskIds);
      if (typeof threadState.active_task_workspace_id === "string") {
        relevantTaskIds.add(threadState.active_task_workspace_id);
      }
      if (relevantTaskIds.size === 0) {
        return [];
      }
      const scopedWorkspaces = workspaces.filter((workspace) =>
        relevantTaskIds.has(workspace.task_id),
      );
      return orderWorkspaces(scopedWorkspaces, linkedTaskIds);
    },
    [linkedTaskIds, threadState.active_task_workspace_id, workspaces],
  );
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(
    typeof threadState.active_task_workspace_id === "string"
      ? threadState.active_task_workspace_id
      : null,
  );
  const selectedSummary = orderedWorkspaces.find(
    (workspace) => workspace.task_id === selectedTaskId,
  ) ?? null;
  const {
    taskWorkspace,
    isLoading: taskLoading,
    refetch: refetchTaskWorkspace,
  } = useTaskWorkspace(selectedTaskId, {
    enabled: selectedTaskId != null,
  });
  const selectedWorkspace = taskWorkspace ?? null;
  const selectedMode = selectedWorkspace?.mode ?? selectedSummary?.mode ?? "single";
  const createTaskWorkspace = useCreateTaskWorkspace();
  const compileTaskWorkspace = useCompileTaskWorkspace(selectedTaskId ?? "");
  const runTaskWorkspace = useRunTaskWorkspace(selectedTaskId ?? "");
  const pauseTaskWorkspace = useTaskWorkspaceAction(selectedTaskId ?? "", "pause");
  const resumeTaskWorkspace = useTaskWorkspaceAction(selectedTaskId ?? "", "resume");
  const terminateTaskWorkspace = useTaskWorkspaceAction(selectedTaskId ?? "", "terminate");
  const updateTaskCardGraph = useUpdateTaskCardGraph(selectedTaskId ?? "");
  const effectiveWorkspaceStatus = optimisticWorkspaceStatus(
    selectedWorkspace?.status ?? selectedSummary?.status,
    {
      runPending: runTaskWorkspace.isPending,
      pausePending: pauseTaskWorkspace.isPending,
      resumePending: resumeTaskWorkspace.isPending,
      terminatePending: terminateTaskWorkspace.isPending,
    },
  );
  const seedGoal = useMemo(() => deriveSeedGoal(threadState), [threadState]);
  const seedName = useMemo(() => deriveSeedName(threadState), [threadState]);
  const [draftName, setDraftName] = useState(seedName);
  const [draftGoal, setDraftGoal] = useState(seedGoal);
  const [draftMode, setDraftMode] = useState<TaskExecutionMode>("single");

  useEffect(() => {
    if (!draftName.trim()) {
      setDraftName(seedName);
    }
  }, [draftName, seedName]);

  useEffect(() => {
    if (!draftGoal.trim()) {
      setDraftGoal(seedGoal);
    }
  }, [draftGoal, seedGoal]);

  useEffect(() => {
    if (selectedTaskId) {
      if (orderedWorkspaces.some((workspace) => workspace.task_id === selectedTaskId)) {
        return;
      }
      if (taskLoading || selectedWorkspace?.task_id === selectedTaskId) {
        return;
      }
    }
    const preferredTaskId =
      typeof threadState.active_task_workspace_id === "string"
        ? orderedWorkspaces.find(
            (workspace) => workspace.task_id === threadState.active_task_workspace_id,
          )?.task_id
        : null;
    setSelectedTaskId(preferredTaskId ?? orderedWorkspaces[0]?.task_id ?? null);
  }, [
    orderedWorkspaces,
    selectedTaskId,
    selectedWorkspace,
    taskLoading,
    threadState.active_task_workspace_id,
  ]);

  useEffect(() => {
    if (!selectedTaskId) {
      return;
    }
    const status = selectedWorkspace?.status ?? selectedSummary?.status;
    if (!status || !["running", "planned", "waiting_review"].includes(status)) {
      return;
    }
    const timer = window.setInterval(() => {
      void refetchWorkspaces();
      void refetchTaskWorkspace();
    }, 4000);
    return () => window.clearInterval(timer);
  }, [refetchTaskWorkspace, refetchWorkspaces, selectedSummary, selectedTaskId, selectedWorkspace]);

  const persistTaskSelection = useCallback(
    async (taskId: string) => {
      if (!threadId || threadId === "new") {
        return;
      }
      const nextTaskIds = Array.from(new Set([...linkedTaskIds, taskId]));
      await getAPIClient().threads.updateState(threadId, {
        values: {
          active_task_workspace_id: taskId,
          task_workspace_ids: nextTaskIds,
        },
      });
    },
    [linkedTaskIds, threadId],
  );

  const handleSelectTask = useCallback(
    (taskId: string) => {
      setSelectedTaskId(taskId);
      void persistTaskSelection(taskId);
    },
    [persistTaskSelection],
  );

  const handleCreateTaskWorkspace = useCallback(async () => {
    try {
      const created = await createTaskWorkspace.mutateAsync({
        name: textOrFallback(draftName, seedName),
        goal: textOrFallback(draftGoal, seedGoal),
        mode: draftMode,
      });
      setSelectedTaskId(created.task_id);
      await persistTaskSelection(created.task_id);
      appendEvent(
        createWorkflowEvent(
          "workflow_saved",
          "Workflow created",
          `${created.name} is now backed by TaskWorkspace runtime.`,
          "success",
          created.task_id,
        ),
      );
      void refetchWorkspaces();
      void refetchTaskWorkspace();
    } catch {
      // Mutation cache handles user-facing errors.
    }
  }, [
    appendEvent,
    createTaskWorkspace,
    draftGoal,
    draftMode,
    draftName,
    persistTaskSelection,
    refetchTaskWorkspace,
    refetchWorkspaces,
    seedGoal,
    seedName,
  ]);

  const handleCompile = useCallback(async () => {
    if (!selectedTaskId) {
      return;
    }
    try {
      await compileTaskWorkspace.mutateAsync();
      appendEvent(
        createWorkflowEvent(
          "workflow_saved",
          workflowCompiledTitle,
          workflowCompiledDetail,
          "info",
          selectedTaskId,
        ),
      );
      void refetchTaskWorkspace();
      void refetchWorkspaces();
    } catch {
      // Mutation cache handles user-facing errors.
    }
  }, [
    appendEvent,
    compileTaskWorkspace,
    refetchTaskWorkspace,
    refetchWorkspaces,
    selectedTaskId,
    workflowCompiledDetail,
    workflowCompiledTitle,
  ]);

  const handleRun = useCallback(async () => {
    if (!selectedTaskId) {
      return;
    }
    try {
      await runTaskWorkspace.mutateAsync({
        auto_compile: true,
        auto_iterate: selectedMode !== "single",
        max_iterations: selectedMode === "single" ? 1 : 3,
      });
      appendEvent(
        createWorkflowEvent(
          "task_started",
          workflowStartedTitle,
          workflowStartedDetail,
          "info",
          selectedTaskId,
        ),
      );
      void refetchTaskWorkspace();
      void refetchWorkspaces();
    } catch {
      // Mutation cache handles user-facing errors.
    }
  }, [
    appendEvent,
    refetchTaskWorkspace,
    refetchWorkspaces,
    runTaskWorkspace,
    selectedMode,
    selectedTaskId,
    workflowStartedDetail,
    workflowStartedTitle,
  ]);

  const handlePause = useCallback(async () => {
    if (!selectedTaskId) {
      return;
    }
    try {
      await pauseTaskWorkspace.mutateAsync();
      appendEvent(
        createWorkflowEvent(
          "workflow_continued",
          workflowPausedTitle,
          workflowPausedDetail,
          "warning",
          selectedTaskId,
        ),
      );
      void refetchTaskWorkspace();
      void refetchWorkspaces();
    } catch {
      // Mutation cache handles user-facing errors.
    }
  }, [
    appendEvent,
    pauseTaskWorkspace,
    refetchTaskWorkspace,
    refetchWorkspaces,
    selectedTaskId,
    workflowPausedDetail,
    workflowPausedTitle,
  ]);

  const handleResume = useCallback(async () => {
    if (!selectedTaskId) {
      return;
    }
    try {
      await resumeTaskWorkspace.mutateAsync();
      appendEvent(
        createWorkflowEvent(
          "workflow_resumed",
          workflowResumedTitle,
          workflowResumedDetail,
          "info",
          selectedTaskId,
        ),
      );
      void refetchTaskWorkspace();
      void refetchWorkspaces();
    } catch {
      // Mutation cache handles user-facing errors.
    }
  }, [
    appendEvent,
    refetchTaskWorkspace,
    refetchWorkspaces,
    resumeTaskWorkspace,
    selectedTaskId,
    workflowResumedDetail,
    workflowResumedTitle,
  ]);

  const handleTerminate = useCallback(async () => {
    if (!selectedTaskId) {
      return;
    }
    try {
      await terminateTaskWorkspace.mutateAsync();
      appendEvent(
        createWorkflowEvent(
          "task_failed",
          workflowTerminatedTitle,
          workflowTerminatedDetail,
          "error",
          selectedTaskId,
        ),
      );
      void refetchTaskWorkspace();
      void refetchWorkspaces();
    } catch {
      // Mutation cache handles user-facing errors.
    }
  }, [
    appendEvent,
    refetchTaskWorkspace,
    refetchWorkspaces,
    selectedTaskId,
    terminateTaskWorkspace,
    workflowTerminatedDetail,
    workflowTerminatedTitle,
  ]);

  const handleGraphChange = useCallback(
    (graph: TaskWorkspace["card_graph"]) => {
      if (!selectedTaskId) {
        return;
      }
      updateTaskCardGraph.mutate({ card_graph: graph });
      appendEvent(
        createWorkflowEvent(
          "workflow_saved",
          workflowGraphUpdatedTitle,
          workflowGraphUpdatedDetail,
          "info",
          selectedTaskId,
        ),
      );
    },
    [
      appendEvent,
      selectedTaskId,
      updateTaskCardGraph,
      workflowGraphUpdatedDetail,
      workflowGraphUpdatedTitle,
    ],
  );

  const renderWorkspaceList = () => (
    <ScrollArea className="min-h-0 flex-1 rounded-xl border">
      <div className="space-y-3 p-3">
        {orderedWorkspaces.length === 0 ? (
          <Card className="gap-3 border-dashed py-4 shadow-none">
            <CardHeader className="px-4">
                <CardTitle className="text-sm">{runtimeCopy.noWorkflowRuntimeTitle}</CardTitle>
              <CardDescription>
                  {runtimeCopy.noWorkflowRuntimeDescription}
              </CardDescription>
            </CardHeader>
          </Card>
        ) : (
          orderedWorkspaces.map((workspace) => {
            const selected = workspace.task_id === selectedTaskId;
            const linked = linkedTaskIds.includes(workspace.task_id);
            return (
              <button
                className="w-full text-left"
                key={workspace.task_id}
                onClick={() => handleSelectTask(workspace.task_id)}
                type="button"
              >
                <Card
                  className={cn(
                    "gap-3 py-4 transition-colors shadow-none",
                    selected
                      ? "border-foreground/30 bg-accent/35"
                      : "hover:bg-accent/20",
                  )}
                >
                  <CardHeader className="px-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="space-y-1">
                        <CardTitle className="text-sm">{workspace.name}</CardTitle>
                        <CardDescription className="line-clamp-2">
                          {textOrFallback(workspace.goal, runtimeCopy.noGoalProvided)}
                        </CardDescription>
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        <Badge variant={statusTone(workspace.status)}>{localizedStatusLabel(locale, workspace.status)}</Badge>
                        {linked ? <Badge variant="secondary">{runtimeCopy.linkedBadge}</Badge> : null}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="flex items-center justify-between px-4 text-xs text-muted-foreground">
                    <span>{localizedModeLabel(locale, workspace.mode)}</span>
                    <span>{taskProgressLabel(locale, workspace)}</span>
                  </CardContent>
                </Card>
              </button>
            );
          })
        )}
      </div>
    </ScrollArea>
  );

  const renderWorkspaceDetail = () => {
    if (!selectedTaskId) {
      return null;
    }

    if (taskLoading || !selectedWorkspace) {
      return (
        <Card className="h-full justify-center shadow-none">
          <CardHeader>
            <CardTitle>{runtimeCopy.loadingRuntimeTitle}</CardTitle>
            <CardDescription>
              {runtimeCopy.loadingRuntimeDescription}
            </CardDescription>
          </CardHeader>
        </Card>
      );
    }

    const primaryAction =
      effectiveWorkspaceStatus === "running"
        ? {
            icon: <CirclePauseIcon className="size-4" />,
            label: actionLabel(locale, "pause"),
            onClick: handlePause,
            variant: "destructive" as const,
            disabled: pauseTaskWorkspace.isPending,
            testId: "task-action-pause",
          }
        : effectiveWorkspaceStatus === "paused" || effectiveWorkspaceStatus === "waiting_review"
          ? {
              icon: <RotateCcwIcon className="size-4" />,
              label: actionLabel(locale, "resume"),
              onClick: handleResume,
              variant: "secondary" as const,
              disabled: resumeTaskWorkspace.isPending,
              testId: "task-action-resume",
            }
          : {
              icon: <PlayIcon className="size-4" />,
              label: actionLabel(locale, "run"),
              onClick: handleRun,
              variant: "default" as const,
              disabled: runTaskWorkspace.isPending,
              testId: "task-action-run",
            };

    const actionButtons = (
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={handleCompile} disabled={compileTaskWorkspace.isPending} data-testid="task-action-compile">
          <BrainCircuitIcon className="size-4" />
          {actionLabel(locale, "compile")}
        </Button>
        <Button
          size="sm"
          variant={primaryAction.variant}
          onClick={primaryAction.onClick}
          disabled={primaryAction.disabled}
          data-testid={primaryAction.testId}
        >
          {primaryAction.icon}
          {primaryAction.label}
        </Button>
        <Button size="sm" variant="outline" onClick={handleTerminate} disabled={terminateTaskWorkspace.isPending} data-testid="task-action-terminate">
          <SquareIcon className="size-4" />
          {actionLabel(locale, "terminate")}
        </Button>
        <Button asChild size="sm" variant="ghost">
          <Link href={`/workspace/workflows/${selectedWorkspace.task_id}`}>
            <ArrowRightIcon className="size-4" />
            {runtimeCopy.openPage}
          </Link>
        </Button>
      </div>
    );

    if (focus === "graph") {
      return (
        <Card className="h-full shadow-none">
          <CardHeader className="gap-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle className="text-base">{selectedWorkspace.name}</CardTitle>
                <CardDescription>
                  {localizedModeLabel(locale, selectedWorkspace.mode)} · {localizedStatusLabel(locale, effectiveWorkspaceStatus)} · {taskProgressLabel(locale, selectedWorkspace)}
                </CardDescription>
              </div>
              <Badge variant={statusTone(effectiveWorkspaceStatus)}>{localizedStatusLabel(locale, effectiveWorkspaceStatus)}</Badge>
            </div>
            {actionButtons}
          </CardHeader>
          <CardContent className="min-h-0 flex-1">
            <TaskCardGraphCanvas
              agents={selectedWorkspace.agents}
              cardGraph={selectedWorkspace.card_graph}
              onGraphChange={handleGraphChange}
            />
          </CardContent>
        </Card>
      );
    }

    return (
      <Card className="h-full shadow-none">
        <CardHeader className="gap-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle className="text-base">{selectedWorkspace.name}</CardTitle>
              <CardDescription>
                {textOrFallback(selectedWorkspace.goal, runtimeCopy.noGoalProvided)}
              </CardDescription>
            </div>
          <Badge variant={statusTone(effectiveWorkspaceStatus)}>{localizedStatusLabel(locale, effectiveWorkspaceStatus)}</Badge>
          </div>
          {actionButtons}
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-lg border p-3">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">{runtimeCopy.modeLabel}</div>
              <div className="mt-1 text-sm font-medium">{localizedModeLabel(locale, selectedWorkspace.mode)}</div>
            </div>
            <div className="rounded-lg border p-3">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">{runtimeCopy.progressLabel}</div>
              <div className="mt-1 text-sm font-medium">{taskProgressLabel(locale, selectedWorkspace)}</div>
            </div>
            <div className="rounded-lg border p-3">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">{runtimeCopy.threadBindingLabel}</div>
              <div className="mt-1 text-sm font-medium">
                {linkedTaskIds.includes(selectedWorkspace.task_id)
                  ? runtimeCopy.linkedToThisChat
                  : runtimeCopy.visibleGlobally}
              </div>
            </div>
          </div>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,6.5fr)_minmax(260px,3.5fr)]">
            <TaskCardGraphCanvas
              agents={selectedWorkspace.agents}
              cardGraph={selectedWorkspace.card_graph}
              onGraphChange={handleGraphChange}
            />
            <div className="space-y-4">
              <Card className="shadow-none">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">{runtimeCopy.agentsTitle}</CardTitle>
                  <CardDescription>
                    {runtimeCopy.agentsDescription}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {selectedWorkspace.agents.length === 0 ? (
                    <p className="text-muted-foreground">{runtimeCopy.noAgentsRegistered}</p>
                  ) : (
                    selectedWorkspace.agents.map((agent) => (
                      <div className="rounded-md border px-3 py-2" key={agent.agent_id}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium">{agent.name}</span>
                          <Badge variant={statusTone(agent.status)}>{localizedStatusLabel(locale, agent.status)}</Badge>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {agent.task_scope?.trim() ? agent.task_scope : agent.role}
                        </p>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
              <Card className="shadow-none">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">{runtimeCopy.checkpointsTitle}</CardTitle>
                  <CardDescription>
                    {runtimeCopy.checkpointsDescription}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {selectedWorkspace.checkpoints.length === 0 ? (
                    <p className="text-muted-foreground">{runtimeCopy.noCheckpoints}</p>
                  ) : (
                    selectedWorkspace.checkpoints.slice(0, 4).map((checkpoint) => (
                      <div className="rounded-md border px-3 py-2" key={checkpoint.checkpoint_id}>
                        <div className="font-medium">{checkpoint.label}</div>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {localizedStatusLabel(locale, checkpoint.task_status)} · {checkpoint.created_at}
                        </p>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  };

  const hasSelectedWorkspace = selectedTaskId != null;

  return (
    <div
      className={cn(
        "grid h-full min-h-0 gap-4",
        hasSelectedWorkspace
          ? "xl:grid-cols-[minmax(260px,3.5fr)_minmax(0,6.5fr)]"
          : "xl:grid-cols-1",
      )}
    >
      <div className="flex min-h-0 flex-col gap-4">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle className="text-sm">{runtimeCopy.realWorkflowRuntimeTitle}</CardTitle>
            <CardDescription>
              {runtimeCopy.realWorkflowRuntimeDescription}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <label htmlFor="task-workspace-name" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {runtimeCopy.workflowNameLabel}
              </label>
              <Input aria-label={runtimeCopy.workflowNameLabel} id="task-workspace-name" value={draftName} onChange={(event) => setDraftName(event.target.value)} />
            </div>
            <div className="space-y-2">
              <label htmlFor="task-workspace-goal" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {runtimeCopy.goalLabel}
              </label>
              <Textarea
                aria-label={runtimeCopy.goalLabel}
                id="task-workspace-goal"
                className="min-h-[104px]"
                value={draftGoal}
                onChange={(event) => setDraftGoal(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label id="task-workspace-mode-label" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {runtimeCopy.modeSelectLabel}
              </label>
              <Select value={draftMode} onValueChange={(value) => setDraftMode(value as TaskExecutionMode)}>
                <SelectTrigger aria-labelledby="task-workspace-mode-label" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="single">{localizedModeLabel(locale, "single")}</SelectItem>
                  <SelectItem value="branch">{localizedModeLabel(locale, "branch")}</SelectItem>
                  <SelectItem value="group">{localizedModeLabel(locale, "group")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button className="w-full" onClick={handleCreateTaskWorkspace} disabled={createTaskWorkspace.isPending}>
              <GitBranchPlusIcon className="size-4" />
              {runtimeCopy.createFromChatContext}
            </Button>
            <p className="text-xs text-muted-foreground">
              {linkedTaskIds.length > 0
                ? runtimeCopy.linkedWorkflowsCount(linkedTaskIds.length)
                : runtimeCopy.noLinkedWorkflows}
            </p>
          </CardContent>
        </Card>
        {workspacesLoading ? (
          <Card className="flex min-h-[240px] items-center justify-center shadow-none">
            <CardContent className="text-sm text-muted-foreground">
              {locale === "zh-CN" ? "正在加载工作流运行时…" : locale === "zh-TW" ? "正在載入工作流執行時…" : locale === "ja" ? "ワークフロー実行時を読み込み中…" : locale === "ko" ? "워크플로 런타임을 불러오는 중…" : "Loading workflow runtimes…"}
            </CardContent>
          </Card>
        ) : (
          renderWorkspaceList()
        )}
      </div>
      {hasSelectedWorkspace ? <div className="min-h-0">{renderWorkspaceDetail()}</div> : null}
    </div>
  );
}
