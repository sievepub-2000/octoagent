export type WorkflowMode = "task" | "branch" | "group";

export type WorkflowStatus =
  | "draft"
  | "queued"
  | "running"
  | "waiting_retry"
  | "waiting_user"
  | "blocked"
  | "completed"
  | "failed"
  | "cancelled";

export type WorkflowTopTab = "plan" | "graph" | "artifacts";
export type WorkflowConsoleTab = "thinking" | "events" | "terminal";

export type FailurePolicy = {
  maxStepAttempts: number;
  maxNoProgressRounds: number;
  maxTotalSteps: number;
  onFinalFailure: "stop" | "fallback" | "ask_user";
};

export type BrainWorkflowConfig = {
  preferredMode: "plan" | "research" | "quant" | "policy";
  factorCandidates: string[];
  riskLimits: string[];
  memoryHints: string[];
};

export type WorkflowBase = {
  id: string;
  mode: WorkflowMode;
  title: string;
  goal: string;
  expectedOutput: string;
  agents: string[];
  status: WorkflowStatus;
  failurePolicy: FailurePolicy;
  brainConfig: BrainWorkflowConfig;
};

export type WorkflowEvent = {
  id: string;
  kind:
    | "task_started"
    | "task_running"
    | "task_completed"
    | "task_failed"
    | "task_timed_out"
    | "runtime_ready"
    | "runtime_degraded"
    | "fallback_switch"
    | "primary_restored"
    | "runtime_failed"
    | "continuation_loaded"
    | "workflow_resumed"
    | "workflow_continued"
    | "workflow_saved";
  title: string;
  detail?: string;
  createdAt: string;
  level: "info" | "success" | "warning" | "error";
  taskId?: string;
};

export type TaskWorkflow = WorkflowBase & {
  mode: "task";
  route: string[];
};

export type BranchWorkflow = WorkflowBase & {
  mode: "branch";
  branches: Array<{
    id: string;
    agentName: string;
    responsibility: string;
  }>;
};

export type GroupWorkflow = WorkflowBase & {
  mode: "group";
  collaborationStyle: "fast" | "balanced" | "deep_review";
};

export type Workflow = TaskWorkflow | BranchWorkflow | GroupWorkflow;

export const DEFAULT_FAILURE_POLICY: FailurePolicy = {
  maxStepAttempts: 3,
  maxNoProgressRounds: 2,
  maxTotalSteps: 12,
  onFinalFailure: "fallback",
};

const DEFAULT_AGENT_SET = ["lead_agent", "researcher", "coder", "reviewer"];

function createId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function createWorkflowEvent(
  kind: WorkflowEvent["kind"],
  title: string,
  detail?: string,
  level: WorkflowEvent["level"] = "info",
  taskId?: string,
): WorkflowEvent {
  return {
    id: createId("workflow-event"),
    kind,
    title,
    detail,
    createdAt: new Date().toISOString(),
    level,
    taskId,
  };
}

export function createWorkflow(mode: WorkflowMode): Workflow {
  const base: WorkflowBase = {
    id: createId("workflow"),
    mode,
    title:
      mode === "task"
        ? "New Task"
        : mode === "branch"
          ? "New Branch"
          : "New Group",
    goal: "",
    expectedOutput: "",
    agents: DEFAULT_AGENT_SET,
    status: "draft",
    failurePolicy: DEFAULT_FAILURE_POLICY,
    brainConfig: {
      preferredMode:
        mode === "group" ? "policy" : mode === "branch" ? "research" : "quant",
      factorCandidates: [],
      riskLimits: [],
      memoryHints: [],
    },
  };

  if (mode === "task") {
    return {
      ...base,
      mode,
      route: ["lead_agent", "executor", "lead_agent"],
    };
  }

  if (mode === "branch") {
    return {
      ...base,
      mode,
      branches: [
        {
          id: createId("branch"),
          agentName: "researcher",
          responsibility: "Research the problem space",
        },
        {
          id: createId("branch"),
          agentName: "coder",
          responsibility: "Produce a candidate implementation",
        },
      ],
    };
  }

  return {
    ...base,
    mode,
    collaborationStyle: "balanced",
  };
}

export function countWorkflowSteps(workflow: Workflow) {
  if (workflow.mode === "task") {
    return workflow.route.length;
  }
  if (workflow.mode === "branch") {
    return workflow.branches.length + 2;
  }
  return workflow.agents.length + 2;
}

export function buildBrainPlanPayload(workflow: Workflow) {
  return {
    user_goal: workflow.goal,
    constraints: [
      `workflow_mode:${workflow.mode}`,
      `max_total_steps:${workflow.failurePolicy.maxTotalSteps}`,
      `on_final_failure:${workflow.failurePolicy.onFinalFailure}`,
      ...workflow.brainConfig.riskLimits,
    ],
    evidence: workflow.expectedOutput ? [workflow.expectedOutput] : [],
    preferred_mode: workflow.brainConfig.preferredMode,
    factor_candidates: workflow.brainConfig.factorCandidates,
    risk_limits: workflow.brainConfig.riskLimits,
    memory_hints: workflow.brainConfig.memoryHints,
  };
}
