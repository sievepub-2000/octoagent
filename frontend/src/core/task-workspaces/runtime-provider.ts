import type { TaskAgentRuntimeProvider } from "./types";

export const TASK_RUNTIME_PROVIDER_OPTIONS: TaskAgentRuntimeProvider[] = [
  "langgraph",
];

export function formatTaskRuntimeProvider(
  provider: TaskAgentRuntimeProvider | string | null | undefined,
): string {
  if (provider === "langgraph") {
    return "LangGraph";
  }
  if (typeof provider === "string" && provider.trim().length > 0) {
    return provider;
  }
  return "Pending";
}