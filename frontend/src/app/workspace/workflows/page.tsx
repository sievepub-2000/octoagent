"use client";

import {
  CheckCircle2Icon,
  CircleDotIcon,
  GitBranchIcon,
  GitMergeIcon,
  LinkIcon,
  Loader2Icon,
  MessageSquareIcon,
  NetworkIcon,
  OctagonXIcon,
  PauseIcon,
  PlayIcon,
  PlusIcon,
  SettingsIcon,
  SquareIcon,
  TimerIcon,
  Trash2Icon,
  UserIcon,
  UsersIcon,
  XCircleIcon,
  ZapIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAgents } from "@/core/agents";
import { postJSON } from "@/core/api/http";
import { useI18n } from "@/core/i18n/hooks";
import {
  useCreateTaskWorkspace,
  useDeleteTaskWorkspace,
  useTaskWorkspace,
  useTaskWorkspaces,
  useUpdateTaskWorkspace,
} from "@/core/task-workspaces/hooks";
import {
  formatTaskRuntimeProvider,
  TASK_RUNTIME_PROVIDER_OPTIONS,
} from "@/core/task-workspaces/runtime-provider";
import type {
  TaskAgentRuntimeProvider,
  TaskExecutionMode,
  TaskWorkspaceSummary,
  TaskWorkspaceStatus,
} from "@/core/task-workspaces/types";
import { cn } from "@/lib/utils";

function shouldIgnoreCardClick(target: EventTarget | null): boolean {
  return target instanceof HTMLElement
    && target.closest("[data-card-interactive='true']") !== null;
}

// ── Extended types for workflow topology + run mode ─────────────────────────
type WorkflowRunMode = "chat" | "cron" | "yolo";
type WorkflowTopology = "chain" | "branch" | "swarm";

// stored in task workspace metadata
interface WorkflowMeta {
  topology?: WorkflowTopology;
  runMode?: WorkflowRunMode;
  primaryAgent?: string;
  subAgents?: string[];
  scheduledAt?: string;
}

// Wizard steps
type WizardStep = "task" | "agent" | "topology" | "execution";

type WorkflowScheduleParts = {
  year: string;
  month: string;
  day: string;
  hour: string;
  minute: string;
  second: string;
};

const EMPTY_SCHEDULE_PARTS: WorkflowScheduleParts = {
  year: "",
  month: "",
  day: "",
  hour: "",
  minute: "",
  second: "",
};

const SCHEDULE_FIELDS: Array<{
  key: keyof WorkflowScheduleParts;
  min: number;
  max: number;
  placeholder: string;
}> = [
  { key: "year", min: 1970, max: 9999, placeholder: "YYYY" },
  { key: "month", min: 1, max: 12, placeholder: "MM" },
  { key: "day", min: 1, max: 31, placeholder: "DD" },
  { key: "hour", min: 0, max: 23, placeholder: "hh" },
  { key: "minute", min: 0, max: 59, placeholder: "mm" },
  { key: "second", min: 0, max: 59, placeholder: "ss" },
];

function parseWorkflowMeta(summary?: string): WorkflowMeta {
  if (!summary?.trim()) {
    return {};
  }
  try {
    const parsed = JSON.parse(summary) as WorkflowMeta;
    if (!parsed || typeof parsed !== "object") {
      return {};
    }
    return parsed;
  } catch {
    return {};
  }
}

function schedulePartsFromIso(iso?: string | null): WorkflowScheduleParts {
  if (!iso) {
    return { ...EMPTY_SCHEDULE_PARTS };
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return { ...EMPTY_SCHEDULE_PARTS };
  }
  return {
    year: String(date.getUTCFullYear()),
    month: String(date.getUTCMonth() + 1).padStart(2, "0"),
    day: String(date.getUTCDate()).padStart(2, "0"),
    hour: String(date.getUTCHours()).padStart(2, "0"),
    minute: String(date.getUTCMinutes()).padStart(2, "0"),
    second: String(date.getUTCSeconds()).padStart(2, "0"),
  };
}

function toScheduleIso(parts: WorkflowScheduleParts): {
  valid: boolean;
  scheduledAt: string | null;
} {
  const values = Object.values(parts).map((value) => value.trim());
  const hasAny = values.some((value) => value.length > 0);
  if (!hasAny) {
    return { valid: true, scheduledAt: null };
  }
  if (values.some((value) => value.length === 0)) {
    return { valid: false, scheduledAt: null };
  }

  const asNumbers = {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hour: Number(parts.hour),
    minute: Number(parts.minute),
    second: Number(parts.second),
  };

  if (
    !Number.isInteger(asNumbers.year)
    || !Number.isInteger(asNumbers.month)
    || !Number.isInteger(asNumbers.day)
    || !Number.isInteger(asNumbers.hour)
    || !Number.isInteger(asNumbers.minute)
    || !Number.isInteger(asNumbers.second)
  ) {
    return { valid: false, scheduledAt: null };
  }

  for (const field of SCHEDULE_FIELDS) {
    const value = asNumbers[field.key];
    if (value < field.min || value > field.max) {
      return { valid: false, scheduledAt: null };
    }
  }

  const candidate = new Date(
    Date.UTC(
      asNumbers.year,
      asNumbers.month - 1,
      asNumbers.day,
      asNumbers.hour,
      asNumbers.minute,
      asNumbers.second,
    ),
  );
  if (Number.isNaN(candidate.getTime())) {
    return { valid: false, scheduledAt: null };
  }

  const matchesInput =
    candidate.getUTCFullYear() === asNumbers.year
    && candidate.getUTCMonth() + 1 === asNumbers.month
    && candidate.getUTCDate() === asNumbers.day
    && candidate.getUTCHours() === asNumbers.hour
    && candidate.getUTCMinutes() === asNumbers.minute
    && candidate.getUTCSeconds() === asNumbers.second;
  if (!matchesInput) {
    return { valid: false, scheduledAt: null };
  }

  return { valid: true, scheduledAt: candidate.toISOString() };
}

