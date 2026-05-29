export type RunEventKind =
  | "queued"
  | "planning"
  | "tool_call"
  | "tool_result"
  | "workflow"
  | "subagent"
  | "answer_delta"
  | "artifact"
  | "done"
  | "error";

export type RunEventLevel = "info" | "success" | "warning" | "error";

export type RunEvent = {
  id: string;
  kind: RunEventKind;
  title: string;
  detail?: string;
  level: RunEventLevel;
  createdAt: string;
  runId?: string;
  nodeId?: string;
  taskId?: string;
  payload?: Record<string, unknown>;
};

function createId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function createRunEvent(
  kind: RunEventKind,
  title: string,
  detail?: string,
  level: RunEventLevel = "info",
  extras: Partial<Omit<RunEvent, "id" | "kind" | "title" | "detail" | "level" | "createdAt">> = {},
): RunEvent {
  return {
    id: createId("run-event"),
    kind,
    title,
    detail,
    level,
    createdAt: new Date().toISOString(),
    ...extras,
  };
}

export function normalizeRunEvent(event: unknown): RunEvent | null {
  if (typeof event !== "object" || event === null) return null;
  const record = event as Record<string, unknown>;
  if (record.type && record.type !== "run_event") return null;
  const payload = record.type === "run_event" && typeof record.event === "object" && record.event !== null
    ? record.event as Record<string, unknown>
    : record;
  const kind = typeof payload.kind === "string" ? payload.kind : "";
  if (!isRunEventKind(kind)) return null;
  return {
    id: typeof payload.id === "string" ? payload.id : createId("run-event"),
    kind,
    title: typeof payload.title === "string" ? payload.title : labelForRunEventKind(kind),
    detail: typeof payload.detail === "string" ? payload.detail : undefined,
    level: isRunEventLevel(payload.level) ? payload.level : "info",
    createdAt: typeof payload.createdAt === "string"
      ? payload.createdAt
      : typeof payload.created_at === "string"
        ? payload.created_at
        : new Date().toISOString(),
    runId: typeof payload.runId === "string" ? payload.runId : typeof payload.run_id === "string" ? payload.run_id : undefined,
    nodeId: typeof payload.nodeId === "string" ? payload.nodeId : typeof payload.node_id === "string" ? payload.node_id : undefined,
    taskId: typeof payload.taskId === "string" ? payload.taskId : typeof payload.task_id === "string" ? payload.task_id : undefined,
    payload: typeof payload.payload === "object" && payload.payload !== null ? payload.payload as Record<string, unknown> : undefined,
  };
}

export function normalizeRunEvents(events: unknown): RunEvent[] {
  if (!Array.isArray(events)) return [];
  return events
    .map((event) => normalizeRunEvent(event))
    .filter((event): event is RunEvent => event !== null);
}

export function mergeRunEvents(incoming: RunEvent[], existing: RunEvent[], limit = 120): RunEvent[] {
  const seen = new Set<string>();
  const merged: RunEvent[] = [];
  for (const event of [...incoming, ...existing]) {
    const key = [
      event.id,
      event.kind,
      event.taskId ?? "",
      event.title,
      event.detail ?? "",
    ].join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(event);
  }
  return merged.slice(0, limit);
}

export function labelForRunEventKind(kind: RunEventKind) {
  switch (kind) {
    case "queued":
      return "Queued";
    case "planning":
      return "Planning";
    case "tool_call":
      return "Calling tool";
    case "tool_result":
      return "Tool finished";
    case "workflow":
      return "Workflow";
    case "subagent":
      return "Subagent";
    case "answer_delta":
      return "Writing";
    case "artifact":
      return "Artifact";
    case "done":
      return "Done";
    case "error":
      return "Error";
  }
}

export function latestRunEvent(events: RunEvent[]) {
  return events.length > 0 ? events[0] : null;
}

function isRunEventKind(value: string): value is RunEventKind {
  return [
    "queued",
    "planning",
    "tool_call",
    "tool_result",
    "workflow",
    "subagent",
    "answer_delta",
    "artifact",
    "done",
    "error",
  ].includes(value);
}

function isRunEventLevel(value: unknown): value is RunEventLevel {
  return value === "info" || value === "success" || value === "warning" || value === "error";
}
