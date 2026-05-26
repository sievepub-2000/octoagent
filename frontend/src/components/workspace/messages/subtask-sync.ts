import type { Message } from "@langchain/langgraph-sdk";

import { extractTextFromMessage } from "@/core/messages/utils";
import type { Subtask } from "@/core/tasks";

type ToolCallLike = {
  id?: string;
  name?: string;
  args?: Record<string, unknown>;
};

type MessageWithToolCalls = Message & {
  tool_calls?: ToolCallLike[];
};

type ToolMessageWithCallId = Message & {
  tool_call_id?: string;
};

function isTaskToolCall(toolCall: ToolCallLike): toolCall is ToolCallLike & {
  id: string;
  args: {
    subagent_type?: string;
    description?: string;
    prompt?: string;
  };
} {
  return (
    toolCall.name === "task" &&
    typeof toolCall.id === "string" &&
    toolCall.args != null
  );
}

export function getTaskToolCallIds(message: Message): string[] {
  if (message.type !== "ai") {
    return [];
  }
  return ((message as MessageWithToolCalls).tool_calls ?? [])
    .filter(isTaskToolCall)
    .map((toolCall) => toolCall.id);
}

export function collectSubtaskUpdates(messages: Message[]) {
  const updates: Array<Partial<Subtask> & { id: string }> = [];
  const taskToolCallIds = new Set<string>();

  for (const message of messages) {
    if (message.type === "ai") {
      for (const toolCall of (message as MessageWithToolCalls).tool_calls ?? []) {
        if (!isTaskToolCall(toolCall)) {
          continue;
        }
        taskToolCallIds.add(toolCall.id);
        updates.push({
          id: toolCall.id,
          subagent_type: toolCall.args.subagent_type ?? "",
          description: toolCall.args.description ?? "",
          prompt: toolCall.args.prompt ?? "",
          status: "in_progress",
        });
      }
      continue;
    }

    if (message.type !== "tool") {
      continue;
    }

    const taskId =
      typeof (message as ToolMessageWithCallId).tool_call_id === "string"
        ? (message as ToolMessageWithCallId).tool_call_id
        : null;
    if (!taskId || !taskToolCallIds.has(taskId)) {
      continue;
    }

    const result = extractTextFromMessage(message);
    if (result.startsWith("Task Succeeded. Result:")) {
      updates.push({
        id: taskId,
        status: "completed",
        result: result.split("Task Succeeded. Result:")[1]?.trim(),
      });
    } else if (result.startsWith("Task failed.")) {
      updates.push({
        id: taskId,
        status: "failed",
        error: result.split("Task failed.")[1]?.trim(),
      });
    } else if (result.startsWith("Task timed out")) {
      updates.push({
        id: taskId,
        status: "failed",
        error: result,
      });
    } else {
      updates.push({
        id: taskId,
        status: "in_progress",
      });
    }
  }

  return updates;
}
