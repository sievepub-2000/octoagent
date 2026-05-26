import type { AgentThreadContext, AgentThreadState } from "./types";
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
  | "continue_workflows"
>;

export function buildContinuationContext(
  sourceThreadId: string | null | undefined,
  sourceState: AgentThreadState | null | undefined,
): ContinuationContext | undefined {
  if (!sourceThreadId || !sourceState) {
    return undefined;
  }

  const recentMessages = (sourceState.messages ?? [])
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
    runtime.memory_write
      ? JSON.stringify(runtime.memory_write)
      : null,
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
    continue_workflows: sourceState.workflows ?? [],
  };
}
