import type { AgentThreadContext, AgentThreadState, ContinuationContract } from "./types";
import { textOfMessage } from "./utils";

export const CONTINUATION_RECENT_EXCHANGE_LIMIT = 3;
const CONTINUATION_RECENT_MESSAGE_LIMIT =
  CONTINUATION_RECENT_EXCHANGE_LIMIT * 2;

type ContinuationContext = Pick<
  AgentThreadContext,
  | "continue_trigger"
  | "continue_from_thread_id"
  | "continue_from_title"
  | "continue_message_count"
  | "continue_recent_messages"
  | "continue_memory_summary"
  | "continue_todos"
  | "continue_task_state"
  | "continue_contract"
>;

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
}

function fallbackObjective(state: AgentThreadState): string | undefined {
  for (const message of [...(state.messages ?? [])].reverse()) {
    if (message.type !== "human") continue;
    const content = (textOfMessage(message) ?? "").trim();
    if (content.length < 12 || /^(continue\b|go on\b|继续执行上一段|继续当前任务)/i.test(content)) continue;
    return content;
  }
  return stringValue(state.title);
}

function buildContract(sourceThreadId: string, sourceState: AgentThreadState): ContinuationContract {
  const taskState = sourceState.task_state ?? {};
  const pendingSteps = stringList(taskState.pending_steps);
  const pendingTodos = (sourceState.todos ?? [])
    .filter((todo) => todo.status === "pending" || todo.status === "in_progress")
    .map((todo) => todo.content)
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0);
  const messages = sourceState.messages ?? [];

  return {
    version: 2,
    objective: stringValue(taskState.goal) ?? fallbackObjective(sourceState) ?? "",
    status: stringValue(taskState.status) ?? "active",
    current_phase: stringValue(taskState.current_step),
    next_action: stringValue(taskState.next_action) ?? pendingSteps[0] ?? pendingTodos[0],
    constraints: stringList(taskState.constraints),
    forbidden_actions: stringList(taskState.forbidden_actions),
    acceptance_criteria: stringList(taskState.acceptance_criteria),
    confirmed_decisions: stringList(taskState.confirmed_decisions),
    completed_steps: stringList(taskState.completed_steps),
    pending_steps: pendingSteps.length > 0 ? pendingSteps : pendingTodos,
    blockers: stringList(taskState.blockers),
    evidence: stringList(taskState.evidence),
    artifacts: sourceState.artifacts ?? [],
    permission_scope: stringValue(taskState.permission_scope),
    source_thread_id: sourceThreadId,
    source_title: stringValue(sourceState.title),
    source_message_ids: messages
      .slice(-CONTINUATION_RECENT_MESSAGE_LIMIT)
      .map((message) => stringValue(message.id))
      .filter((id): id is string => Boolean(id)),
  };
}

export function buildContinuationContext(
  sourceThreadId: string | null | undefined,
  sourceState: AgentThreadState | null | undefined,
): ContinuationContext | undefined {
  if (!sourceThreadId || !sourceState) {
    return undefined;
  }

  const recentMessages = (sourceState.messages ?? [])
    .filter((message) => message.type === "human" || message.type === "ai")
    .slice(-CONTINUATION_RECENT_MESSAGE_LIMIT)
    .map((message) => ({
      role: message.type,
      content: textOfMessage(message) ?? "",
    }))
    .filter((message) => message.content.trim().length > 0);
  const runtime = sourceState.runtime ?? {};
  const memorySummaryParts = [
    runtime.compaction_summary,
    runtime.instruction_focus_summary,
  ].filter((item): item is string => typeof item === "string" && item.trim().length > 0);

  return {
    continue_trigger: "continue",
    continue_from_thread_id: sourceThreadId,
    continue_from_title: sourceState.title,
    continue_message_count: sourceState.messages?.length ?? 0,
    continue_recent_messages: recentMessages,
    continue_memory_summary:
      memorySummaryParts.length > 0 ? memorySummaryParts.join("\n\n") : undefined,
    continue_todos: sourceState.todos ?? [],
    continue_task_state: sourceState.task_state ?? null,
    continue_contract: buildContract(sourceThreadId, sourceState),
  };
}
