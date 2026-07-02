import type { AIMessage, Message, StreamMode } from "@langchain/langgraph-sdk";
import type { ThreadsClient } from "@langchain/langgraph-sdk/client";
import { useStream } from "@langchain/langgraph-sdk/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { pushSystemEvent } from "@/core/system-events/store";


import {
  getAPIClient,
  isRecoverableThreadMissingError,
  markThreadPersisted,
  markThreadProvisional,
} from "../api";
import { deleteJSON } from "../api/http";
import { getLangGraphBaseURL } from "../config";
import { useI18n } from "../i18n/hooks";
import type { FileInMessage } from "../messages/utils";
import { buildMlInternThreadContext, resolveMlInternProfile } from "../ml-intern/defaults";
import { planQueryOperation } from "../query-engine/api";
import { getRecursionLimit } from "../runtime-profile";
import { createRunEvent, normalizeRunEvent, type RunEvent } from "../runtime/run-events";
import type { LocalSettings } from "../settings";
import { useUpdateSubtask } from "../tasks/context";
import type { UploadedFileInfo } from "../uploads";
import { uploadFiles } from "../uploads";
import { createWorkflowEvent, useWorkflows } from "../workflows";

import { classifyDialogueRoute, type DialogueRoute } from "./dialogue-routing";
import { SYSTEM_SESSION_CONTINUE_PROMPT } from "./system-prompts";
import type { AgentThread, AgentThreadState } from "./types";

export type ToolEndEvent = {
  name: string;
  data: unknown;
};

export type ThreadStreamOptions = {
  threadId?: string | null | undefined;
  context: LocalSettings["context"];
  isMock?: boolean;
  loadInitialState?: boolean;
  onStart?: (threadId: string) => void;
  onFinish?: (state: AgentThreadState) => void;
  onRunEvent?: (event: RunEvent) => void;
  onToolEnd?: (event: ToolEndEvent) => void;
};

export function normalizeRuntimeMode(
  mode: LocalSettings["context"]["mode"],
  reasoningEffort?: LocalSettings["context"]["reasoning_effort"],
): NonNullable<LocalSettings["context"]["mode"]> {
  if (mode === "pro" && (!reasoningEffort || reasoningEffort === "minimal")) {
    return "flash";
  }
  return mode ?? "flash";
}

export function resolvePermissionMode(
  permissionMode?: LocalSettings["context"]["permission_mode"],
): "approval" | "directory" | "system" {
  if (permissionMode === "directory" || permissionMode === "system") {
    return permissionMode;
  }
  return "approval";
}

export function shouldEnableThinking(mode: NonNullable<LocalSettings["context"]["mode"]>) {
  return mode === "thinking" || mode === "pro" || mode === "ultra";
}

export const DEFAULT_STREAM_MODE: StreamMode[] = ["messages-tuple", "updates", "custom"];
export const MAX_PREPLAN_MESSAGE_CHARS = 16_000;
type AutoContinueSubmit = (
  payload: { messages: Array<Record<string, unknown>> },
  options: Record<string, unknown>,
) => Promise<unknown>;

type ExpectedContextHandoff = {
  threadId: string;
  cycleId: string;
  baseTokens: number;
};

async function fetchThreadStateValues(threadId: string): Promise<AgentThreadState | null> {
  const base = getLangGraphBaseURL();
  const url = `${base}/threads/${encodeURIComponent(threadId)}/state`;
  const response = await fetch(url);
  if (!response.ok) {
    return null;
  }
  const state = await response.json();
  return state.values as AgentThreadState | null;
}

export function contextHandoffMatches(
  state: AgentThreadState | null | undefined,
  expected: ExpectedContextHandoff,
): boolean {
  const runtime = state?.runtime ?? {};
  return (
    runtime.context_cycle_id === expected.cycleId &&
    Number(runtime.context_cycle_base_tokens ?? 0) === expected.baseTokens
  );
}

async function verifyContextHandoffAfterStream(expected: ExpectedContextHandoff): Promise<boolean> {
  for (const delayMs of [0, 250, 750, 1500]) {
    if (delayMs > 0) {
      await new Promise((resolve) => window.setTimeout(resolve, delayMs));
    }
    const values = await fetchThreadStateValues(expected.threadId);
    if (contextHandoffMatches(values, expected)) {
      return true;
    }
  }
  return false;
}

export function messageText(message: Message | undefined): string {
  if (!message) return "";
  if (typeof message.content === "string") return message.content.trim();
  if (!Array.isArray(message.content)) return "";
  return message.content
    .map((part) => {
      if (typeof part === "object" && part !== null && "text" in part && typeof part.text === "string") {
        return part.text;
      }
      return "";
    })
    .join("")
    .trim();
}

function normalizedMessageText(message: Message | undefined): string {
  return messageText(message).replace(/\s+/g, " ").trim();
}

function messageHasFiles(message: Message | undefined): boolean {
  const files = (message?.additional_kwargs as Record<string, unknown> | undefined)?.files;
  return Array.isArray(files) && files.length > 0;
}