function formatScheduledAtLabel(iso?: string): string | null {
  if (!iso) {
    return null;
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  const h = String(date.getUTCHours()).padStart(2, "0");
  const mm = String(date.getUTCMinutes()).padStart(2, "0");
  const s = String(date.getUTCSeconds()).padStart(2, "0");
  return `${y}/${m}/${d} ${h}:${mm}:${s} UTC`;
}

// ── Status helpers ─────────────────────────────────────────────────────────

function statusBadge(
  status: TaskWorkspaceStatus,
  t: ReturnType<typeof useI18n>["t"],
) {
  const map: Record<
    TaskWorkspaceStatus,
    { label: string; className: string; icon: React.ReactNode }
  > = {
    created: {
      label: t.workflows.statusCreated,
      className: "bg-muted text-muted-foreground",
      icon: <CircleDotIcon className="size-3" />,
    },
    planned: {
      label: t.workflows.statusCreated,
      className: "bg-muted text-muted-foreground",
      icon: <CircleDotIcon className="size-3" />,
    },
    running: {
      label: t.workflows.statusRunning,
      className: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
      icon: <Loader2Icon className="size-3 animate-spin" />,
    },
    paused: {
      label: t.workflows.statusPaused,
      className: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
      icon: <PauseIcon className="size-3" />,
    },
    waiting_review: {
      label: t.workflows.statusPaused,
      className: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
      icon: <PauseIcon className="size-3" />,
    },
    completed: {
      label: t.workflows.statusCompleted,
      className: "bg-green-500/15 text-green-600 dark:text-green-400",
      icon: <CheckCircle2Icon className="size-3" />,
    },
    failed: {
      label: t.workflows.statusFailed,
      className: "bg-destructive/15 text-destructive",
      icon: <XCircleIcon className="size-3" />,
    },
    terminated: {
      label: t.workflows.statusTerminated,
      className: "bg-muted text-muted-foreground",
      icon: <OctagonXIcon className="size-3" />,
    },
  };
  const m = map[status] ?? map.created;
  return (
    <Badge variant="outline" className={cn("gap-1 text-[10px]", m.className)}>
      {m.icon}
      {m.label}
    </Badge>
  );
}

// ── Run mode helpers ───────────────────────────────────────────────────────

function topoIcon(topo: WorkflowTopology) {
  switch (topo) {
    case "chain":
      return <LinkIcon className="size-3.5" />;
    case "branch":
      return <GitBranchIcon className="size-3.5" />;
    case "swarm":
      return <NetworkIcon className="size-3.5" />;
  }
}

// ── Action helper ──────────────────────────────────────────────────────────

async function taskAction(
  taskId: string,
  action: "run" | "pause" | "resume" | "terminate",
  mode?: TaskExecutionMode,
) {
  if (action === "run") {
    await postJSON(`/api/task-workspaces/${taskId}/run`, {
      auto_compile: true,
      auto_iterate: mode != null && mode !== "single",
      max_iterations: mode === "single" ? 1 : 3,
    });
    return;
  }
  await postJSON(`/api/task-workspaces/${taskId}/${action}`, {});
}

// ── Page ───────────────────────────────────────────────────────────────────
export default function WorkflowsPage() {
  const { t } = useI18n();
  const router = useRouter();
  const { workspaces, isLoading, refetch } = useTaskWorkspaces();
  const createMutation = useCreateTaskWorkspace();
  const deleteMutation = useDeleteTaskWorkspace();

  const { agents: availableAgents } = useAgents();

  const [createOpen, setCreateOpen] = useState(false);
  const [editTaskId, setEditTaskId] = useState<string | null>(null);
  const { taskWorkspace: editableTaskWorkspace } = useTaskWorkspace(editTaskId, {
    enabled: editTaskId != null,
  });
  const updateTaskMutation = useUpdateTaskWorkspace(editTaskId ?? "");
  const [deletingAll, setDeletingAll] = useState(false);
  const [editName, setEditName] = useState("");
  const [editGoal, setEditGoal] = useState("");
  const [editTopology, setEditTopology] = useState<WorkflowTopology>("chain");
  const [editRunMode, setEditRunMode] = useState<WorkflowRunMode>("chat");
  const [editProvider, setEditProvider] = useState<TaskAgentRuntimeProvider>("langgraph");
  const [editPrimaryAgent, setEditPrimaryAgent] = useState<string>("");
  const [editSubAgents, setEditSubAgents] = useState<string[]>([]);
  const [editScheduleParts, setEditScheduleParts] =
    useState<WorkflowScheduleParts>(EMPTY_SCHEDULE_PARTS);
  const [pendingEditRunMode, setPendingEditRunMode] = useState<WorkflowRunMode | null>(null);

  // ── Wizard state ──
  const [wizardStep, setWizardStep] = useState<WizardStep>("task");
  const [taskName, setTaskName] = useState("");
  const [taskGoal, setTaskGoal] = useState("");
  const [agentMode, setAgentMode] = useState<"single" | "multi">("single");
  const [topology, setTopology] = useState<WorkflowTopology>("chain");
  const [runMode, setRunMode] = useState<WorkflowRunMode>("chat");
  const [runtimeProvider, setRuntimeProvider] = useState<TaskAgentRuntimeProvider>("langgraph");
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  const [primaryAgent, setPrimaryAgent] = useState<string>("");
  const [scheduleParts, setScheduleParts] =
    useState<WorkflowScheduleParts>(EMPTY_SCHEDULE_PARTS);

  const wizardSteps = useMemo<WizardStep[]>(() => ["task", "agent", "topology", "execution"], []);

  const wizardStepIndex = wizardSteps.indexOf(wizardStep);
  const isLastStep = wizardStepIndex === wizardSteps.length - 1;

  const resetWizard = () => {
    setWizardStep("task");
    setTaskName("");
    setTaskGoal("");
    setAgentMode("single");
    setTopology("chain");
    setRunMode("chat");
    setRuntimeProvider("langgraph");
    setSelectedAgents([]);
    setPrimaryAgent("");
    setScheduleParts({ ...EMPTY_SCHEDULE_PARTS });
  };

  const handleWizardNext = useCallback(() => {
    const idx = wizardSteps.indexOf(wizardStep);
    if (idx < wizardSteps.length - 1) {
      setWizardStep(wizardSteps[idx + 1]!);
    }
  }, [wizardStep, wizardSteps]);

  const handleWizardBack = useCallback(() => {
    const idx = wizardSteps.indexOf(wizardStep);
    if (idx > 0) {
      setWizardStep(wizardSteps[idx - 1]!);
    }
  }, [wizardStep, wizardSteps]);

  const handleCreate = useCallback(async () => {
    if (!taskName.trim()) return;
    const mode: TaskExecutionMode =
      agentMode === "single"
        ? "single"
        : topology === "branch"
          ? "branch"
          : "group";
    const scheduleResult = toScheduleIso(scheduleParts);
    if (runMode === "cron" && !scheduleResult.valid) {
      toast.error(t.workflows.scheduleInvalid);
      return;
    }
    const scheduledAt = runMode === "cron" ? scheduleResult.scheduledAt ?? undefined : undefined;

    try {
      const created = await createMutation.mutateAsync({
        name: taskName.trim(),
        goal: taskGoal.trim() || undefined,
        mode,
        agent_runtime_provider: runtimeProvider,
        summary: JSON.stringify({
          topology,
          runMode,
          primaryAgent: primaryAgent || undefined,
          subAgents: selectedAgents.length > 0 ? selectedAgents : undefined,
          scheduledAt,
        } satisfies WorkflowMeta),
      });

      if (runMode === "chat") {
        if (primaryAgent.trim()) {
          router.push(
            `/workspace/agents/${encodeURIComponent(primaryAgent.trim())}/chats/new?from_workflow=${encodeURIComponent(created.task_id)}`,
          );
        } else {
          router.push(`/workspace/chats/new?from_workflow=${encodeURIComponent(created.task_id)}`);
        }
      }

      toast.success(t.workflows.saveSuccess);
      setCreateOpen(false);
      resetWizard();
      void refetch();
    } catch {
      toast.error("Failed to create workflow");
    }
  }, [
    agentMode,
    createMutation,
    primaryAgent,
    router,
    refetch,
    runMode,
    scheduleParts,
    runtimeProvider,
    selectedAgents,
    t,
    taskGoal,
    taskName,
    topology,
  ]);

  // Auto-refresh running tasks
  useEffect(() => {
    const hasRunning = workspaces.some((w) => w.status === "running");
    if (!hasRunning) return;
    const timer = setInterval(() => {
      void refetch();
    }, 5000);
    return () => clearInterval(timer);
  }, [workspaces, refetch]);

  const handleAction = useCallback(
    async (
      taskId: string,
      action: "run" | "pause" | "resume" | "terminate",
      mode?: TaskExecutionMode,
    ) => {
      try {
        await taskAction(taskId, action, mode);
        void refetch();
      } catch {
        toast.error(`Failed to ${action}`);
      }
    },
    [refetch],
  );

  // Parse metadata for display
  const topoLabel = (topo: WorkflowTopology) => {
    switch (topo) {
      case "chain":
        return t.workflows.chain;
      case "branch":
        return t.workflows.branch;
      case "swarm":
        return t.workflows.swarm;
    }
  };

  const runModeLabel = (mode: WorkflowRunMode) => {
    switch (mode) {
      case "chat":
        return t.workflows.modeChat;
      case "cron":
        return t.workflows.modeCron;
      case "yolo":
        return t.workflows.modeYolo;
    }
  };

  // Derive mode/topology from task workspace fields
  const getDisplayInfo = (ws: TaskWorkspaceSummary) => {
    const parsed = parseWorkflowMeta(ws.summary);
    const topo: WorkflowTopology =
      parsed.topology
      ?? (ws.mode === "single" ? "chain" : ws.mode === "branch" ? "branch" : "swarm");
    const runModeValue = parsed.runMode;
    const runMode: WorkflowRunMode =
      runModeValue === "chat" || runModeValue === "cron" || runModeValue === "yolo"
        ? runModeValue
        : "chat";
    return {
      topology: topo,
      runMode,
      scheduledAt: parsed.scheduledAt,
      primaryAgent: parsed.primaryAgent,
    };
  };

  const openWorkflowSettings = useCallback(
    (taskId: string, preferredRunMode?: WorkflowRunMode) => {
      setPendingEditRunMode(preferredRunMode ?? null);
      setEditTaskId(taskId);
    },
    [],
  );

  useEffect(() => {
    if (!editableTaskWorkspace) {
      return;
    }
    setEditName(editableTaskWorkspace.name ?? "");
    setEditGoal(editableTaskWorkspace.goal ?? "");
    const parsed = (() => {
      try {
        return editableTaskWorkspace.summary
          ? (JSON.parse(editableTaskWorkspace.summary) as WorkflowMeta)
          : {};
      } catch {
        return {} as WorkflowMeta;
      }
    })();
    setEditTopology(
      parsed.topology ??
        (editableTaskWorkspace.mode === "single"
          ? "chain"
          : editableTaskWorkspace.mode === "branch"
            ? "branch"
            : "swarm"),
    );
    const resolvedRunMode: WorkflowRunMode =
      pendingEditRunMode ?? parsed.runMode ?? "chat";
    setEditRunMode(resolvedRunMode);
    setEditPrimaryAgent(parsed.primaryAgent ?? "");
    setEditSubAgents(parsed.subAgents ?? []);
    setEditScheduleParts(schedulePartsFromIso(parsed.scheduledAt));
    setEditProvider(editableTaskWorkspace.agent_runtime_provider ?? "langgraph");
    setPendingEditRunMode(null);
  }, [editableTaskWorkspace, pendingEditRunMode]);

  // Auto-set primary agent to first available agent when empty and agents loaded
  useEffect(() => {
    if (editTaskId && editPrimaryAgent === "" && availableAgents.length > 0) {
      setEditPrimaryAgent(availableAgents[0]!.name);
    }
  }, [editTaskId, editPrimaryAgent, availableAgents]);

  // Also set create wizard primary agent default
  useEffect(() => {
    if (createOpen && primaryAgent === "" && availableAgents.length > 0) {
      setPrimaryAgent(availableAgents[0]!.name);
    }
  }, [createOpen, primaryAgent, availableAgents]);

  const handleDeleteWorkflow = useCallback(
    async (taskId: string) => {
      try {
        await deleteMutation.mutateAsync(taskId);
        toast.success(t.common.deleteAllSuccess);
      } catch {
        toast.error("Failed to delete workflow");
      }
    },
    [deleteMutation, t.common.deleteAllSuccess],
  );

  const handleDeleteAll = useCallback(async () => {
    if (!workspaces.length) return;
    if (!window.confirm(t.common.deleteAllConfirm)) return;
    setDeletingAll(true);
    try {
      for (const workspace of workspaces) {
        await deleteMutation.mutateAsync(workspace.task_id);
      }
      toast.success(t.common.deleteAllSuccess);
    } catch {
      toast.error("Failed to delete some workflows");
    } finally {
      setDeletingAll(false);
    }
  }, [deleteMutation, t.common.deleteAllConfirm, t.common.deleteAllSuccess, workspaces]);

  const handleSaveWorkflow = useCallback(async () => {
    if (!editTaskId || !editName.trim()) {
      return;
    }
    const editScheduleResult = toScheduleIso(editScheduleParts);
    if (editRunMode === "cron" && !editScheduleResult.valid) {
      toast.error(t.workflows.scheduleInvalid);
      return;
    }
    const editScheduledAt = editRunMode === "cron" ? editScheduleResult.scheduledAt ?? undefined : undefined;
    try {
      await updateTaskMutation.mutateAsync({
        name: editName.trim(),
        goal: editGoal.trim(),
        agent_runtime_provider: editProvider,
        summary: JSON.stringify({
          topology: editTopology,
          runMode: editRunMode,
          primaryAgent: editPrimaryAgent || undefined,
          subAgents: editSubAgents.length > 0 ? editSubAgents : undefined,
          scheduledAt: editScheduledAt,
        } satisfies WorkflowMeta),
        top_bar_label: editName.trim(),
      });
      toast.success(t.common.save);
      setEditTaskId(null);
      void refetch();
    } catch {
      toast.error("Failed to update workflow");
    }
  }, [editGoal, editName, editPrimaryAgent, editProvider, editRunMode, editScheduleParts, editSubAgents, editTaskId, editTopology, refetch, t.common.save, t.workflows.scheduleInvalid, updateTaskMutation]);

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold">{t.workflows.title}</h1>
          <p className="text-sm text-muted-foreground">
            {t.workflows.description}
          </p>
        </div>
        <div className="flex gap-2">
          {workspaces.length > 0 && (
            <Button
              size="sm"
              variant="destructive"
              disabled={deletingAll}
              onClick={() => void handleDeleteAll()}
            >
              <Trash2Icon className="mr-1 size-4" />
              {t.common.deleteAll}
            </Button>
          )}
          <Button
            size="sm"
            onClick={() => {
              resetWizard();
              setCreateOpen(true);
            }}
          >
            <PlusIcon className="mr-1 size-4" />
            {t.workflows.newWorkflow}
          </Button>
        </div>
      </div>

      {/* Workflow Cards */}
      <div className="flex-1 p-6">
        {isLoading ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2Icon className="size-5 animate-spin" />
          </div>
        ) : workspaces.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <GitMergeIcon className="mb-3 size-10 opacity-30" />
            <p className="font-medium">{t.workflows.emptyTitle}</p>
            <p className="mt-1 text-sm">{t.workflows.emptyDescription}</p>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => {
                resetWizard();
                setCreateOpen(true);
              }}
            >
              <PlusIcon className="mr-1 size-4" />
              {t.workflows.newWorkflow}
            </Button>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {workspaces.map((ws) => {
              const info = getDisplayInfo(ws);
              const canRun =
                ws.status === "created" || ws.status === "planned";
              const canPause = ws.status === "running";
              const canResume =
                ws.status === "paused" || ws.status === "waiting_review";
              const canStop =
                ws.status === "running" ||
                ws.status === "paused" ||
                ws.status === "waiting_review";

              const isRunning = ws.status === "running";

              return (
                <div
                  key={ws.task_id}
                  data-testid={`workflow-card-${ws.task_id}`}
                  className="group flex min-w-0 cursor-pointer flex-col overflow-hidden rounded-xl border border-primary/25 bg-card p-4 shadow-sm transition-shadow hover:shadow-md"
                  onClick={(event) => {
                    if (shouldIgnoreCardClick(event.target)) {
                      return;
                    }
                    router.push(`/workspace/workflows/${ws.task_id}`);
                  }}
                >
                  {/* Top row: name + status */}
                  <div className="mb-1.5 flex items-start justify-between gap-2">
                    <h3 className="min-w-0 break-words text-sm font-medium text-foreground">
                      {ws.name || "Untitled"}
                    </h3>
                    {statusBadge(ws.status, t)}
                  </div>

                  {/* Goal */}
                  <p className="mb-3 min-h-0 shrink break-words line-clamp-2 text-xs text-muted-foreground">
                    {ws.goal || t.workflows.noGoal}
                  </p>

                  {/* Progress bar */}
                  {ws.progress.total_cards > 0 && (
                    <div className="mb-3">
                      <div className="mb-1 flex justify-between text-[10px] text-muted-foreground">
                        <span>
                          {ws.progress.completed_cards}/{ws.progress.total_cards}
                        </span>
                        <span>
                          {ws.progress.active_agents} active
                        </span>
                      </div>
                      <progress
                        className="h-1 w-full overflow-hidden rounded-full [&::-webkit-progress-bar]:rounded-full [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:rounded-full [&::-webkit-progress-value]:bg-primary [&::-moz-progress-bar]:rounded-full [&::-moz-progress-bar]:bg-primary"
                        max={ws.progress.total_cards}
                        value={ws.progress.completed_cards}
                      />
                    </div>
                  )}

                  {/* Badges + Controls */}
                  <div className="mt-auto flex items-center justify-between gap-2">
                    <div
                      data-card-interactive="true"
                      className="flex min-w-0 flex-wrap gap-1"
                    >
                      <Badge
                        variant="outline"
                        className="border-primary/30 text-[10px] text-primary"
                      >
                        {info.topology === "chain" ? (
                          <UserIcon className="mr-0.5 size-3" />
                        ) : (
                          <UsersIcon className="mr-0.5 size-3" />
                        )}
                        {ws.mode === "single"
                          ? t.workflows.singleAgent
                          : t.workflows.multiAgent}
                      </Badge>
                      {ws.mode !== "single" && (
                        <Badge
                          variant="outline"
                          className="border-primary/30 text-[10px] text-primary"
                        >
                          {topoIcon(info.topology)}
                          <span className="ml-0.5">
                            {topoLabel(info.topology)}
                          </span>
                        </Badge>
                      )}
                      <Badge
                        variant="outline"
                        className="border-primary/30 text-[10px] text-primary"
                      >
                        {formatTaskRuntimeProvider(ws.agent_runtime_provider)}
                      </Badge>
                      {([
                        "chat",
                        "cron",
                        "yolo",
                      ] as const).map((modeItem) => {
                        const active = info.runMode === modeItem;
                        return (
                          <button
                            key={modeItem}
                            type="button"
                            className={cn(
                              "inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] transition-colors",
                              active
                                ? "border-primary bg-primary/10 text-primary"
                                : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground",
                            )}
                            onClick={(event) => {
                              event.stopPropagation();
                              openWorkflowSettings(ws.task_id, modeItem);
                            }}
                          >
                            {modeItem === "chat" ? (
                              <MessageSquareIcon className="mr-1 size-3" />
                            ) : modeItem === "cron" ? (
                              <TimerIcon className="mr-1 size-3" />
                            ) : (
                              <ZapIcon className="mr-1 size-3" />
                            )}
                            {runModeLabel(modeItem)}
                          </button>
                        );
                      })}
                      {info.runMode === "cron" && info.scheduledAt ? (
                        <Badge
                          variant="outline"
                          className="max-w-full break-all border-amber-500/30 bg-amber-500/5 text-[10px] text-amber-700 dark:text-amber-300"
                        >
                          {formatScheduledAtLabel(info.scheduledAt)}
                        </Badge>
                      ) : null}
                    </div>

                    {/* Action buttons */}
                    <div
                      data-card-interactive="true"
                      className="flex gap-1"
                    >
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7"
                        data-testid={`workflow-card-settings-${ws.task_id}`}
                        title={isRunning ? "Stop workflow to edit settings" : t.common.settings}
                        disabled={isRunning}
                        onClick={(e) => {
                          e.stopPropagation();
                          openWorkflowSettings(ws.task_id);
                        }}
                      >
                        <SettingsIcon className="size-3.5" />
                      </Button>
                      {canRun && (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-7 text-green-600"
                          data-testid={`workflow-card-run-${ws.task_id}`}
                          title={t.workflows.run}
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleAction(ws.task_id, "run", ws.mode);
                          }}
                        >
                          <PlayIcon className="size-3.5" />
                        </Button>
                      )}
                      {canPause && (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-7 text-amber-600"
                          data-testid={`workflow-card-pause-${ws.task_id}`}
                          title={t.workflows.pause}
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleAction(ws.task_id, "pause");
                          }}
                        >
                          <PauseIcon className="size-3.5" />
                        </Button>
                      )}
                      {canResume && (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-7 text-blue-600"
                          data-testid={`workflow-card-resume-${ws.task_id}`}
                          title={t.workflows.resume}
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleAction(ws.task_id, "resume");
                          }}
                        >
                          <PlayIcon className="size-3.5" />
                        </Button>
                      )}
                      {canStop && (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-7 text-destructive"
                          data-testid={`workflow-card-stop-${ws.task_id}`}
                          title={t.workflows.stop}
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleAction(ws.task_id, "terminate");
                          }}
                        >
                          <SquareIcon className="size-3.5" />
                        </Button>
                      )}
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7 text-destructive"
                        data-testid={`workflow-card-delete-${ws.task_id}`}
                        title={t.common.delete}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (window.confirm(t.common.deleteAllConfirm)) {
                            void handleDeleteWorkflow(ws.task_id);
                          }
                        }}
                      >
                        <Trash2Icon className="size-3.5" />
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Create Workflow Wizard Dialog ─────────────────────────────────── */}
      <Dialog
        open={createOpen}
        onOpenChange={(o) => {
          setCreateOpen(o);
          if (!o) resetWizard();
        }}
      >
        <DialogContent className="flex w-[min(96vw,52rem)] max-h-[calc(100vh-4rem)] flex-col overflow-hidden sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t.workflows.newWorkflow}</DialogTitle>
            <DialogDescription>{t.workflows.description}</DialogDescription>
          </DialogHeader>

          {/* Step indicator */}
          <div className="flex flex-wrap items-center justify-center gap-2 py-2">
            {wizardSteps.map((s, i) => {
              const labels: Record<WizardStep, string> = {
                task: t.workflows.wizardStepTask,
                agent: t.workflows.wizardStepAgent,
                topology: t.workflows.wizardStepTopology,
                execution: t.workflows.wizardStepExecution,
              };
              return (
                <div key={s} className="flex items-center gap-1.5">
                  <div
                    className={cn(
                      "flex size-6 items-center justify-center rounded-full text-[10px] font-bold transition-colors",
                      i <= wizardStepIndex
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground",
                    )}
                  >
                    {i + 1}
                  </div>
                  <span
                    className={cn(
                      "max-w-[8rem] truncate text-xs",
                      i <= wizardStepIndex
                        ? "font-medium text-foreground"
                        : "text-muted-foreground",
                    )}
                  >
                    {labels[s]}
                  </span>
                  {i < wizardSteps.length - 1 && (
                    <div
                      className={cn(
                        "h-px w-4",
                        i < wizardStepIndex ? "bg-primary" : "bg-muted",
                      )}
                    />
                  )}
                </div>
              );
            })}
          </div>

          {/* Step: Task Info */}
          {wizardStep === "task" && (
            <div className="min-h-0 overflow-y-auto py-2">
              <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">
                  {t.workflows.taskName}
                </span>
                <Input
                  value={taskName}
                  onChange={(e) => setTaskName(e.target.value)}
                  placeholder="my-workflow"
                  autoFocus
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">
                  {t.workflows.taskGoal}
                </span>
                <Textarea
                  value={taskGoal}
                  onChange={(e) => setTaskGoal(e.target.value)}
                  rows={3}
                  placeholder={t.workflows.taskGoal}
                />
              </div>
              </div>
            </div>
          )}

          {/* Step: Agent Mode + Agent Selection (merged) */}
          {wizardStep === "agent" && (
            <div className="min-h-0 overflow-y-auto py-2 pr-1">
              <div className="flex flex-col gap-4">
              {/* Mode selector */}
              <div className="grid gap-2 sm:grid-cols-2">
                <button
                  type="button"
                  className={cn(
                    "flex min-w-0 items-start gap-3 rounded-lg border p-3 text-left transition-colors",
                    agentMode === "single"
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/40",
                  )}
                  onClick={() => {
                    setAgentMode("single");
                    setTopology("chain");
                    setSelectedAgents([]);
                  }}
                >
                  <UserIcon className="mt-0.5 size-4 shrink-0 text-primary" />
                  <div className="min-w-0">
                    <div className="text-sm font-medium">
                      {t.workflows.singleAgent}
                    </div>
                    <div className="mt-1 break-words text-xs text-muted-foreground">
                      {t.workflows.singleAgentDesc}
                    </div>
                  </div>
                </button>
                <button
                  type="button"
                  className={cn(
                    "flex min-w-0 items-start gap-3 rounded-lg border p-3 text-left transition-colors",
                    agentMode === "multi"
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/40",
                  )}
                  onClick={() => setAgentMode("multi")}
                >
                  <UsersIcon className="mt-0.5 size-4 shrink-0 text-primary" />
                  <div className="min-w-0">
                    <div className="text-sm font-medium">
                      {t.workflows.multiAgent}
                    </div>
                    <div className="mt-1 break-words text-xs text-muted-foreground">
                      {t.workflows.multiAgentDesc}
                    </div>
                  </div>
                </button>
              </div>

              {/* Primary agent dropdown */}
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">
                  {agentMode === "single"
                    ? t.workflows.wizardStepAgent
                    : t.workflows.wizardPrimaryAgent}
                </span>
                <Select
                  value={primaryAgent || "__default__"}
                  onValueChange={(v) => setPrimaryAgent(v === "__default__" ? "" : v)}
                >
                  <SelectTrigger className="border-primary/30 bg-card text-foreground data-[placeholder]:text-muted-foreground focus-visible:ring-primary/30">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="max-w-[min(42rem,calc(100vw-2rem))] border-primary/20 bg-popover text-popover-foreground">
                    <SelectItem value="__default__">
                      {t.workflows.systemDefault}
                    </SelectItem>
                    {availableAgents.map((ag) => (
                      <SelectItem key={ag.name} value={ag.name} className="items-start py-2">
                        <div className="min-w-0 whitespace-normal">
                          <div className="break-words font-medium">{ag.name}</div>
                          {ag.description ? (
                            <div className="mt-0.5 break-words text-xs text-muted-foreground">
                              {ag.description}
                            </div>
                          ) : null}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Multi-agent: sub-agents */}
              {agentMode === "multi" && (
                <div className="flex flex-col gap-1.5">
                  <span className="text-sm font-medium">
                    {t.workflows.wizardSubAgents}
                  </span>
                  <div className="mt-1 grid max-h-64 gap-2 overflow-y-auto rounded-lg border border-border/60 bg-muted/10 p-2">
                    {availableAgents
                      .filter((ag) => ag.name !== primaryAgent)
                      .map((ag) => {
                        const isSelected = selectedAgents.includes(ag.name);
                        return (
                          <button
                            key={ag.name}
                            type="button"
                            className={cn(
                              "flex min-w-0 items-start gap-2 rounded-md border px-3 py-2 text-left text-sm transition-colors",
                              isSelected
                                ? "border-primary bg-primary/5"
                                : "border-border hover:border-primary/40",
                            )}
                            onClick={() => {
                              setSelectedAgents((prev) =>
                                isSelected
                                  ? prev.filter((n) => n !== ag.name)
                                  : [...prev, ag.name],
                              );
                            }}
                          >
                            <div className={cn(
                              "flex size-4 items-center justify-center rounded border",
                              isSelected ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/30"
                            )}>
                              {isSelected && <CheckCircle2Icon className="size-3" />}
                            </div>
                            <div className="min-w-0">
                              <div className="break-words font-medium text-foreground">{ag.name}</div>
                              {ag.description ? (
                                <div className="mt-0.5 break-words text-xs text-muted-foreground">
                                  {ag.description}
                                </div>
                              ) : null}
                            </div>
                          </button>
                        );
                      })}
                  </div>
                </div>
              )}
              </div>
            </div>
          )}



          {/* Step: Topology (multi-agent only) */}
          {wizardStep === "topology" && (
            <div className="min-h-0 overflow-y-auto py-2 pr-1">
              <div className="flex flex-col gap-3">
              {agentMode === "single" ? (
                <div className="rounded-lg border border-primary/30 bg-primary/5 p-4">
                  <div className="flex items-start gap-3">
                    <LinkIcon className="mt-0.5 size-5 shrink-0 text-primary" />
                    <div>
                      <div className="text-sm font-medium">{topoLabel("chain")}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {t.workflows.singleAgentDesc}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                (
                  [
                    {
                      key: "chain" as const,
                      icon: LinkIcon,
                      desc: t.workflows.chainDesc,
                    },
                    {
                      key: "branch" as const,
                      icon: GitBranchIcon,
                      desc: t.workflows.branchDesc,
                    },
                    {
                      key: "swarm" as const,
                      icon: NetworkIcon,
                      desc: t.workflows.swarmDesc,
                    },
                  ] as const
                ).map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    className={cn(
                      "flex items-start gap-3 rounded-lg border p-4 text-left transition-colors",
                      topology === item.key
                        ? "border-primary bg-primary/5"
                        : "border-border hover:border-primary/40",
                    )}
                    onClick={() => setTopology(item.key)}
                  >
                    <item.icon className="mt-0.5 size-5 text-primary" />
                    <div>
                      <div className="text-sm font-medium">
                        {topoLabel(item.key)}
                      </div>
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        {item.desc}
                      </div>
                    </div>
                  </button>
                ))
              )}
              </div>
            </div>
          )}

          {/* Step: Execution Mode */}
          {wizardStep === "execution" && (
            <div className="min-h-0 overflow-y-auto py-2 pr-1">
              <div className="flex flex-col gap-3">
              {(
                [
                  {
                    key: "chat" as const,
                    icon: MessageSquareIcon,
                    label: t.workflows.modeChat,
                    desc: t.workflows.modeChatDesc,
                  },
                  {
                    key: "cron" as const,
                    icon: TimerIcon,
                    label: t.workflows.modeCron,
                    desc: t.workflows.modeCronDesc,
                  },
                  {
                    key: "yolo" as const,
                    icon: ZapIcon,
                    label: t.workflows.modeYolo,
                    desc: t.workflows.modeYoloDesc,
                  },
                ] as const
              ).map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={cn(
                    "flex items-start gap-3 rounded-lg border p-4 text-left transition-colors",
                    runMode === item.key
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/40",
                  )}
                  onClick={() => setRunMode(item.key)}
                >
                  <item.icon className="mt-0.5 size-5 text-primary" />
                  <div>
                    <div className="text-sm font-medium">{item.label}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {item.desc}
                    </div>
                  </div>
                </button>
              ))}
              {runMode === "cron" ? (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                  <div className="mb-2 text-xs text-muted-foreground">
                    {t.workflows.scheduleHint}
                  </div>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {SCHEDULE_FIELDS.map((field) => (
                      <Input
                        key={field.key}
                        type="number"
                        inputMode="numeric"
                        placeholder={field.placeholder}
                        min={field.min}
                        max={field.max}
                        value={scheduleParts[field.key]}
                        onChange={(event) => {
                          const nextValue = event.target.value;
                          setScheduleParts((prev) => ({
                            ...prev,
                            [field.key]: nextValue,
                          }));
                        }}
                      />
                    ))}
                  </div>
                  <div className="mt-2 text-[11px] text-muted-foreground">
                    {t.workflows.scheduleEmptyRunsNow}
                  </div>
                </div>
              ) : null}
              <div className="mt-2 flex flex-col gap-1.5">
                <span className="text-sm font-medium">Runtime provider</span>
                <Select
                  value={runtimeProvider}
                  onValueChange={(value) => setRuntimeProvider(value as TaskAgentRuntimeProvider)}
                >
                  <SelectTrigger className="border-primary/30 bg-card text-foreground data-[placeholder]:text-muted-foreground focus-visible:ring-primary/30">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-primary/20 bg-popover text-popover-foreground">
                    {TASK_RUNTIME_PROVIDER_OPTIONS.map((provider) => (
                      <SelectItem key={provider} value={provider}>
                        {formatTaskRuntimeProvider(provider)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              </div>
            </div>
          )}

          <DialogFooter className="gap-2 sm:gap-0">
            {wizardStepIndex > 0 && (
              <Button variant="outline" onClick={handleWizardBack}>
                {t.workflows.back}
              </Button>
            )}
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              {t.common.cancel}
            </Button>
            {isLastStep ? (
              <Button
                onClick={handleCreate}
                disabled={!taskName.trim() || createMutation.isPending}
              >
                {createMutation.isPending ? (
                  <Loader2Icon className="mr-1.5 size-3.5 animate-spin" />
                ) : null}
                {t.workflows.create}
              </Button>
            ) : (
              <Button
                onClick={handleWizardNext}
                disabled={wizardStep === "task" && !taskName.trim()}
              >
                {t.setupWizard.next}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!editTaskId} onOpenChange={(open) => !open && setEditTaskId(null)}>
        <DialogContent className="flex w-[min(96vw,46rem)] max-h-[calc(100vh-4rem)] flex-col overflow-hidden sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{t.common.settings}</DialogTitle>
            <DialogDescription>{editableTaskWorkspace?.name ?? ""}</DialogDescription>
          </DialogHeader>
          <div className="min-h-0 overflow-y-auto py-2 pr-1">
            <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">{t.workflows.taskName}</span>
              <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">{t.workflows.taskGoal}</span>
              <Textarea value={editGoal} onChange={(e) => setEditGoal(e.target.value)} rows={3} />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">{t.workflows.wizardStepTopology}</span>
                <div className="grid gap-2">
                  {(["chain", "branch", "swarm"] as const).map((item) => (
                    <Button
                      key={item}
                      variant={editTopology === item ? "default" : "outline"}
                      className="justify-start"
                      onClick={() => setEditTopology(item)}
                    >
                      {topoLabel(item)}
                    </Button>
                  ))}
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">{t.workflows.wizardStepExecution}</span>
                <div className="grid gap-2">
                  {(["chat", "cron", "yolo"] as const).map((item) => (
                    <Button
                      key={item}
                      variant={editRunMode === item ? "default" : "outline"}
                      className="justify-start"
                      onClick={() => setEditRunMode(item)}
                    >
                      {item === "chat" ? t.workflows.modeChat : item === "cron" ? t.workflows.modeCron : t.workflows.modeYolo}
                    </Button>
                  ))}
                </div>
                {editRunMode === "cron" ? (
                  <div className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                    <div className="mb-2 text-xs text-muted-foreground">
                      {t.workflows.scheduleHint}
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {SCHEDULE_FIELDS.map((field) => (
                        <Input
                          key={`edit-${field.key}`}
                          type="number"
                          inputMode="numeric"
                          placeholder={field.placeholder}
                          min={field.min}
                          max={field.max}
                          value={editScheduleParts[field.key]}
                          onChange={(event) => {
                            const nextValue = event.target.value;
                            setEditScheduleParts((prev) => ({
                              ...prev,
                              [field.key]: nextValue,
                            }));
                          }}
                        />
                      ))}
                    </div>
                    <div className="mt-2 text-[11px] text-muted-foreground">
                      {t.workflows.scheduleEmptyRunsNow}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>

            {/* Primary Agent */}
            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">{t.workflows.wizardPrimaryAgent}</span>
              <Select
                value={editPrimaryAgent || "__default__"}
                onValueChange={(v) => setEditPrimaryAgent(v === "__default__" ? "" : v)}
              >
                <SelectTrigger className="border-primary/30 bg-card text-foreground data-[placeholder]:text-muted-foreground focus-visible:ring-primary/30">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-w-[min(42rem,calc(100vw-2rem))] border-primary/20 bg-popover text-popover-foreground">
                  <SelectItem value="__default__">{t.workflows.systemDefault}</SelectItem>
                  {availableAgents.map((ag) => (
                    <SelectItem key={ag.name} value={ag.name} className="items-start py-2">
                      <div className="min-w-0 whitespace-normal">
                        <div className="break-words font-medium">{ag.name}</div>
                        {ag.description ? (
                          <div className="mt-0.5 break-words text-xs text-muted-foreground">
                            {ag.description}
                          </div>
                        ) : null}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Sub-Agents (for branch / swarm topologies) */}
            {editTopology !== "chain" && (
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">{t.workflows.wizardSubAgents}</span>
                <div className="mt-1 grid max-h-40 gap-1.5 overflow-y-auto">
                  {availableAgents
                    .filter((ag) => ag.name !== editPrimaryAgent)
                    .map((ag) => {
                      const isSelected = editSubAgents.includes(ag.name);
                      return (
                        <button
                          key={ag.name}
                          type="button"
                          className={cn(
                            "flex items-center gap-2 rounded-md border px-3 py-2 text-left text-sm transition-colors",
                            isSelected
                              ? "border-primary bg-primary/5"
                              : "border-border hover:border-primary/40",
                          )}
                          onClick={() => {
                            setEditSubAgents((prev) =>
                              isSelected
                                ? prev.filter((n) => n !== ag.name)
                                : [...prev, ag.name],
                            );
                          }}
                        >
                          <div className={cn(
                            "flex size-4 items-center justify-center rounded border",
                            isSelected ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/30"
                          )}>
                            {isSelected && <CheckCircle2Icon className="size-3" />}
                          </div>
                          <span className="truncate">{ag.name}</span>
                        </button>
                      );
                    })}
                </div>
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">Runtime provider</span>
              <Select
                value={editProvider}
                onValueChange={(value) => setEditProvider(value as TaskAgentRuntimeProvider)}
              >
                <SelectTrigger className="border-primary/30 bg-card text-foreground data-[placeholder]:text-muted-foreground focus-visible:ring-primary/30">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-primary/20 bg-popover text-popover-foreground">
                  {TASK_RUNTIME_PROVIDER_OPTIONS.map((provider) => (
                    <SelectItem key={provider} value={provider}>
                      {formatTaskRuntimeProvider(provider)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTaskId(null)}>{t.common.cancel}</Button>
            <Button onClick={() => void handleSaveWorkflow()} disabled={!editName.trim() || updateTaskMutation.isPending}>
              {updateTaskMutation.isPending ? t.common.loading : t.common.save}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
