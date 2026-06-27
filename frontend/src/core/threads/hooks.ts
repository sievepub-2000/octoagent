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

function normalizeRuntimeMode(
  mode: LocalSettings["context"]["mode"],
  reasoningEffort?: LocalSettings["context"]["reasoning_effort"],
): NonNullable<LocalSettings["context"]["mode"]> {
  if (mode === "pro" && (!reasoningEffort || reasoningEffort === "minimal")) {
    return "flash";
  }
  return mode ?? "flash";
}

function resolvePermissionMode(
  permissionMode?: LocalSettings["context"]["permission_mode"],
): "approval" | "directory" | "system" {
  if (permissionMode === "directory" || permissionMode === "system") {
    return permissionMode;
  }
  return "approval";
}

function shouldEnableThinking(mode: NonNullable<LocalSettings["context"]["mode"]>) {
  return mode === "thinking" || mode === "pro" || mode === "ultra";
}

const DEFAULT_STREAM_MODE: StreamMode[] = ["messages-tuple", "updates", "custom"];
const MAX_PREPLAN_MESSAGE_CHARS = 16_000;
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

function contextHandoffMatches(
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

function messageText(message: Message | undefined): string {
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
    .join("\n")
    .trim();
}

function normalizedMessageText(message: Message | undefined): string {
  return messageText(message).replace(/\s+/g, " ").trim();
}

function messageHasFiles(message: Message | undefined): boolean {
  const files = (message?.additional_kwargs as Record<string, unknown> | undefined)?.files;
  return Array.isArray(files) && files.length > 0;
}

function isDuplicateOptimisticHuman(
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

function isUnfinishedActionAnnouncement(message: Message | undefined): boolean {
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

function lastMessage(messages: Message[]): Message | undefined {
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

function detectRecoverableIncompleteState(values: AgentThreadState): RecoverableIncompleteDetection | null {
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

export function useThreadStream({
  threadId,
  context,
  isMock,
  loadInitialState = true,
  onStart,
  onFinish,
  onRunEvent,
  onToolEnd,
}: ThreadStreamOptions) {
  const { t } = useI18n();
  // Track the thread ID that is currently streaming to handle thread changes during streaming
  const [onStreamThreadId, setOnStreamThreadId] = useState(() => threadId);
  // Ref to track current thread ID across async callbacks without causing re-renders,
  // and to allow access to the current thread id in onUpdateEvent
  const threadIdRef = useRef<string | null>(threadId ?? null);
  const startedRef = useRef(false);
  const autoContinueRef = useRef<Set<string>>(new Set());
  // Track how many times we auto-continued from a recoverable/incomplete state
  // (silent output, continuation announcement, tool-failure rollup, ...) within
  // the current thread. Capped at _MAX_INCOMPLETE_RETRIES across the whole thread
  // to prevent infinite cross-turn loops when the model is stuck.
  const incompleteRetryRef = useRef<number>(0);
  const _MAX_INCOMPLETE_RETRIES = 5;
  const autoContinueSubmitRef = useRef<AutoContinueSubmit | null>(null);
  const expectedContextHandoffRef = useRef<ExpectedContextHandoff | null>(null);

  const listeners = useRef({
    onStart,
    onFinish,
    onRunEvent,
    onToolEnd,
  });

  // Keep listeners ref updated with latest callbacks
  useEffect(() => {
    listeners.current = { onStart, onFinish, onRunEvent, onToolEnd };
  }, [onStart, onFinish, onRunEvent, onToolEnd]);

  useEffect(() => {
    const normalizedThreadId = threadId ?? null;
    threadIdRef.current = normalizedThreadId;
    autoContinueRef.current.clear();
    incompleteRetryRef.current = 0;
    if (!normalizedThreadId) {
      // Just reset for new thread creation when threadId becomes null/undefined
      startedRef.current = false;
    } else if (loadInitialState) {
      markThreadPersisted(normalizedThreadId);
    } else {
      markThreadProvisional(normalizedThreadId);
    }
    setOnStreamThreadId((currentThreadId) =>
      currentThreadId === normalizedThreadId ? currentThreadId : normalizedThreadId,
    );
  }, [loadInitialState, threadId]);

  const _handleOnStart = useCallback((id: string) => {
    if (!startedRef.current) {
      listeners.current.onStart?.(id);
      startedRef.current = true;
    }
  }, []);

  const handleStreamStart = useCallback(
    (_threadId: string) => {
      threadIdRef.current = _threadId;
      markThreadPersisted(_threadId);
      _handleOnStart(_threadId);
    },
    [_handleOnStart],
  );

  const queryClient = useQueryClient();
  const updateSubtask = useUpdateSubtask();
  const { appendEvent } = useWorkflows();

  const thread = useStream<AgentThreadState>({
    client: getAPIClient(isMock),
    assistantId: "lead_agent",
    // Always pass the concrete threadId so that the SDK's internal
    // submit() knows the thread already exists and won't attempt to
    // re-create it (which would fail with 409 after the pre-create in
    // sendMessage).  For new threads the thread doesn't exist in
    // LangGraph yet, but getHistory / getState are patched in
    // api-client.ts to return empty results on 404.
    threadId: onStreamThreadId ?? undefined,
    reconnectOnMount: loadInitialState,
    // The LangGraph SDK throws if any consumer touches `thread.history`
    // while fetchStateHistory is disabled. Keep history enabled for fresh
    // threads, but only bind/reconnect to an existing thread when requested.
    fetchStateHistory:
      loadInitialState && onStreamThreadId ? { limit: 1 } : true,
    onError(error) {
      // When reconnecting to a thread that no longer exists in LangGraph
      // (e.g. after server restart), log and swallow the 404 instead of
      // showing a runtime error overlay.
      if (isRecoverableThreadMissingError(error)) {
        console.warn(
          `[useThreadStream] Thread ${onStreamThreadId} no longer exists — treating as new conversation.`,
        );
        return;
      }
      // GraphRecursionError safety net: when LangGraph hits its recursion
      // limit (e.g. a stale browser cache submitted a low recursion_limit),
      // the exception propagates out before any middleware after_agent hook
      // can flag `recoverable_failure`, so the auto-continue path in
      // onFinish never fires. Detect the error here and trigger the same
      // continuation so the user's task does not stop without reason.
      const rawMessage = typeof error === "object" && error !== null && "message" in error
        ? (error as { message?: unknown }).message
        : error;
      const errMsg = typeof rawMessage === "string" ? rawMessage : "";
      if (/UserInterrupt/i.test(errMsg)) {
        // Historical interrupted runs are expected after a restart or manual
        // stop. Treat them as a settled history view instead of surfacing a
        // scary runtime error in the chat/timeline.
        return;
      }
      if (/Recursion limit of \d+ reached/i.test(errMsg) || /GraphRecursionError/i.test(errMsg)) {
        const currentThreadId = threadIdRef.current;
        const submit = autoContinueSubmitRef.current;
        const signature = `${currentThreadId ?? ""}:graph-recursion-error`;
        if (currentThreadId && submit && !autoContinueRef.current.has(signature)) {
          autoContinueRef.current.add(signature);
          pushSystemEvent({
            level: "warning",
            message: t.threadEvents.recursionLimit,
            source: "auto-continue",
          });
          void submit(
            {
              messages: [
                {
                  type: "system" as const,
                  content: SYSTEM_SESSION_CONTINUE_PROMPT,
                },
              ],
            },
            {
              threadId: currentThreadId,
              streamSubgraphs: true,
              streamResumable: true,
              streamMode: DEFAULT_STREAM_MODE,
              multitaskStrategy: "interrupt" as const,
              config: {
                // Force the safe ceiling for the recovery run, ignoring any
                // potentially stale getRecursionLimit() value in the browser.
                recursion_limit: 1_000_000,
              },
              context: {
                ...context,
                thread_id: currentThreadId,
                system_continue_reason: "graph_recursion_limit_reached",
              },
            },
          ).catch((err) => {
            console.error("Failed to auto-continue after GraphRecursionError:", err);
          });
          return;
        }
      }
      console.error("[useThreadStream] Stream error:", error);
    },
    onCreated(meta) {
      handleStreamStart(meta.thread_id);
      setOnStreamThreadId(meta.thread_id);
    },
    onLangChainEvent(event) {
      if (event.event === "on_tool_start") {
        listeners.current.onRunEvent?.(
          createRunEvent(
            "tool_call",
            event.name ? `Calling ${event.name}` : "Calling tool",
            undefined,
            "info",
          ),
        );
      }
      if (event.event === "on_tool_end") {
        listeners.current.onToolEnd?.({
          name: event.name,
          data: event.data,
        });
        listeners.current.onRunEvent?.(
          createRunEvent(
            "tool_result",
            event.name ? `${event.name} finished` : "Tool finished",
            undefined,
            "success",
          ),
        );
      }
    },
    onUpdateEvent(data) {
      const updates: Array<Partial<AgentThreadState> | null> = Object.values(
        data || {},
      );
      for (const update of updates) {
        if (update && "title" in update && update.title) {
          void queryClient.setQueriesData(
            {
              queryKey: ["threads", "search"],
              exact: false,
            },
            (oldData: Array<AgentThread> | undefined) => {
              return oldData?.map((t) => {
                if (t.thread_id === threadIdRef.current) {
                  return {
                    ...t,
                    values: {
                      ...t.values,
                      title: update.title,
                    },
                  };
                }
                return t;
              });
            },
          );
        }
      }
    },
    onCustomEvent(event: unknown) {
      const runEvent = normalizeRunEvent(event);
      if (runEvent) {
        listeners.current.onRunEvent?.(runEvent);
        return;
      }
      if (typeof event === "object" && event !== null && "type" in event) {
        const eventType = event.type;
        if (eventType === "task_running") {
          const e = event as {
            type: "task_running";
            task_id: string;
            message: AIMessage;
          };
          updateSubtask({ id: e.task_id, latestMessage: e.message });
          appendEvent(
            createWorkflowEvent(
              "task_running",
              "Subagent still running",
              "The delegated task is producing new messages.",
              "info",
              e.task_id,
            ),
          );
          listeners.current.onRunEvent?.(
            createRunEvent(
              "subagent",
              "Subagent still running",
              "The delegated task is producing new messages.",
              "info",
              { taskId: e.task_id },
            ),
          );
        } else if (eventType === "task_started") {
          const e = event as {
            type: "task_started";
            task_id: string;
            description?: string;
          };
          appendEvent(
            createWorkflowEvent(
              "task_started",
              e.description ?? "Subagent task started",
              "Runtime checkpoint created.",
              "info",
              e.task_id,
            ),
          );
          listeners.current.onRunEvent?.(
            createRunEvent(
              "subagent",
              e.description ?? "Subagent task started",
              "Runtime checkpoint created.",
              "info",
              { taskId: e.task_id },
            ),
          );
        } else if (eventType === "task_completed") {
          const e = event as {
            type: "task_completed";
            task_id: string;
            result?: string;
          };
          appendEvent(
            createWorkflowEvent(
              "task_completed",
              "Subagent task completed",
              e.result,
              "success",
              e.task_id,
            ),
          );
          listeners.current.onRunEvent?.(
            createRunEvent(
              "subagent",
              "Subagent task completed",
              e.result,
              "success",
              { taskId: e.task_id },
            ),
          );
        } else if (eventType === "task_failed") {
          const e = event as {
            type: "task_failed";
            task_id: string;
            error?: string;
          };
          appendEvent(
            createWorkflowEvent(
              "task_failed",
              "Subagent task failed",
              e.error,
              "error",
              e.task_id,
            ),
          );
          listeners.current.onRunEvent?.(
            createRunEvent(
              "error",
              "Subagent task failed",
              e.error,
              "error",
              { taskId: e.task_id },
            ),
          );
        } else if (eventType === "task_timed_out") {
          const e = event as {
            type: "task_timed_out";
            task_id: string;
            error?: string;
          };
          appendEvent(
            createWorkflowEvent(
              "task_timed_out",
              "Subagent task timed out",
              e.error,
              "warning",
              e.task_id,
            ),
          );
          listeners.current.onRunEvent?.(
            createRunEvent(
              "error",
              "Subagent task timed out",
              e.error,
              "warning",
              { taskId: e.task_id },
            ),
          );
        }
      }
    },
    onFinish(state) {
      const values = state.values;
      const expectedHandoff = expectedContextHandoffRef.current;
      if (expectedHandoff) {
        if (contextHandoffMatches(values, expectedHandoff)) {
          expectedContextHandoffRef.current = null;
        } else {
          void verifyContextHandoffAfterStream(expectedHandoff).then((matched) => {
            if (expectedContextHandoffRef.current?.cycleId !== expectedHandoff.cycleId) {
              return;
            }
            if (matched) {
              expectedContextHandoffRef.current = null;
              return;
            }
            console.warn("Context handoff verification did not observe persisted runtime state", {
              expected: expectedHandoff,
            });
            pushSystemEvent({ level: "warning", message: t.threadEvents.contextHandoffSubmitted, source: "context-handoff" });
          });
        }
      }
      const last = lastMessage(values.messages ?? []);
      const runtimeState = (values.runtime ?? {}) as Record<string, unknown>;
      const incompleteRecovery = detectRecoverableIncompleteState(values);
      if (!isMock && isUnfinishedActionAnnouncement(last)) {
        const currentThreadId = threadIdRef.current;
        const signature = `${currentThreadId ?? ""}:${last?.id ?? ""}:${messageText(last)}`;
        const submit = autoContinueSubmitRef.current;
        if (currentThreadId && submit && !autoContinueRef.current.has(signature)) {
          autoContinueRef.current.add(signature);
          pushSystemEvent({ level: "info", message: t.threadEvents.autoContinueAction, source: "auto-continue" });
          void submit(
            {
              messages: [
                {
                  type: "system" as const,
                  content: SYSTEM_SESSION_CONTINUE_PROMPT,
                },
              ],
            },
            {
              threadId: currentThreadId,
              streamSubgraphs: true,
              streamResumable: true,
              streamMode: DEFAULT_STREAM_MODE,
              multitaskStrategy: "interrupt" as const,
              config: {
                recursion_limit: getRecursionLimit(),
              },
              context: {
                ...context,
                thread_id: currentThreadId,
                system_continue_reason: "assistant_final_message_ended_with_unfinished_action_announcement",
              },
            },
          ).catch((error) => {
            console.error("Failed to auto-continue unfinished assistant action:", error);
            listeners.current.onFinish?.(values);
          });
          return;
        }
      }
      // Context handoff: when compaction was insufficient, signal page.tsx
      // to create a new thread with continuation context
      const contextHandoffRequired = runtimeState.context_handoff_required;
      if (!isMock && contextHandoffRequired) {
        const currentThreadId = threadIdRef.current;
        pushSystemEvent({
          level: "info",
          message: t.threadEvents.contextLimitHandoff,
          source: "context-handoff",
        });
        // Signal the page component via onFinish with handoff metadata.
        // page.tsx will read this and navigate to a new thread.
        const handoffValues = {
          ...values,
          _context_handoff: {
            required: true,
            source_thread_id: currentThreadId,
            reason: runtimeState.context_handoff_reason ?? "context_exceeded",
          },
        };
        listeners.current.onFinish?.(handoffValues);
        void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
        return;
      }
      if (!isMock && incompleteRecovery) {
        const currentThreadId = threadIdRef.current;
        const reason = incompleteRecovery.reason;
        // Include message count in the signature so a fresh attempt after a prior
        // recovery also resulting in an incomplete state gets a different signature
        // and triggers another retry. incompleteRetryRef caps total cross-turn
        // retries at _MAX_INCOMPLETE_RETRIES.
        const msgCount = (values.messages ?? []).length;
        const isSilentOutput = incompleteRecovery.isSilentOutput;
        const signature = `${currentThreadId ?? ""}:recoverable:${incompleteRecovery.source}:${reason}:msgs${msgCount}`;
        const submit = autoContinueSubmitRef.current;
        const retryAllowed = incompleteRetryRef.current < _MAX_INCOMPLETE_RETRIES;
        if (currentThreadId && submit && retryAllowed && !autoContinueRef.current.has(signature)) {
          autoContinueRef.current.add(signature);
          incompleteRetryRef.current += 1;
          const attemptNo = incompleteRetryRef.current;
          pushSystemEvent({
            level: "info",
            message:
              attemptNo > 1
                ? `检测到可恢复的未完成任务（${reason}），正在第 ${attemptNo} 次自动继续（最多 ${_MAX_INCOMPLETE_RETRIES} 次）。`
                : t.threadEvents.incompleteRetry,
            source: "auto-continue",
          });
          void submit(
            {
              messages: [
                {
                  type: "system" as const,
                  content: SYSTEM_SESSION_CONTINUE_PROMPT,
                },
              ],
            },
            {
              threadId: currentThreadId,
              streamSubgraphs: true,
              streamResumable: true,
              streamMode: DEFAULT_STREAM_MODE,
              multitaskStrategy: "interrupt" as const,
              config: {
                recursion_limit: getRecursionLimit(),
              },
              context: {
                ...context,
                thread_id: currentThreadId,
                system_continue_reason: incompleteRecovery.source === "tool_results_without_final"
                  ? "tool_results_without_final_recovery"
                  : isSilentOutput
                    ? "silent_output_recovery"
                    : "recoverable_failure_or_incomplete_state",
              },
            },
          ).catch((error) => {
            console.error("Failed to auto-continue recoverable incomplete task:", error);
            listeners.current.onFinish?.(values);
          });
          return;
        }
      }
      listeners.current.onFinish?.(values);
      void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
    },
  });
  autoContinueSubmitRef.current = thread.submit as unknown as AutoContinueSubmit;

  useEffect(() => {
    if (isMock || thread.isLoading) {
      return;
    }
    const recovery = detectRecoverableIncompleteState(thread.values);
    if (!recovery) {
      return;
    }
    const currentThreadId = threadIdRef.current;
    const submit = autoContinueSubmitRef.current;
    const retryAllowed = incompleteRetryRef.current < _MAX_INCOMPLETE_RETRIES;
    const msgCount = (thread.messages ?? []).length;
    const signature = `${currentThreadId ?? ""}:loaded-recoverable:${recovery.source}:${recovery.reason}:msgs${msgCount}`;
    if (!currentThreadId || !submit || !retryAllowed || autoContinueRef.current.has(signature)) {
      return;
    }
    autoContinueRef.current.add(signature);
    incompleteRetryRef.current += 1;
    pushSystemEvent({
      level: "warning",
      message: `检测到上一轮停在工具结果之后但没有最终回复（${recovery.reason}），正在自动接续。`,
      source: "auto-continue",
    });
    void submit(
      {
        messages: [
          {
            type: "system" as const,
            content: SYSTEM_SESSION_CONTINUE_PROMPT,
          },
        ],
      },
      {
        threadId: currentThreadId,
        streamSubgraphs: true,
        streamResumable: true,
        streamMode: DEFAULT_STREAM_MODE,
        multitaskStrategy: "interrupt" as const,
        config: {
          recursion_limit: getRecursionLimit(),
        },
        context: {
          ...context,
          thread_id: currentThreadId,
          system_continue_reason: recovery.source === "tool_results_without_final"
            ? "tool_results_without_final_recovery"
            : recovery.isSilentOutput
              ? "silent_output_recovery"
              : "recoverable_failure_or_incomplete_state",
        },
      },
    ).catch((error) => {
      console.error("Failed to auto-continue loaded recoverable incomplete task:", error);
    });
  }, [context, isMock, thread.isLoading, thread.messages, thread.values]);

  // Optimistic messages shown before the server stream responds
  const [optimisticMessages, setOptimisticMessages] = useState<Message[]>([]);
  // Track message count before sending so we know when server has responded
  const prevMsgCountRef = useRef(thread.messages.length);
  // Long-running monitor: after 30s without a stream update, keep checking
  // the server-side thread state instead of cancelling the run.
  const watchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const monitorIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const clearWatchdog = useCallback(() => {
    if (watchdogRef.current) {
      clearTimeout(watchdogRef.current);
      watchdogRef.current = null;
    }
    if (monitorIntervalRef.current) {
      clearInterval(monitorIntervalRef.current);
      monitorIntervalRef.current = null;
    }
  }, []);

  // Clear optimistic when server messages arrive (count increases)
  useEffect(() => {
    if (
      optimisticMessages.length > 0 &&
      thread.messages.length > prevMsgCountRef.current
    ) {
      clearWatchdog();
      setOptimisticMessages([]);
    }
  }, [thread.messages.length, optimisticMessages.length, clearWatchdog]);

  // Cleanup any pending watchdog on unmount.
  useEffect(() => () => clearWatchdog(), [clearWatchdog]);

  useEffect(() => {
    if (!thread.isLoading) {
      clearWatchdog();
    }
  }, [thread.isLoading, clearWatchdog]);

  const sendMessage = useCallback(
    async (
      threadId: string,
      message: PromptInputMessage,
      extraContext?: Record<string, unknown>,
    ) => {
      listeners.current.onRunEvent?.(
        createRunEvent("queued", "Queued", "Preparing the run envelope."),
      );
      const text = message.text.trim();
      const nextHandoffCycleId = typeof extraContext?.continue_cycle_id === "string" ? extraContext.continue_cycle_id : "";
      const nextHandoffBaseTokens = Number(extraContext?.continue_cycle_base_tokens ?? 0);
      expectedContextHandoffRef.current = nextHandoffCycleId && threadId && !isMock
        ? { threadId, cycleId: nextHandoffCycleId, baseTokens: nextHandoffBaseTokens }
        : null;

      // Capture current count before showing optimistic messages
      prevMsgCountRef.current = thread.messages.length;

      // Build optimistic files list with uploading status
      const optimisticFiles: FileInMessage[] = (message.files ?? []).map(
        (f) => ({
          filename: f.filename ?? "",
          size: 0,
          status: "uploading" as const,
        }),
      );

      // Create optimistic human message (shown immediately)
      const optimisticHumanMsg: Message = {
        type: "human",
        id: `opt-human-${Date.now()}`,
        content: text ? [{ type: "text", text }] : "",
        additional_kwargs:
          optimisticFiles.length > 0 ? { files: optimisticFiles } : {},
      };

      const newOptimistic: Message[] = [optimisticHumanMsg];
      if (optimisticFiles.length > 0) {
        // Mock AI message while files are being uploaded
        newOptimistic.push({
          type: "ai",
          id: `opt-ai-${Date.now()}`,
          content: t.uploads.uploadingFiles,
          additional_kwargs: { element: "task" },
        });
      }
      setOptimisticMessages(newOptimistic);

      // Arm a 30s health check. Slow agent tasks should be observed and
      // refreshed, not killed from the browser.
      clearWatchdog();
      watchdogRef.current = setTimeout(() => {
        watchdogRef.current = null;
        pushSystemEvent({ level: "info", message: t.threadEvents.watchdogLongRun, source: "watchdog" });
        const pollThreadState = () => {
          const base = getLangGraphBaseURL();
          void fetch(`${base}/threads/${encodeURIComponent(threadId)}/state`).catch(() => undefined);
          void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
          void queryClient.invalidateQueries({ queryKey: ["threads", "state", threadId] });
        };
        pollThreadState();
        monitorIntervalRef.current = setInterval(pollThreadState, 30_000);
      }, 90_000);

      // Pre-create the thread if it doesn't exist yet.  This allows us to
      // always pass a concrete threadId to useStream (avoiding the
      // undefined→uuid transition that triggers SDK stream.clear()).
      // A 409 "already exists" is expected for existing threads.
      const threadMetadata: Record<string, unknown> = {};
      if (extraContext?.agent_name || context.agent_name) {
        threadMetadata.agent_name = extraContext?.agent_name ?? context.agent_name;
      }
      await getAPIClient()
        .threads.create({
          threadId,
          metadata: Object.keys(threadMetadata).length > 0 ? threadMetadata : undefined,
        })
        .catch(() => undefined);
      markThreadPersisted(threadId);

      // NOTE: _handleOnStart(threadId) is intentionally deferred until just
      // before thread.submit() fires (after any file uploads complete).
      // Calling it here used to fire activateThreadRoute() — which calls
      // history.replaceState() to strip ?fresh=1&draft=... — while uploads
      // were still in flight.  That URL change cascaded into Next.js
      // useSearchParams re-renders → useThreadChat setIsNewThread(false) →
      // page-level state churn while thread.submit was preparing, which
      // could orphan the request so /runs/stream was never POSTed at all
      // (observed via nginx logs: threads.create + /uploads succeed, but
      // no /runs/stream → user perceives the chat as silently reset).
      // Deferring to post-upload removes the race entirely.

      let uploadedFileInfo: UploadedFileInfo[] = [];
      let operationPlan: Awaited<ReturnType<typeof planQueryOperation>> | null = null;
      const effectiveMode = normalizeRuntimeMode(context.mode, context.reasoning_effort);
      const dialogueRoute = classifyDialogueRoute({
        text,
        mode: effectiveMode,
        hasFiles: Boolean(message.files?.length),
      });

      try {
        if (text) {
          try {
            const needsClientOperationPlan = dialogueRoute.kind === "tool_action" || dialogueRoute.needsDeepAgent;
            if (needsClientOperationPlan && text.length <= MAX_PREPLAN_MESSAGE_CHARS) {
              listeners.current.onRunEvent?.(
                createRunEvent("planning", "Planning", "Selecting the execution route."),
              );
              operationPlan = await planQueryOperation({
                user_message: text,
                continuation_source:
                  typeof extraContext?.continue_from_title === "string"
                    ? extraContext.continue_from_title
                    : typeof extraContext?.continue_from_thread_id === "string"
                      ? extraContext.continue_from_thread_id
                      : undefined,
                permission_mode: resolvePermissionMode(context.permission_mode),
              });
            } else if (needsClientOperationPlan) {
              console.info(
                `[octoagent] Skipping query pre-plan for ${text.length} character message; submitting directly to context-managed chat runtime.`,
              );
            }
          } catch (error) {
            console.warn("Failed to pre-plan query operation; falling back to raw thread submit.", error);
          }
        }

        // Upload files first if any
        if (message.files && message.files.length > 0) {
          try {
            // Convert FileUIPart to File objects by fetching blob URLs
            const filePromises = message.files.map(async (fileUIPart) => {
              if (fileUIPart.url && fileUIPart.filename) {
                try {
                  // Fetch the blob URL to get the file data
                  const response = await fetch(fileUIPart.url);
                  const blob = await response.blob();

                  // Create a File object from the blob
                  return new File([blob], fileUIPart.filename, {
                    type: fileUIPart.mediaType || blob.type,
                  });
                } catch (error) {
                  console.error(
                    `Failed to fetch file ${fileUIPart.filename}:`,
                    error,
                  );
                  return null;
                }
              }
              return null;
            });

            const conversionResults = await Promise.all(filePromises);
            const files = conversionResults.filter(
              (file): file is File => file !== null,
            );
            const failedConversions = conversionResults.length - files.length;

            if (failedConversions > 0) {
              throw new Error(
                `Failed to prepare ${failedConversions} attachment(s) for upload. Please retry.`,
              );
            }

            if (!threadId) {
              throw new Error("Thread is not ready for file upload.");
            }

            if (files.length > 0) {
              const uploadResponse = await uploadFiles(threadId, files);
              uploadedFileInfo = uploadResponse.files;

              // Update optimistic human message with uploaded status + paths
              const uploadedFiles: FileInMessage[] = uploadedFileInfo.map(
                (info) => ({
                  filename: info.filename,
                  size: info.size,
                  path: info.virtual_path,
                  status: "uploaded" as const,
                }),
              );
              // Update human message with uploaded paths AND drop the
              // "uploading files..." AI placeholder. After this point the
              // optimistic state contains ONLY the human message bubble (with
              // file chips), so the about-to-fire thread.submit() stream
              // produces the same visual flow as a plain-text turn -- the
              // first server-emitted assistant chunk renders the normal
              // step/Reasoning/Tool panels directly, not stacked under a
              // lingering upload spinner. Matches the user expectation that
              // attached and plain dialogs share identical WebUI flow.
              setOptimisticMessages((messages) => {
                if (messages.length > 0 && messages[0]) {
                  const humanMessage: Message = messages[0];
                  return [
                    {
                      ...humanMessage,
                      additional_kwargs: { files: uploadedFiles },
                    },
                  ];
                }
                return messages;
              });
            }
          } catch (error) {
            console.error("[sendMessage] Upload failed (thread.submit will NOT fire); user remains on fresh URL to retry. threadId:", threadId, "error:", error);
            const errorMessage =
              error instanceof Error
                ? error.message
                : "Failed to upload files.";
            toast.error(errorMessage);
            setOptimisticMessages([]);
            throw error;
          }
        }

        // Build files metadata for submission (included in additional_kwargs)
        const filesForSubmit: FileInMessage[] = uploadedFileInfo.map(
          (info) => ({
            filename: info.filename,
            size: info.size,
            path: info.virtual_path,
            status: "uploaded" as const,
          }),
        );

        const buildSubmitPayload = (files: FileInMessage[]) => ({
          messages: [
            {
              type: "human" as const,
              content: [
                {
                  type: "text" as const,
                  text,
                },
              ],
              additional_kwargs: files.length > 0 ? { files } : {},
            },
          ],
        });

        const buildSubmitOptions = (
          targetThreadId?: string | null,
          route: DialogueRoute = dialogueRoute,
        ) => {
          const permissionMode = resolvePermissionMode(context.permission_mode);
          const thinkingEnabled = shouldEnableThinking(effectiveMode) || route.needsDeepAgent;
          const mlInternProfile = resolveMlInternProfile({
            permissionMode,
            mode: "dialogue",
          });
          return {
            threadId: targetThreadId ?? undefined,
            streamSubgraphs: true,
            streamResumable: true,
            streamMode: DEFAULT_STREAM_MODE,
              multitaskStrategy: "interrupt" as const,
            config: {
              recursion_limit: getRecursionLimit(),
            },
            context: {
              ...context,
              mode: effectiveMode,
              reasoning_effort:
                effectiveMode === "flash" ? "minimal" : context.reasoning_effort,
              ...extraContext,
              ...buildMlInternThreadContext(mlInternProfile),
              client_command: operationPlan?.command,
              session_governance: operationPlan?.governance,
              // SINGLE-SOURCE-ROUTING: backend is sole route truth.
              // dialogue_route / dialogue_route_reason intentionally omitted so
              // backend always reclassifies from text + signals.
              dialogue_text: text,
              last_user_message: text,
              thread_message_count: thread.messages.length,
              dialogue_needs_tools: route.needsTools,
              dialogue_needs_memory: route.needsMemory,
              dialogue_needs_deep_agent: route.needsDeepAgent,
              permission_mode: permissionMode,
              thinking_enabled: thinkingEnabled,
              is_plan_mode: route.kind === "plan_only" || route.needsDeepAgent || effectiveMode === "pro" || effectiveMode === "ultra",
              subagent_enabled: route.needsDeepAgent && effectiveMode === "ultra",
              thread_id: targetThreadId ?? undefined,
            },
          };
        };

        try {
          // Now that threads.create succeeded AND any attachment uploads
          // finished, notify the UI we're leaving /new. This used to fire
          // before uploads (see comment near markThreadPersisted above) but
          // that caused a URL-strip race that orphaned thread.submit().
          _handleOnStart(threadId);
          listeners.current.onRunEvent?.(
            createRunEvent("planning", "Streaming started", "Waiting for runtime events."),
          );
          await thread.submit(buildSubmitPayload(filesForSubmit), buildSubmitOptions(threadId));
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          const looksLikeMissingAttachment =
            /file not found|file not exist|FileNotFound|ENOENT|no such file/i.test(msg) ||
            (msg.toLowerCase().includes("not found") && msg.toLowerCase().includes("file"));

          if (looksLikeMissingAttachment && filesForSubmit.length > 0) {
            console.warn(
              "thread.submit failed due to missing file on server, retrying without files:",
              msg,
            );
            toast.error("Attachment missing on server - sending without attachments.");

            try {
              await thread.submit(buildSubmitPayload([]), buildSubmitOptions(threadId));
              void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
            } catch (err2) {
              console.error("Fallback submit without files also failed:", err2);
              throw err;
            }
          } else if (threadId && isRecoverableThreadMissingError(err)) {
            console.warn(
              "thread.submit failed because the active thread is missing, retrying in a fresh thread:",
              msg,
            );
            markThreadProvisional(threadId);
            setOnStreamThreadId(null);
            threadIdRef.current = null;
            startedRef.current = false;
            pushSystemEvent({ level: "warning", message: t.threadEvents.sessionRefreshed, source: "session" });

            try {
              await thread.submit(buildSubmitPayload(filesForSubmit), buildSubmitOptions(null));
              void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
            } catch (err2) {
              console.error("Fresh-thread submit fallback also failed:", err2);
              throw err;
            }
          } else {
            throw err;
          }
        }
        void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
      } catch (error) {
        console.error("[sendMessage] Outer pipeline error (clearing optimistic messages, watchdog). threadId:", threadId, "error:", error);
        clearWatchdog();
        setOptimisticMessages([]);
        throw error;
      }
    },
    [
      thread,
      _handleOnStart,
      t.threadEvents.sessionRefreshed,
      t.threadEvents.watchdogLongRun,
      t.uploads.uploadingFiles,
      context,
      queryClient,
      clearWatchdog,
      isMock,
    ],
  );

  // Merge thread with optimistic messages for display
  const visibleOptimisticMessages =
    optimisticMessages.length > 0
      ? optimisticMessages.filter((message) => !isDuplicateOptimisticHuman(message, thread.messages))
      : optimisticMessages;
  const mergedThread =
    visibleOptimisticMessages.length > 0
      ? ({
          ...thread,
          messages: [...thread.messages, ...visibleOptimisticMessages],
        } as typeof thread)
      : thread;

  return [mergedThread, sendMessage] as const;
}

export function useThreads(
  params: Parameters<ThreadsClient["search"]>[0] = {
    limit: 50,
    sortBy: "updated_at",
    sortOrder: "desc",
    select: ["thread_id", "updated_at", "values", "metadata"],
  },
) {
  const apiClient = getAPIClient();
  return useQuery<AgentThread[]>({
    queryKey: ["threads", "search", params],
    queryFn: async () => {
      const maxResults = params.limit;
      const initialOffset = params.offset ?? 0;
      const DEFAULT_PAGE_SIZE = 50;

      // Preserve prior semantics: if a non-positive limit is explicitly provided,
      // delegate to a single search call with the original parameters.
      if (maxResults !== undefined && maxResults <= 0) {
        const response = await apiClient.threads.search<AgentThreadState>(params);
        return response as AgentThread[];
      }

      const pageSize =
        typeof maxResults === "number" && maxResults > 0
          ? Math.min(DEFAULT_PAGE_SIZE, maxResults)
          : DEFAULT_PAGE_SIZE;

      const threads: AgentThread[] = [];
      let offset = initialOffset;

      while (true) {
        if (typeof maxResults === "number" && threads.length >= maxResults) {
          break;
        }

        const currentLimit =
          typeof maxResults === "number"
            ? Math.min(pageSize, maxResults - threads.length)
            : pageSize;

        if (typeof maxResults === "number" && currentLimit <= 0) {
          break;
        }

        const response = (await apiClient.threads.search<AgentThreadState>({
          ...params,
          limit: currentLimit,
          offset,
        })) as AgentThread[];

        threads.push(...response);

        if (response.length < currentLimit) {
          break;
        }

        offset += response.length;
      }

      return threads;
    },
    refetchOnWindowFocus: false,
  });
}

export function useThreadState(threadId?: string | null, enabled = true) {
  const query = useQuery<AgentThreadState | null>({
    queryKey: ["threads", "state", threadId],
    enabled: enabled && Boolean(threadId),
    queryFn: async () => {
      if (!threadId) {
        throw new Error("threadId is required");
      }
      // Use a raw fetch instead of the LangGraph SDK client here.
      // The SDK's AsyncCaller wraps fetch with p-retry and throws
      // HTTPError for 404s in a way that leaks unhandled promise
      // rejections — triggering the Next.js dev Runtime Error overlay
      // even when the error is caught in application code.
      // A direct fetch avoids this: we check `response.ok` synchronously
      // and return `null` without ever throwing for missing threads.
      const base = getLangGraphBaseURL();
      const url = `${base}/threads/${encodeURIComponent(threadId)}/state`;
      const response = await fetch(url);
      if (!response.ok) {
        // 404 = thread genuinely missing; 500 = thread exists but state is
        // broken (e.g. error status after backend restart).  Both cases
        // return null so the caller can redirect gracefully instead of
        // TanStack Query entering an error state that blocks rendering.
        return null;
      }
      const state = await response.json();
      return state.values as AgentThreadState | null;
    },
    refetchOnWindowFocus: false,
    // Never use stale cached thread state — the server may have restarted
    // and lost threads; stale cache causes useStream 404 before redirect fires.
    gcTime: 0,
    staleTime: 0,
    retry: false,
  });
  return {
    ...query,
    // isVerifying: true while the network request is in flight, even on cache hit.
    // Use this instead of isLoading to gate components that depend on fresh state.
    isVerifying: query.isFetching,
  };
}

export function useDeleteThread() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ threadId }: { threadId: string }) => {
      await deleteJSON(
        `/api/runtime/langgraph-contract/threads/${encodeURIComponent(threadId)}`,
      );
    },
    onSuccess(_, { threadId }) {
      queryClient.setQueriesData(
        {
          queryKey: ["threads", "search"],
          exact: false,
        },
        (oldData: Array<AgentThread>) => {
          return oldData.filter((t) => t.thread_id !== threadId);
        },
      );
    },
  });
}

export function useRenameThread() {
  const queryClient = useQueryClient();
  const apiClient = getAPIClient();
  return useMutation({
    mutationFn: async ({
      threadId,
      title,
    }: {
      threadId: string;
      title: string;
    }) => {
      await apiClient.threads.updateState(threadId, {
        values: { title },
      });
    },
    onSuccess(_, { threadId, title }) {
      queryClient.setQueriesData(
        {
          queryKey: ["threads", "search"],
          exact: false,
        },
        (oldData: Array<AgentThread>) => {
          return oldData.map((t) => {
            if (t.thread_id === threadId) {
              return {
                ...t,
                values: {
                  ...t.values,
                  title,
                },
              };
            }
            return t;
          });
        },
      );
    },
  });
}