export function isDuplicateOptimisticHuman(
  optimistic: Message,
  serverMessages: Message[],
): boolean {
  if (optimistic.type !== "human") {
    return false;
  }
  const optimisticText = normalizedMessageText(optimistic);
  if (!optimisticText) {
    return false;
  }
  const optimisticHasFiles = messageHasFiles(optimistic);
  for (let index = serverMessages.length - 1; index >= Math.max(0, serverMessages.length - 8); index -= 1) {
    const serverMessage = serverMessages[index];
    if (serverMessage?.type !== "human") {
      continue;
    }
    if (normalizedMessageText(serverMessage) !== optimisticText) {
      continue;
    }
    if (optimisticHasFiles && !messageHasFiles(serverMessage)) {
      continue;
    }
    return true;
  }
  return false;
}

export function isUnfinishedActionAnnouncement(message: Message | undefined): boolean {
  if (message?.type !== "ai" || (message.tool_calls?.length ?? 0) > 0) {
    return false;
  }
  const text = messageText(message);
  if (!text) {
    return false;
  }
  if (/<tool_call\b[\s\S]*<\/tool_call>/i.test(text) || /<function=\w[\s\S]*<parameter=/i.test(text)) {
    return true;
  }
  if (text.length > 320) {
    return false;
  }
  const actionPattern = /(现在让我|我来|我将|接下来我会|首先[，,\s]*让我|让我|let me|i(?:'ll| will)|now let me).{0,160}(检查|查看|读取|搜索|运行|分析|确认|排查|探索|inspect|check|look|read|search|run|analy[sz]e|verify|explore)/i;
  if (!actionPattern.test(text)) {
    const resumeOnlyPattern = /(继续|接续|恢复|continue|resume).{0,80}(之前|上一步|这个任务|工作|执行|处理|排查|修复|previous task|prior work)/i;
    if (!resumeOnlyPattern.test(text)) {
      return false;
    }
  }
  if (/[：:]\s*$/.test(text)) {
    return true;
  }
  const completionMarkers = /(已完成|完成了|结论|总结|结果如下|修复完成|验证通过|done|completed|summary|result)/i;
  return !completionMarkers.test(text);
}

export function lastMessage(messages: Message[]): Message | undefined {
  return messages.length > 0 ? messages[messages.length - 1] : undefined;
}

type RecoverableIncompleteDetection = {
  reason: string;
  source: "runtime" | "last_run_record" | "tool_results_without_final";
  isSilentOutput: boolean;
};

function toolCallIds(message: Message | undefined): string[] {
  const record = message as unknown as { tool_calls?: Array<{ id?: unknown }> };
  return (record.tool_calls ?? [])
    .map((call) => (typeof call.id === "string" ? call.id : ""))
    .filter(Boolean);
}

function toolResultId(message: Message | undefined): string {
  if (message?.type !== "tool") return "";
  const record = message as unknown as Record<string, unknown>;
  return typeof record.tool_call_id === "string" ? record.tool_call_id : "";
}

function resolvedToolIdsAfter(messages: Message[], index: number): Set<string> {
  const ids = new Set<string>();
  for (const message of messages.slice(index + 1)) {
    const id = toolResultId(message);
    if (id) ids.add(id);
  }
  return ids;
}

export function detectRecoverableIncompleteState(values: AgentThreadState): RecoverableIncompleteDetection | null {
  const runtimeState = (values.runtime ?? {}) as Record<string, unknown>;
  const recoverableFailure = runtimeState.recoverable_failure as Record<string, unknown> | undefined;
  const incompleteState = runtimeState.incomplete_state as Record<string, unknown> | undefined;
  const lastRunRecord = runtimeState.last_run_record as Record<string, unknown> | undefined;
  const finalEvaluation = lastRunRecord?.final_evaluation as Record<string, unknown> | undefined;
  const runtimeReason =
    (typeof recoverableFailure?.reason === "string" ? recoverableFailure.reason : undefined) ??
    (typeof incompleteState?.reason === "string" ? incompleteState.reason : undefined);
  if (recoverableFailure || incompleteState) {
    const reason = runtimeReason ?? "recoverable_failure";
    return { reason, source: "runtime", isSilentOutput: reason === "assistant produced no user-visible final answer" };
  }
  if (finalEvaluation?.status === "failed" || finalEvaluation?.status === "incomplete") {
    const reason = typeof finalEvaluation.reason === "string" ? finalEvaluation.reason : "recoverable_failure";
    return { reason, source: "last_run_record", isSilentOutput: reason === "assistant produced no user-visible final answer" };
  }

  const messages = values.messages ?? [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message?.type !== "ai") continue;
    const expectedIds = toolCallIds(message);
    if (expectedIds.length === 0) return null;
    const resolvedIds = resolvedToolIdsAfter(messages, index);
    if (expectedIds.every((id) => resolvedIds.has(id))) {
      const rawTaskStatus = runtimeState.task_state_status ?? values.task_state?.status;
      const taskStatus = typeof rawTaskStatus === "string" ? rawTaskStatus : "";
      if (taskStatus !== "completed") {
        return {
          reason: "assistant ended after tool results without final answer",
          source: "tool_results_without_final",
          isSilentOutput: true,
        };
      }
    }
    return null;
  }
  return null;
}
