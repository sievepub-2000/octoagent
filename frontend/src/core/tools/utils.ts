import type { ToolCall } from "@langchain/core/messages";
import type { AIMessage } from "@langchain/langgraph-sdk";

import type { Translations } from "../i18n";
import { hasToolCalls } from "../messages/utils";

export function explainLastToolCall(message: AIMessage, t: Translations) {
  if (hasToolCalls(message)) {
    const lastToolCall = message.tool_calls![message.tool_calls!.length - 1]!;
    return explainToolCall(lastToolCall, t);
  }
  return t.common.thinking;
}

export function explainToolCall(toolCall: ToolCall, t: Translations) {
  if (toolCall.name === "web_search" || toolCall.name === "image_search") {
    return t.toolCalls.searchFor(toolCall.args.query);
  } else if (toolCall.name === "web_fetch") {
    return t.toolCalls.viewWebPage;
  } else if (toolCall.name === "present_files") {
    return t.toolCalls.presentFiles;
  } else if (toolCall.name === "write_todos") {
    return t.toolCalls.writeTodos;
  } else if (toolCall.args.description) {
    return toolCall.args.description;
  } else if (
    toolCall.name === "bash" ||
    toolCall.name === "host_shell" ||
    toolCall.name === "glob" ||
    toolCall.name === "grep" ||
    toolCall.name === "lsp"
  ) {
    // Shell-family tools: when no description, show the actual command so the
    // operator can see what is running (host_shell otherwise rendered the
    // generic "Using host_shell" label, hiding the executed command).
    const command =
      (toolCall.args as { command?: string }).command ??
      (toolCall.args as { pattern?: string }).pattern ??
      (toolCall.args as { query?: string }).query;
    if (typeof command === "string" && command.length > 0) {
      return command;
    }
    return t.toolCalls.useTool(toolCall.name);
  } else {
    return t.toolCalls.useTool(toolCall.name);
  }
}
