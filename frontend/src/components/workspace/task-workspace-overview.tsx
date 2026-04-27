"use client";

import {
  AlertCircleIcon,
  ArrowRightIcon,
  CirclePauseIcon,
  EyeIcon,
  FolderKanbanIcon,
  PlayIcon,
  PlusIcon,
  RefreshCcwIcon,
  SearchIcon,
  SquareIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { postJSON } from "@/core/api/http";
import {
  useCreateTaskWorkspace,
  useCreateTaskCheckpoint,
  useTaskCardGraph,
  useTaskWorkspaceAction,
  useTaskWorkspace,
  useTaskWorkspaces,
  useUpdateTaskCardGraph,
  useUpdateTaskWorkspace,
  type AgentHandleStatus,
  type TaskAgentPermissionMode,
  type TaskCardStatus,
  type TaskExecutionMode,
  type TaskWorkspaceStatus,
  type TaskWorkspaceSummary,
} from "@/core/task-workspaces";
import { formatTimeAgo } from "@/core/utils/datetime";

function statusTone(status: TaskWorkspaceStatus | TaskCardStatus | AgentHandleStatus) {
  if (status === "running" || status === "completed") return "default";
  if (status === "paused" || status === "waiting_review") return "secondary";
  if (status === "failed" || status === "terminated") return "destructive";
  return "outline";
}

function taskProgressLabel(task: TaskWorkspaceSummary) {
  if (task.progress.total_cards === 0) {
    return "No cards configured";
  }
  return `${task.progress.completed_cards}/${task.progress.total_cards} cards`;
}

type StatusFilter = "all" | TaskWorkspaceStatus;
type HealthFilter = "all" | TaskHealth;
type SortKey = "updated_desc" | "updated_asc" | "name_asc" | "progress_desc";

type TaskHealth = "healthy" | "watch" | "blocked" | "completed";
type ActivityItem = {
  detail: string;
  id: string;
  kind: "agent" | "checkpoint" | "task";
  label: string;
  timestamp: string;
};
type BulkActionResult = {
  action: "pause" | "resume";
  failed: number;
  message: string;
  succeeded: number;
};

function canPause(status: TaskWorkspaceStatus) {
  return status === "created" || status === "planned" || status === "running";
}

function canResume(status: TaskWorkspaceStatus) {
  return status === "paused" || status === "waiting_review";
}

function canTerminate(status: TaskWorkspaceStatus) {
  return status !== "terminated" && status !== "completed" && status !== "failed";
}

function taskModeLabel(mode: TaskExecutionMode) {
  if (mode === "branch") return "Branch";
  if (mode === "group") return "Group";
  return "Single";
}

function healthTone(health: TaskHealth) {
  if (health === "healthy" || health === "completed") return "default";
  if (health === "watch") return "secondary";
  return "destructive";
}

function deriveTaskHealth(task: TaskWorkspaceSummary | NonNullable<ReturnType<typeof useTaskWorkspace>["taskWorkspace"]>) {
  if (task.status === "completed") {
    return { health: "completed" as const, note: "Execution complete" };
  }
  if (task.status === "failed" || task.status === "terminated") {
    return { health: "blocked" as const, note: "Task requires intervention" };
  }
  if (task.status === "waiting_review") {
    return { health: "watch" as const, note: "Waiting for review" };
  }
  if (task.status === "paused") {
    return { health: "watch" as const, note: "Paused and waiting to resume" };
  }
  if (task.progress.total_cards > 0 && task.progress.completed_cards === 0 && task.progress.active_agents === 0) {
    return { health: "blocked" as const, note: "Planned but no active execution" };
  }
  if (task.progress.active_agents > 0 || task.status === "running") {
    return { health: "healthy" as const, note: "Actively progressing" };
  }
  return { health: "watch" as const, note: "Needs a push to continue" };
}

function activityTone(kind: ActivityItem["kind"]) {
  if (kind === "checkpoint") return "secondary";
  if (kind === "agent") return "default";
  return "outline";
}

function detailTabForActivity(kind: ActivityItem["kind"]) {
  if (kind === "checkpoint") return "checkpoints";
  if (kind === "agent") return "agents";
  return "cards";
}

function detailTabForHealth(health: TaskHealth) {
  if (health === "blocked") return "cards";
  if (health === "watch") return "agents";
  if (health === "completed") return "checkpoints";
  return "brain";
}

function sortTasks(tasks: TaskWorkspaceSummary[], sortKey: SortKey) {
  const list = [...tasks];
  list.sort((left, right) => {
    if (sortKey === "updated_desc") {
      return Date.parse(right.updated_at) - Date.parse(left.updated_at);
    }
    if (sortKey === "updated_asc") {
      return Date.parse(left.updated_at) - Date.parse(right.updated_at);
    }
    if (sortKey === "name_asc") {
      return left.name.localeCompare(right.name);
    }
    const leftRatio =
      left.progress.total_cards === 0
        ? 0
        : left.progress.completed_cards / left.progress.total_cards;
    const rightRatio =
      right.progress.total_cards === 0
        ? 0
        : right.progress.completed_cards / right.progress.total_cards;
    return rightRatio - leftRatio;
  });
  return list;
}

function TaskWorkspacePreviewSheet({
  onOpenChange,
  open,
  taskId,
}: {
  open: boolean;
  taskId: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const { isLoading, taskWorkspace } = useTaskWorkspace(taskId, { enabled: open });
  const { cardGraph } = useTaskCardGraph(taskId, { enabled: open });
  const updateTaskWorkspace = useUpdateTaskWorkspace(taskId ?? "");
  const updateTaskCardGraph = useUpdateTaskCardGraph(taskId ?? "");
  const createCheckpoint = useCreateTaskCheckpoint(taskId ?? "");
  const [draftGoal, setDraftGoal] = useState("");
  const [draftSummary, setDraftSummary] = useState("");

  const cardStatusSummary = useMemo(() => {
    const counts = new Map<string, number>();
    for (const card of cardGraph?.card_graph.cards ?? []) {
      counts.set(card.status, (counts.get(card.status) ?? 0) + 1);
    }
    return [...counts.entries()].sort((left, right) => right[1] - left[1]);
  }, [cardGraph]);

  const selectedRuntime = taskWorkspace?.runtime_profiles.find((profile) => profile.selected);
  const recentActivity = useMemo<ActivityItem[]>(() => {
    if (!taskWorkspace) {
      return [];
    }

    return [
      {
        id: `task-updated-${taskWorkspace.task_id}`,
        kind: "task" as const,
        label: "Task updated",
        detail: `${taskWorkspace.name} was updated`,
        timestamp: taskWorkspace.updated_at,
      },
      ...taskWorkspace.checkpoints.map((checkpoint) => ({
        id: checkpoint.checkpoint_id,
        kind: "checkpoint" as const,
        label: "Checkpoint saved",
        detail: checkpoint.note ?? checkpoint.label,
        timestamp: checkpoint.created_at,
      })),
      ...taskWorkspace.agents
        .filter((agent) => agent.conversation.last_message_at)
        .map((agent) => ({
          id: `agent-${agent.agent_id}`,
          kind: "agent" as const,
          label: `${agent.name} activity`,
          detail: `${agent.conversation.message_count} messages in transcript`,
          timestamp: agent.conversation.last_message_at!,
        })),
    ].sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp));
  }, [taskWorkspace]);
  const previewHealth = taskWorkspace ? deriveTaskHealth(taskWorkspace) : null;

  const handleSaveSummary = async () => {
    if (!taskWorkspace) return;
    try {
      await updateTaskWorkspace.mutateAsync({
        goal: draftGoal,
        summary: draftSummary,
      });
      toast.success("Task preview details saved.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save task details.");
    }
  };

  const handleCheckpoint = async () => {
    if (!taskWorkspace) return;
    try {
      await createCheckpoint.mutateAsync({
        label: `Checkpoint ${new Date().toLocaleTimeString()}`,
        note: "Created from task overview preview.",
      });
      toast.success("Checkpoint created.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to create checkpoint.");
    }
  };

  const handlePermissionModeChange = async (
    cardId: string,
    permissionMode: TaskAgentPermissionMode,
  ) => {
    if (!taskWorkspace || !cardGraph) return;
    try {
      const nextGraph = {
        ...cardGraph.card_graph,
        cards: cardGraph.card_graph.cards.map((card) =>
          card.card_id === cardId ? { ...card, permission_mode: permissionMode } : card,
        ),
      };
      await updateTaskCardGraph.mutateAsync({ card_graph: nextGraph });
      toast.success("Agent card permission updated.");
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to update agent card permission.",
      );
    }
  };

  useEffect(() => {
    if (!taskWorkspace) {
      return;
    }
    setDraftGoal(taskWorkspace.goal);
    setDraftSummary(taskWorkspace.summary);
  }, [taskWorkspace]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-2xl" side="right">
        <SheetHeader className="border-b">
          <SheetTitle>
            {taskWorkspace?.name ?? (taskId ? "Loading task preview" : "Task preview")}
          </SheetTitle>
          <SheetDescription>
            Review summary, cards, agents, runtime, and checkpoints without leaving the
            overview surface.
          </SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 px-4 pb-4">
          {isLoading || taskWorkspace == null ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Loading task preview…
            </div>
          ) : (
            <Tabs className="flex h-full min-h-0 flex-col gap-4" defaultValue="summary">
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="summary">Summary</TabsTrigger>
                <TabsTrigger value="cards">Cards</TabsTrigger>
                <TabsTrigger value="agents">Agents</TabsTrigger>
                <TabsTrigger value="checkpoints">Checkpoints</TabsTrigger>
              </TabsList>
              <TabsContent className="min-h-0 flex-1" value="summary">
                <ScrollArea className="h-[70vh] rounded-xl border">
                  <div className="space-y-4 p-4">
                    <div className="grid gap-3 md:grid-cols-2">
                      <Card className="shadow-none">
                        <CardHeader className="pb-2">
                          <CardDescription>Status</CardDescription>
                          <CardTitle className="flex items-center gap-2 text-lg">
                            <Badge variant={statusTone(taskWorkspace.status)}>
                              {taskWorkspace.status}
                            </Badge>
                            <span>{taskModeLabel(taskWorkspace.mode)} mode</span>
                          </CardTitle>
                        </CardHeader>
                      </Card>
                      <Card className="shadow-none">
                        <CardHeader className="pb-2">
                          <CardDescription>Progress</CardDescription>
                          <CardTitle className="text-lg">
                            {taskProgressLabel(taskWorkspace)}
                          </CardTitle>
                        </CardHeader>
                      </Card>
                    </div>
                    <Card className="shadow-none">
                      <CardHeader className="pb-2">
                        <CardDescription>Health</CardDescription>
                        <CardTitle className="flex items-center gap-2 text-lg">
                          <Badge variant={healthTone(previewHealth?.health ?? "watch")}>
                            {previewHealth?.health ?? "watch"}
                          </Badge>
                          <span>{previewHealth?.note ?? "No health signal yet"}</span>
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <Button asChild size="sm" variant="outline">
                          <Link
                            href={`/workspace/workflows/${taskWorkspace.task_id}?tab=${detailTabForHealth(previewHealth?.health ?? "watch")}`}
                          >
                            Open health context
                          </Link>
                        </Button>
                      </CardContent>
                    </Card>
                    <Card className="shadow-none">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">Goal</CardTitle>
                      </CardHeader>
                      <CardContent className="text-sm text-muted-foreground">
                        {taskWorkspace.goal ?? "No goal captured yet."}
                      </CardContent>
                    </Card>
                    <Card className="shadow-none">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">Summary</CardTitle>
                      </CardHeader>
                      <CardContent className="text-sm text-muted-foreground">
                        {taskWorkspace.summary ?? "No summary available yet."}
                      </CardContent>
                    </Card>
                    <div className="grid gap-3 md:grid-cols-3">
                      <Card className="shadow-none">
                        <CardHeader className="pb-2">
                          <CardDescription>Agents</CardDescription>
                          <CardTitle className="text-lg">
                            {taskWorkspace.agents.length}
                          </CardTitle>
                        </CardHeader>
                      </Card>
                      <Card className="shadow-none">
                        <CardHeader className="pb-2">
                          <CardDescription>Checkpoints</CardDescription>
                          <CardTitle className="text-lg">
                            {taskWorkspace.checkpoints.length}
                          </CardTitle>
                        </CardHeader>
                      </Card>
                      <Card className="shadow-none">
                        <CardHeader className="pb-2">
                          <CardDescription>Runtime</CardDescription>
                          <CardTitle className="text-lg">
                            {selectedRuntime?.label ?? "None selected"}
                          </CardTitle>
                        </CardHeader>
                      </Card>
                    </div>
                    <Card className="shadow-none">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">Interfaces</CardTitle>
                      </CardHeader>
                      <CardContent className="flex flex-wrap gap-2">
                        {taskWorkspace.deployment_interfaces.length === 0 ? (
                          <span className="text-sm text-muted-foreground">
                            No deployment interfaces configured.
                          </span>
                        ) : (
                          taskWorkspace.deployment_interfaces.map((item) => (
                            <Badge key={item.label} variant={item.enabled ? "default" : "outline"}>
                              {item.label}
                            </Badge>
                          ))
                        )}
                      </CardContent>
                    </Card>
                    <Card className="shadow-none">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">Quick actions</CardTitle>
                        <CardDescription>
                          Make light task updates without leaving the overview.
                        </CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <div className="space-y-2">
                          <div className="text-sm font-medium">Goal</div>
                          <Textarea
                            value={draftGoal}
                            onChange={(event) => setDraftGoal(event.target.value)}
                            placeholder="Refine the task goal"
                          />
                        </div>
                        <div className="space-y-2">
                          <div className="text-sm font-medium">Summary</div>
                          <Textarea
                            value={draftSummary}
                            onChange={(event) => setDraftSummary(event.target.value)}
                            placeholder="Capture the current task summary"
                          />
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            onClick={handleSaveSummary}
                            disabled={updateTaskWorkspace.isPending}
                          >
                            Save details
                          </Button>
                          <Button
                            variant="outline"
                            onClick={handleCheckpoint}
                            disabled={createCheckpoint.isPending}
                          >
                            Create checkpoint
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                    <Card className="shadow-none">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">Recent activity</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        {recentActivity.length === 0 ? (
                          <p className="text-sm text-muted-foreground">
                            No recent activity available yet.
                          </p>
                        ) : (
                          recentActivity.slice(0, 8).map((item) => (
                            <div
                              className="rounded-lg border px-3 py-2"
                              key={item.id}
                            >
                              <div className="flex items-center justify-between gap-3">
                                <div className="flex items-center gap-2">
                                  <Badge variant={activityTone(item.kind)}>{item.kind}</Badge>
                                  <div className="font-medium">{item.label}</div>
                                </div>
                                <div className="text-xs text-muted-foreground">
                                  {formatTimeAgo(item.timestamp)}
                                </div>
                              </div>
                              <div className="mt-1 text-sm text-muted-foreground">
                                {item.detail}
                              </div>
                              <div className="mt-2">
                                <Button asChild size="sm" variant="ghost">
                                  <Link
                                    href={`/workspace/workflows/${taskWorkspace.task_id}?tab=${detailTabForActivity(item.kind)}`}
                                  >
                                    Open in detail
                                  </Link>
                                </Button>
                              </div>
                            </div>
                          ))
                        )}
                      </CardContent>
                    </Card>
                  </div>
                </ScrollArea>
              </TabsContent>
              <TabsContent className="min-h-0 flex-1" value="cards">
                <ScrollArea className="h-[70vh] rounded-xl border">
                  <div className="space-y-4 p-4">
                    <div className="flex flex-wrap gap-2">
                      {cardStatusSummary.length === 0 ? (
                        <span className="text-sm text-muted-foreground">
                          No task cards configured.
                        </span>
                      ) : (
                        cardStatusSummary.map(([status, count]) => (
                          <Badge key={status} variant="outline">
                            {status}: {count}
                          </Badge>
                        ))
                      )}
                    </div>
                    <Separator />
                    <div className="space-y-3">
                      {cardGraph?.card_graph.cards.length ? (
                        cardGraph.card_graph.cards.map((card) => (
                          <Card className="shadow-none" key={card.card_id}>
                            <CardHeader className="pb-2">
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <CardTitle className="text-base">{card.title}</CardTitle>
                                  <CardDescription>{card.kind}</CardDescription>
                                </div>
                                <Badge variant={statusTone(card.status)}>{card.status}</Badge>
                              </div>
                            </CardHeader>
                            <CardContent className="space-y-2 text-sm text-muted-foreground">
                              <p>{card.description ?? "No description provided."}</p>
                              {card.kind === "agent" ? (
                                <div className="space-y-2 rounded-lg border bg-muted/10 p-3">
                                  <div className="text-xs font-medium uppercase tracking-wide text-foreground/80">
                                    Permission Mode
                                  </div>
                                  <Select
                                    onValueChange={(value) =>
                                      void handlePermissionModeChange(
                                        card.card_id,
                                        value as TaskAgentPermissionMode,
                                      )
                                    }
                                    value={card.permission_mode}
                                  >
                                    <SelectTrigger className="w-full bg-background">
                                      <SelectValue placeholder="Select permission mode" />
                                    </SelectTrigger>
                                    <SelectContent>
                                      <SelectItem value="workspace">
                                        Workspace only
                                      </SelectItem>
                                      <SelectItem value="system">
                                        System tools
                                      </SelectItem>
                                      <SelectItem value="yolo">
                                        YOLO full trust
                                      </SelectItem>
                                    </SelectContent>
                                  </Select>
                                  <p className="text-xs text-muted-foreground">
                                    {card.permission_mode === "workspace"
                                      ? "Autonomous actions stay scoped to the workspace and bounded file/system-safe operations."
                                      : card.permission_mode === "system"
                                        ? "System-level tools and browser/system execution can proceed without approval prompts."
                                        : "Full-trust mode. Execute directly, suppress approval prompts, and return concrete results only."}
                                  </p>
                                </div>
                              ) : null}
                              {card.tags.length > 0 ? (
                                <div className="flex flex-wrap gap-2">
                                  {card.tags.map((tag) => (
                                    <Badge key={tag} variant="outline">
                                      {tag}
                                    </Badge>
                                  ))}
                                </div>
                              ) : null}
                            </CardContent>
                          </Card>
                        ))
                      ) : (
                        <Card className="border-dashed shadow-none">
                          <CardHeader>
                            <CardTitle className="text-base">No cards yet</CardTitle>
                            <CardDescription>
                              Card graph details will appear here once the task is planned.
                            </CardDescription>
                          </CardHeader>
                        </Card>
                      )}
                    </div>
                  </div>
                </ScrollArea>
              </TabsContent>
              <TabsContent className="min-h-0 flex-1" value="agents">
                <ScrollArea className="h-[70vh] rounded-xl border">
                  <div className="space-y-3 p-4">
                    {taskWorkspace.agents.length === 0 ? (
                      <Card className="border-dashed shadow-none">
                        <CardHeader>
                          <CardTitle className="text-base">No agents assigned</CardTitle>
                          <CardDescription>
                            Agent handles will show up here when the task starts execution.
                          </CardDescription>
                        </CardHeader>
                      </Card>
                    ) : (
                      taskWorkspace.agents.map((agent) => (
                        <Card className="shadow-none" key={agent.agent_id}>
                          <CardHeader className="pb-2">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <CardTitle className="text-base">{agent.name}</CardTitle>
                                <CardDescription>
                                  {agent.task_scope ?? agent.role}
                                </CardDescription>
                              </div>
                              <Badge variant={statusTone(agent.status)}>{agent.status}</Badge>
                            </div>
                          </CardHeader>
                          <CardContent className="grid gap-2 text-sm text-muted-foreground">
                            <div>Model: {agent.model_name ?? "Not assigned"}</div>
                            <div>
                              Messages: {agent.conversation.message_count}
                              {agent.conversation.last_message_at
                                ? ` · updated ${formatTimeAgo(agent.conversation.last_message_at)}`
                                : ""}
                            </div>
                          </CardContent>
                        </Card>
                      ))
                    )}
                  </div>
                </ScrollArea>
              </TabsContent>
              <TabsContent className="min-h-0 flex-1" value="checkpoints">
                <ScrollArea className="h-[70vh] rounded-xl border">
                  <div className="space-y-3 p-4">
                    {taskWorkspace.checkpoints.length === 0 ? (
                      <Card className="border-dashed shadow-none">
                        <CardHeader>
                          <CardTitle className="text-base">No checkpoints yet</CardTitle>
                          <CardDescription>
                            Save checkpoints to preserve task state, card state, and agent work.
                          </CardDescription>
                        </CardHeader>
                      </Card>
                    ) : (
                      taskWorkspace.checkpoints.map((checkpoint) => (
                        <Card className="shadow-none" key={checkpoint.checkpoint_id}>
                          <CardHeader className="pb-2">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <CardTitle className="text-base">{checkpoint.label}</CardTitle>
                                <CardDescription>{checkpoint.task_status}</CardDescription>
                              </div>
                              <Badge variant="outline">
                                {formatTimeAgo(checkpoint.created_at)}
                              </Badge>
                            </div>
                          </CardHeader>
                          <CardContent className="text-sm text-muted-foreground">
                            {checkpoint.note ?? "Task workspace checkpoint saved."}
                          </CardContent>
                        </Card>
                      ))
                    )}
                  </div>
                </ScrollArea>
              </TabsContent>
            </Tabs>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function TaskWorkspaceSummaryCard({
  selected,
  task,
  onSelect,
  onPreview,
}: {
  onSelect: (taskId: string, checked: boolean) => void;
  onPreview: (taskId: string) => void;
  selected: boolean;
  task: TaskWorkspaceSummary;
}) {
  const pauseTask = useTaskWorkspaceAction(task.task_id, "pause");
  const resumeTask = useTaskWorkspaceAction(task.task_id, "resume");
  const terminateTask = useTaskWorkspaceAction(task.task_id, "terminate");
  const health = deriveTaskHealth(task);

  return (
    <Card className="shadow-none">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <input
              aria-label={`Select ${task.name}`}
              checked={selected}
              className="mt-1 size-4"
              onChange={(event) => onSelect(task.task_id, event.target.checked)}
              type="checkbox"
            />
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2 text-base">
                <FolderKanbanIcon className="size-4" />
                {task.name}
              </CardTitle>
              <CardDescription>
                {taskModeLabel(task.mode)} mode · {task.status} · {taskProgressLabel(task)}
              </CardDescription>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={statusTone(task.status)}>{task.status}</Badge>
            <Badge variant={healthTone(health.health)}>{health.health}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 text-sm md:grid-cols-3">
          <div className="rounded-lg border p-3">
            <div className="font-medium">Goal</div>
            <div className="mt-1 line-clamp-3 text-muted-foreground">
              {task.goal.trim().length > 0 ? task.goal : "No goal captured yet."}
            </div>
          </div>
          <div className="rounded-lg border p-3">
            <div className="font-medium">Agents</div>
            <div className="mt-1 text-muted-foreground">
              {task.progress.active_agents} active · {task.progress.completed_agents} completed
            </div>
          </div>
          <div className="rounded-lg border p-3">
            <div className="font-medium">Updated</div>
            <div className="mt-1 text-muted-foreground">
              {formatTimeAgo(task.updated_at)}
            </div>
          </div>
        </div>
        <div className="rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground">
          {health.note}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm">
            <Link href={`/workspace/workflows/${task.task_id}`}>
              Open workspace
              <ArrowRightIcon className="size-4" />
            </Link>
          </Button>
          <Button size="sm" variant="outline" onClick={() => onPreview(task.task_id)}>
            <EyeIcon className="size-4" />
            Preview
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => pauseTask.mutate()}
            disabled={!canPause(task.status) || pauseTask.isPending}
          >
            <CirclePauseIcon className="size-4" />
            Pause
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => resumeTask.mutate()}
            disabled={!canResume(task.status) || resumeTask.isPending}
          >
            <PlayIcon className="size-4" />
            Resume
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => terminateTask.mutate()}
            disabled={!canTerminate(task.status) || terminateTask.isPending}
          >
            <SquareIcon className="size-4" />
            Terminate
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function TaskWorkspaceOverview() {
  const router = useRouter();
  const { error, isLoading, refetch, workspaces } = useTaskWorkspaces();
  const createTaskWorkspaceMutation = useCreateTaskWorkspace();
  const [query, setQuery] = useState("");
  const [healthFilter, setHealthFilter] = useState<HealthFilter>("all");
  const [bulkActionPending, setBulkActionPending] = useState<"pause" | "resume" | null>(null);
  const [lastBulkResult, setLastBulkResult] = useState<BulkActionResult | null>(null);
  const [previewTaskId, setPreviewTaskId] = useState<string | null>(null);
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("updated_desc");

  const handleCreate = async () => {
    try {
      const nextIndex = workspaces.length + 1;
      const workspace = await createTaskWorkspaceMutation.mutateAsync({
        name: `Task ${nextIndex}`,
        mode: "single",
      });
      router.push(`/workspace/workflows/${workspace.task_id}`);
    } catch {
      // Global MutationCache onError shows the toast
    }
  };

  const filteredWorkspaces = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const visible = workspaces.filter((task) => {
      if (statusFilter !== "all" && task.status !== statusFilter) {
        return false;
      }
      if (healthFilter !== "all" && deriveTaskHealth(task).health !== healthFilter) {
        return false;
      }
      if (!normalizedQuery) {
        return true;
      }
      return [task.name, task.goal, task.mode, task.status].some((value) =>
        value.toLowerCase().includes(normalizedQuery),
      );
    });
    return sortTasks(visible, sortKey);
  }, [healthFilter, query, sortKey, statusFilter, workspaces]);

  const selectedVisibleTasks = useMemo(
    () => filteredWorkspaces.filter((task) => selectedTaskIds.includes(task.task_id)),
    [filteredWorkspaces, selectedTaskIds],
  );

  useEffect(() => {
    const validTaskIds = new Set(workspaces.map((task) => task.task_id));
    setSelectedTaskIds((current) => current.filter((taskId) => validTaskIds.has(taskId)));
  }, [workspaces]);

  const bulkPauseableCount = selectedVisibleTasks.filter((task) =>
    canPause(task.status),
  ).length;
  const bulkResumeableCount = selectedVisibleTasks.filter((task) =>
    canResume(task.status),
  ).length;

  const handleSelectTask = (taskId: string, checked: boolean) => {
    setSelectedTaskIds((current) => {
      if (checked) {
        return current.includes(taskId) ? current : [...current, taskId];
      }
      return current.filter((id) => id !== taskId);
    });
  };

  const handleSelectNeedsAttention = () => {
    setHealthFilter("all");
    setSelectedTaskIds(
      workspaces
        .filter((task) => {
          const health = deriveTaskHealth(task).health;
          return health === "blocked" || health === "watch";
        })
        .map((task) => task.task_id),
    );
  };

  const runBulkAction = async (action: "pause" | "resume") => {
    const actionTasks = selectedVisibleTasks.filter((task) =>
      action === "pause" ? canPause(task.status) : canResume(task.status),
    );
    if (actionTasks.length === 0) {
      setLastBulkResult(null);
      toast.error(`No selected tasks can ${action}.`);
      return;
    }

    setBulkActionPending(action);
    try {
      const results = await Promise.allSettled(
        actionTasks.map(async (task) => {
          const path =
            action === "pause"
              ? `/api/task-workspaces/${task.task_id}/pause`
              : `/api/task-workspaces/${task.task_id}/resume`;
          await postJSON(path);
          return task.task_id;
        }),
      );

      const succeeded = results.filter((result) => result.status === "fulfilled");
      const failed = results.filter((result) => result.status === "rejected");

      if (succeeded.length > 0) {
        setSelectedTaskIds((current) =>
          current.filter(
            (taskId) =>
              !succeeded.some(
                (result) => result.status === "fulfilled" && result.value === taskId,
              ),
          ),
        );
      }

      await refetch();

      if (failed.length === 0) {
        setLastBulkResult({
          action,
          failed: 0,
          message: `${succeeded.length} task(s) ${action}d successfully.`,
          succeeded: succeeded.length,
        });
        toast.success(`${succeeded.length} task(s) ${action}d.`);
        return;
      }

      if (succeeded.length === 0) {
        const firstError = failed[0];
        const message =
          firstError?.status === "rejected"
            ? firstError.reason instanceof Error
              ? firstError.reason.message
              : `Failed to ${action} selected tasks.`
            : `Failed to ${action} selected tasks.`;
        setLastBulkResult({
          action,
          failed: failed.length,
          message,
          succeeded: 0,
        });
        toast.error(
          message,
        );
        return;
      }

      const firstError = failed[0];
      const errorMessage =
        firstError?.status === "rejected"
          ? firstError.reason instanceof Error
            ? firstError.reason.message
            : "Unknown error"
          : "Unknown error";
      setLastBulkResult({
        action,
        failed: failed.length,
        message: errorMessage,
        succeeded: succeeded.length,
      });
      toast.warning(
        `${succeeded.length} task(s) ${action}d, ${failed.length} failed: ${errorMessage}`,
      );
    } catch (error) {
      setLastBulkResult({
        action,
        failed: actionTasks.length,
        message: error instanceof Error ? error.message : `Failed to ${action} tasks.`,
        succeeded: 0,
      });
      toast.error(error instanceof Error ? error.message : `Failed to ${action} tasks.`);
    } finally {
      setBulkActionPending(null);
    }
  };

  const summary = useMemo(() => {
    return workspaces.reduce(
      (accumulator, task) => {
        accumulator.total += 1;
        if (task.status === "running") accumulator.running += 1;
        if (task.status === "paused") accumulator.paused += 1;
        if (task.status === "completed") accumulator.completed += 1;
        accumulator.activeAgents += task.progress.active_agents;
        return accumulator;
      },
      { activeAgents: 0, completed: 0, paused: 0, running: 0, total: 0 },
    );
  }, [workspaces]);

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody>
        <>
          <TaskWorkspacePreviewSheet
            open={previewTaskId != null}
            taskId={previewTaskId}
            onOpenChange={(open) => {
              if (!open) {
                setPreviewTaskId(null);
              }
            }}
          />
          <div className="flex size-full flex-col">
          <header className="flex shrink-0 items-center justify-between gap-4 border-b px-6 py-5">
            <div>
              <h1 className="text-xl font-semibold">Task Workspace Overview</h1>
              <p className="text-sm text-muted-foreground">
                Review every task, its card progress, and its live execution state from one surface.
              </p>
            </div>
            <Button onClick={handleCreate} disabled={createTaskWorkspaceMutation.isPending}>
              <PlusIcon className="size-4" />
              New Task
            </Button>
          </header>
          <main className="min-h-0 flex-1">
            <ScrollArea className="size-full">
              <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-6">
                <section className="grid gap-3 md:grid-cols-4">
                  <Card className="shadow-none">
                    <CardHeader className="pb-2">
                      <CardDescription>Total tasks</CardDescription>
                      <CardTitle className="text-2xl">{summary.total}</CardTitle>
                    </CardHeader>
                  </Card>
                  <Card className="shadow-none">
                    <CardHeader className="pb-2">
                      <CardDescription>Running now</CardDescription>
                      <CardTitle className="text-2xl">{summary.running}</CardTitle>
                    </CardHeader>
                  </Card>
                  <Card className="shadow-none">
                    <CardHeader className="pb-2">
                      <CardDescription>Paused</CardDescription>
                      <CardTitle className="text-2xl">{summary.paused}</CardTitle>
                    </CardHeader>
                  </Card>
                  <Card className="shadow-none">
                    <CardHeader className="pb-2">
                      <CardDescription>Active agents</CardDescription>
                      <CardTitle className="text-2xl">{summary.activeAgents}</CardTitle>
                    </CardHeader>
                  </Card>
                </section>
                <section className="grid gap-3 rounded-xl border bg-card/60 p-4 md:grid-cols-[minmax(0,1fr)_180px_180px_auto]">
                  <label className="relative block">
                    <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      className="pl-9"
                      placeholder="Search tasks by name, goal, mode, or status"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                    />
                  </label>
                  <Select
                    value={statusFilter}
                    onValueChange={(value) => setStatusFilter(value as StatusFilter)}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="All statuses" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All statuses</SelectItem>
                      <SelectItem value="created">Created</SelectItem>
                      <SelectItem value="planned">Planned</SelectItem>
                      <SelectItem value="running">Running</SelectItem>
                      <SelectItem value="paused">Paused</SelectItem>
                      <SelectItem value="waiting_review">Waiting review</SelectItem>
                      <SelectItem value="completed">Completed</SelectItem>
                      <SelectItem value="terminated">Terminated</SelectItem>
                      <SelectItem value="failed">Failed</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select
                    value={sortKey}
                    onValueChange={(value) => setSortKey(value as SortKey)}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Sort tasks" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="updated_desc">Recently updated</SelectItem>
                      <SelectItem value="updated_asc">Oldest updated</SelectItem>
                      <SelectItem value="name_asc">Name A-Z</SelectItem>
                      <SelectItem value="progress_desc">Most progress</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button variant="outline" onClick={() => refetch()}>
                    <RefreshCcwIcon className="size-4" />
                    Refresh
                  </Button>
                </section>
                <section className="flex flex-wrap items-center gap-2 rounded-xl border bg-card/60 p-4">
                  <Button
                    size="sm"
                    variant={healthFilter === "blocked" ? "default" : "outline"}
                    onClick={() => setHealthFilter("blocked")}
                  >
                    Blocked
                  </Button>
                  <Button
                    size="sm"
                    variant={healthFilter === "watch" ? "default" : "outline"}
                    onClick={() => setHealthFilter("watch")}
                  >
                    Watch
                  </Button>
                  <Button
                    size="sm"
                    variant={healthFilter === "healthy" ? "default" : "outline"}
                    onClick={() => setHealthFilter("healthy")}
                  >
                    Healthy
                  </Button>
                  <Button
                    size="sm"
                    variant={healthFilter === "completed" ? "default" : "outline"}
                    onClick={() => setHealthFilter("completed")}
                  >
                    Completed
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setHealthFilter("all")}>
                    Clear health filter
                  </Button>
                  <Separator className="hidden h-6 md:block" orientation="vertical" />
                  <Button size="sm" variant="outline" onClick={handleSelectNeedsAttention}>
                    Select needing attention
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={bulkPauseableCount === 0 || bulkActionPending != null}
                    onClick={() => void runBulkAction("pause")}
                  >
                    {bulkActionPending === "pause"
                      ? "Pausing..."
                      : `Pause selected (${bulkPauseableCount})`}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={bulkResumeableCount === 0 || bulkActionPending != null}
                    onClick={() => void runBulkAction("resume")}
                  >
                    {bulkActionPending === "resume"
                      ? "Resuming..."
                      : `Resume selected (${bulkResumeableCount})`}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={selectedTaskIds.length === 0}
                    onClick={() => setSelectedTaskIds([])}
                  >
                    Clear selection
                  </Button>
                </section>
                {lastBulkResult ? (
                  <section className="rounded-xl border bg-card/60 p-4">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <Badge variant="outline">Last bulk action</Badge>
                      <Badge variant="outline">{lastBulkResult.action}</Badge>
                      <span>
                        {lastBulkResult.succeeded} succeeded / {lastBulkResult.failed} failed
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {lastBulkResult.message}
                    </p>
                  </section>
                ) : null}
                {error ? (
                  <Alert variant="destructive">
                    <AlertCircleIcon className="size-4" />
                    <AlertTitle>Task overview unavailable</AlertTitle>
                    <AlertDescription>
                      <p>
                        The task workspace list could not be loaded. Retry the query or
                        inspect the gateway logs if this keeps failing.
                      </p>
                      <Button className="mt-2" variant="outline" onClick={() => refetch()}>
                        Retry
                      </Button>
                    </AlertDescription>
                  </Alert>
                ) : null}
                {isLoading ? (
                  <Card className="border-dashed shadow-none">
                    <CardHeader>
                      <CardTitle>Loading tasks…</CardTitle>
                    </CardHeader>
                  </Card>
                ) : workspaces.length === 0 ? (
                  <Card className="border-dashed shadow-none">
                    <CardHeader>
                      <CardTitle>No task workspaces yet</CardTitle>
                      <CardDescription>
                        Create the first task to start building a card-first execution workspace.
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Button
                        onClick={handleCreate}
                        disabled={createTaskWorkspaceMutation.isPending}
                      >
                        <PlusIcon className="size-4" />
                        Create first task
                      </Button>
                    </CardContent>
                  </Card>
                ) : filteredWorkspaces.length === 0 ? (
                  <Card className="border-dashed shadow-none">
                    <CardHeader>
                      <CardTitle>No tasks match the current filters</CardTitle>
                      <CardDescription>
                        Broaden the search query or clear the status filter to see more
                        task workspaces.
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="flex flex-wrap gap-2">
                      <Button variant="outline" onClick={() => setQuery("")}>
                        Clear search
                      </Button>
                      <Button variant="outline" onClick={() => setStatusFilter("all")}>
                        Reset status filter
                      </Button>
                      <Button variant="outline" onClick={() => setHealthFilter("all")}>
                        Reset health filter
                      </Button>
                    </CardContent>
                  </Card>
                ) : (
                  <>
                    <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                      <Badge variant="outline">{filteredWorkspaces.length} visible</Badge>
                      <Badge variant="outline">{summary.completed} completed</Badge>
                      <Badge variant="outline">{selectedVisibleTasks.length} selected</Badge>
                      <span>Sorted by {sortKey.replaceAll("_", " ")}</span>
                    </div>
                    {filteredWorkspaces.map((task) => (
                      <TaskWorkspaceSummaryCard
                        key={task.task_id}
                        onSelect={handleSelectTask}
                        task={task}
                        onPreview={setPreviewTaskId}
                        selected={selectedTaskIds.includes(task.task_id)}
                      />
                    ))}
                  </>
                )}
              </div>
            </ScrollArea>
          </main>
          </div>
        </>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}
