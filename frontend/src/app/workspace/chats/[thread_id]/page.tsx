"use client";

import { PlayIcon, RotateCcwIcon, SquareIcon } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { type PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useSpecificChatMode } from "@/components/workspace/chats/use-chat-mode";
import { useThreadChat } from "@/components/workspace/chats/use-thread-chat";
import { ThreadContext } from "@/components/workspace/messages/context";
import { Welcome } from "@/components/workspace/welcome";
import { isRecoverableThreadMissingError } from "@/core/api";
import type { ContextTokenUsage } from "@/core/context/context-token-counter";
import { useI18n } from "@/core/i18n/hooks";
import { useNotification } from "@/core/notification/hooks";
import {
  createRunEvent,
  mergeRunEvents,
  normalizeRunEvents,
  normalizeWorkflowRunEvents,
  type RunEvent,
} from "@/core/runtime";
import { useLocalSettings } from "@/core/settings";
import { pushSystemEvent } from "@/core/system-events/store";
import { buildContinuationContext } from "@/core/threads";
import { useThreadState, useThreadStream } from "@/core/threads/hooks";
import type { AgentThreadContext, AgentThreadState } from "@/core/threads/types";
import { textOfMessage } from "@/core/threads/utils";
import { useWorkflows } from "@/core/workflows";
import { env } from "@/env";
import { cn } from "@/lib/utils";

import { ChatBox } from "@/components/workspace/chats/chat-box";
import { InputBox } from "@/components/workspace/input-box";
import { MessageList } from "@/components/workspace/messages/message-list";
import { ThreadTitle } from "@/components/workspace/thread-title";
import { TodoList } from "@/components/workspace/todo-list";
function ChatRouteFallback() {
  const { t } = useI18n();
  return (
    <div className="flex size-full min-h-0 flex-col lg:flex-row">
      <section className="relative flex min-h-0 flex-1 flex-col overflow-hidden" aria-labelledby="chat-loading-title">
        <div className="octo-grid pointer-events-none absolute inset-0 opacity-65" />
        <div className="relative flex min-h-0 flex-1 items-center justify-center px-6 text-center">
          <div>
            <h1 id="chat-loading-title" className="text-2xl font-semibold text-foreground">{t.chatLoading.title}</h1>
            <p className="mt-2 text-sm text-muted-foreground">{t.chatLoading.preparing}</p>
          </div>
        </div>
        <div className="relative z-10 px-4 pb-5">
          <div className="octo-panel mx-auto h-24 w-full max-w-5xl rounded-[1.75rem] border border-border/60" />
        </div>
      </section>
      <aside className="hidden min-h-0 w-[38%] min-w-[22rem] border-l border-border/60 p-4 lg:block" aria-label={t.chatLoading.inspectorLoading}>
        <div className="octo-panel flex size-full min-h-[16rem] items-center justify-center rounded-[1.75rem] px-4 text-center text-sm text-muted-foreground">
          Loading runtime inspector...
        </div>
      </aside>
    </div>
  );
}

type RunControlState = {
  visible: boolean;
  label: string;
  detail?: string;
  level: "info" | "warning" | "error";
  canRetry: boolean;
  canResume: boolean;
};

function resolveRunControlState({
  isLoading,
  runtime,
  error,
  lastUserText,
}: {
  isLoading: boolean;
  runtime: AgentThreadState["runtime"];
  error: unknown;
  lastUserText: string | null;
}): RunControlState {
  if (isLoading) {
    return {
      visible: true,
      label: "Running",
      detail: "Current run is active.",
      level: "info",
      canRetry: false,
      canResume: false,
    };
  }

  const recoverable = runtime?.recoverable_failure ?? runtime?.incomplete_state ?? null;
  const lastRunRecord = runtime?.last_run_record as
    | { final_evaluation?: { status?: string; reason?: string } }
    | null
    | undefined;
  const finalEvaluation = lastRunRecord?.final_evaluation;
  const finalStatus = finalEvaluation?.status;
  const hasRuntimeError = Boolean(error || runtime?.final_error);

  if (recoverable || finalStatus === "failed" || finalStatus === "incomplete" || hasRuntimeError) {
    const detail =
      (typeof recoverable?.reason === "string" ? recoverable.reason : undefined) ??
      finalEvaluation?.reason ??
      runtime?.final_error ??
      (error instanceof Error ? error.message : undefined);
    return {
      visible: true,
      label: finalStatus === "incomplete" || recoverable ? "Needs attention" : "Run failed",
      detail,
      level: "error",
      canRetry: Boolean(lastUserText),
      canResume: true,
    };
  }

  if (runtime?.continuation_mode === "resumed" || runtime?.workflow_resume_state === "resumed") {
    return {
      visible: true,
      label: "Resumed",
      detail: runtime.continuation_source ? `Continued from ${runtime.continuation_source}.` : "Continuation context is active.",
      level: "info",
      canRetry: false,
      canResume: false,
    };
  }

  return { visible: false, label: "", level: "info", canRetry: false, canResume: false };
}

function RunControlBar({
  state,
  onStop,
  onRetry,
  onResume,
}: {
  state: RunControlState;
  onStop: () => void;
  onRetry: () => void;
  onResume: () => void;
}) {
  if (!state.visible) return null;
  const tone =
    state.level === "error"
      ? "border-destructive/30 text-destructive"
      : state.level === "warning"
        ? "border-amber-500/30 text-amber-600 dark:text-amber-400"
        : "border-border/70 text-muted-foreground";

  return (
    <div className="mb-2 rounded-md border border-border/70 bg-background/95 px-3 py-2 text-sm shadow-sm backdrop-blur">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className={cn("h-6 px-2 text-xs", tone)}>
          {state.label}
        </Badge>
        {state.detail ? (
          <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{state.detail}</span>
        ) : (
          <span className="min-w-0 flex-1" />
        )}
        {state.label === "Running" ? (
          <Button type="button" variant="outline" size="sm" onClick={onStop} title="Stop current run">
            <SquareIcon className="size-3.5" />
            Stop
          </Button>
        ) : null}
        {state.canRetry ? (
          <Button type="button" variant="outline" size="sm" onClick={onRetry} title="Retry last user message">
            <RotateCcwIcon className="size-3.5" />
            Retry
          </Button>
        ) : null}
        {state.canResume ? (
          <Button type="button" variant="outline" size="sm" onClick={onResume} title="Resume from current state">
            <PlayIcon className="size-3.5" />
            Resume
          </Button>
        ) : null}
      </div>
    </div>
  );
}

type ChatInputContext = Omit<
  AgentThreadContext,
  "thread_id" | "is_plan_mode" | "thinking_enabled" | "subagent_enabled"
> & {
  mode: "flash" | "thinking" | "pro" | "ultra" | undefined;
  reasoning_effort?: "minimal" | "low" | "medium" | "high";
};

export default function ChatPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [settings, setSettings] = useLocalSettings();

  // Defer rendering until after hydration — ChatThreadView contains Radix UI
  // components whose auto-generated IDs (useId) differ between SSR and client
  // when hooks like useStream alter the fiber tree.  Rendering null on both
  // SSR and first client render guarantees identical output; actual UI renders
  // on the second (post-hydration) paint.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => { setHydrated(true); }, []);

  const { thread_id: rawThreadId } = useParams<{ thread_id: string }>();
  const { threadId, isNewThread, isFreshRoute, setThreadId, setIsNewThread, isMock, continueFromThreadId } =
    useThreadChat();
  const [existingThreadVerifyTimedOut, setExistingThreadVerifyTimedOut] =
    useState(false);
  // Track threads that were locally activated (created from /new) so that the
  // blocking thread-state verification does not fire when history.replaceState
  // triggers a Next.js router update and rawThreadId briefly flips to the real
  // UUID — which would cause ChatThreadView to unmount and kill the live stream.
  const justActivatedThreadIdRef = useRef<string | null>(null);
  const markThreadJustActivated = useCallback((id: string) => {
    justActivatedThreadIdRef.current = id;
  }, []);
  useSpecificChatMode();
  const { hydrate } = useWorkflows();
  const continuationHydratedRef = useRef(false);

  // Reset just-activated marker when the user navigates back to a fresh /new thread.
  useEffect(() => {
    if (rawThreadId === "new") {
      justActivatedThreadIdRef.current = null;
    }
  }, [rawThreadId]);

  useEffect(() => {
    if (!hydrated || rawThreadId !== "new" || !threadId || threadId === "new") {
      return;
    }

    const params = new URLSearchParams(window.location.search);
    params.set("fresh", "1");
    if (!params.has("draft")) {
      params.set("draft", String(Date.now()));
    }
    router.replace(`/workspace/chats/${threadId}?${params.toString()}`);
  }, [hydrated, rawThreadId, router, threadId]);

  const { showNotification } = useNotification();
  const { data: continuationSourceState } = useThreadState(
    continueFromThreadId,
    Boolean(isNewThread && continueFromThreadId && !isMock),
  );
  const {
    data: existingThreadState,
    isVerifying: isExistingThreadVerifying,
  } = useThreadState(
    isNewThread ? null : threadId,
    Boolean(!isNewThread && threadId && !isMock),
  );
  const shouldVerifyExistingThread =
    rawThreadId !== "new" &&
    !isNewThread &&
    !isMock &&
    threadId !== justActivatedThreadIdRef.current;

  useEffect(() => {
    setExistingThreadVerifyTimedOut(false);
    if (
      !shouldVerifyExistingThread ||
      !isExistingThreadVerifying ||
      existingThreadState
    ) {
      return;
    }

    const timeout = window.setTimeout(() => {
      console.warn("[ChatPage] Thread state verification timed out; rendering chat shell.", {
        threadId,
      });
      setExistingThreadVerifyTimedOut(true);
    }, 3_000);

    return () => window.clearTimeout(timeout);
  }, [
    existingThreadState,
    isExistingThreadVerifying,
    shouldVerifyExistingThread,
    threadId,
  ]);

  useEffect(() => {
    if (
      !isNewThread ||
      !continueFromThreadId ||
      !continuationSourceState ||
      continuationHydratedRef.current
    ) {
      return;
    }
    hydrate(
      continuationSourceState.workflows ?? [],
      continuationSourceState.workflow_events ?? [],
    );
    continuationHydratedRef.current = true;
  }, [
    continueFromThreadId,
    continuationSourceState,
    hydrate,
    isNewThread,
  ]);

  const continuationContext = useMemo(() => {
    if (!isNewThread || !continueFromThreadId || !continuationSourceState) {
      return undefined;
    }

    return buildContinuationContext(continueFromThreadId, continuationSourceState);
  }, [continueFromThreadId, continuationSourceState, isNewThread]);

  // Only verify existence when the user navigated directly to a thread URL.
  // When transitioning from /new (thread just created), the first checkpoint
  // may not exist yet → GET /state returns 404 → false "expired" redirect.
  // history.replaceState does NOT update useParams, so rawThreadId stays "new".
  const missingExistingThread =
    shouldVerifyExistingThread &&
    !existingThreadVerifyTimedOut &&
    !isExistingThreadVerifying &&
    !existingThreadState;

  useEffect(() => {
    if (missingExistingThread) {
      pushSystemEvent({
        level: "warning",
        message: t.systemEvents.threadLoadFailed,
        source: "session",
      });
      setExistingThreadVerifyTimedOut(true);
    }
  }, [missingExistingThread, t.systemEvents.threadLoadFailed]);

  // Block rendering until the thread state has been verified against the server.
  // Using isVerifying (isFetching) instead of isLoading prevents stale cache
  // from letting ChatThreadView mount with a defunct thread ID.
  const isBlockingExistingThreadVerification =
    shouldVerifyExistingThread &&
    isExistingThreadVerifying &&
    !existingThreadState &&
    !existingThreadVerifyTimedOut;
  if (!hydrated || isBlockingExistingThreadVerification) {
    return <ChatRouteFallback />;
  }

  return (
    <ChatThreadView
      continuationContext={continuationContext}
      continuationSourceState={continuationSourceState ?? undefined}
      continueFromThreadId={continueFromThreadId ?? undefined}
      isMock={isMock}
      isFreshRoute={isFreshRoute}
      isNewThread={isNewThread}
      onThreadActivated={markThreadJustActivated}
      router={router}
      settings={settings}
      setIsNewThread={setIsNewThread}
      setThreadId={setThreadId}
      setSettings={setSettings}
      showNotification={showNotification}
      t={t}
      threadId={threadId}
    />
  );
}

function ChatThreadView({
  continuationContext,
  continuationSourceState,
  continueFromThreadId,
  isMock,
  isFreshRoute,
  isNewThread,
  onThreadActivated,
  router,
  settings,
  setIsNewThread,
  setThreadId,
  setSettings,
  showNotification,
  t,
  threadId,
}: {
  continuationContext: Record<string, unknown> | undefined;
  continuationSourceState: AgentThreadState | undefined;
  continueFromThreadId?: string;
  isMock: boolean;
  isFreshRoute: boolean;
  isNewThread: boolean;
  onThreadActivated: (threadId: string) => void;
  router: ReturnType<typeof useRouter>;
  settings: ReturnType<typeof useLocalSettings>[0];
  setIsNewThread: (value: boolean) => void;
  setThreadId: (value: string) => void;
  setSettings: ReturnType<typeof useLocalSettings>[1];
  showNotification: ReturnType<typeof useNotification>["showNotification"];
  t: ReturnType<typeof useI18n>["t"];
  threadId: string;
}) {
  const threadCreatedAtRef = useRef<number | null>(null);
  // Initialize the "thread freshly opened" timestamp as soon as the
  // component mounts. The 15s protection window on the page-level
  // "thread missing → redirect to /new" guard previously depended on
  // this ref being set inside activateThreadRoute (called from the SDK's
  // onStart). When a turn was attempted but never reached runs/stream
  // (e.g. an upload race or transient error), onStart never fired,
  // threadCreatedAtRef stayed null, and a transient 404 on GET /state
  // could bounce the user to a brand-new fresh chat — losing their
  // attachment + draft. Capturing the timestamp on mount closes that
  // gap without changing the "stale thread eventually redirects" intent.
  threadCreatedAtRef.current ??= Date.now();
  const routeSyncRef = useRef<string | null>(null);
  const [runEvents, setRunEvents] = useState<RunEvent[]>([]);
  const [pendingContinuationContext, setPendingContinuationContext] = useState<Record<string, unknown> | undefined>();
  const [contextCycleBaseTokens, setContextCycleBaseTokens] = useState(0);
  const autoContinuationStartedRef = useRef(false);
  // Capture initial isNewThread to stabilize loadInitialState across re-renders.
  // When onStart fires setIsNewThread(false), loadInitialState must NOT flip
  // from false→true mid-stream, otherwise useStream reconnects and kills the
  // active SSE stream — causing the first message to get no reply.
  const initialIsNewRef = useRef(isNewThread);
  const activateThreadRoute = useCallback(
    (createdThreadId: string) => {
      threadCreatedAtRef.current ??= Date.now();
      // Mark the thread as locally activated BEFORE setIsNewThread so that
      // when history.replaceState causes Next.js to update useParams and
      // rawThreadId flips to the real UUID, shouldVerifyExistingThread is
      // already gated — preventing ChatThreadView from unmounting and killing
      // the live SSE stream (which would swallow the first message reply).
      onThreadActivated(createdThreadId);
      setThreadId(createdThreadId);
      if (routeSyncRef.current === createdThreadId) {
        return;
      }

      routeSyncRef.current = createdThreadId;
      const url = new URL(window.location.href);
      url.pathname = `/workspace/chats/${createdThreadId}`;
      history.replaceState(null, "", url.pathname + url.search);
      // Note (2026-05-26): query cleanup of ?fresh=1&draft=... is intentionally
      // deferred to the "first AI message arrives" effect below. Stripping
      // the query here used to fire BEFORE the upload + thread.submit pipeline
      // completed, causing a cascade:
      //   history.replaceState → useSearchParams re-renders →
      //   useThreadChat setIsNewThread(false) → page re-evaluation →
      //   useThreadState may fetch /state during the brief window before
      //   the activation ref propagates → 404 → ChatRouteFallback renders →
      //   ChatThreadView UNMOUNTS → in-flight thread.submit() orphaned →
      //   no /runs/stream POST ever reaches the server → user sees the
      //   chat silently "reset" with no agent reply.
      // Keep fresh/draft through the first turn, but sync the pathname to the
      // real server-created thread immediately so stale client-generated UUIDs
      // are never verified as existing conversations.
      // The "first AI message" effect (below) handles fresh/draft cleanup
      // once a streamed reply has actually started arriving.
    },
    [onThreadActivated, setThreadId],
  );

  const [thread, sendMessage] = useThreadStream({
    threadId: threadId,
    context: settings.context,
    isMock,
    loadInitialState: !initialIsNewRef.current,
    onStart: (createdThreadId) => {
      activateThreadRoute(createdThreadId);
    },
    onRunEvent: (event) => {
      setRunEvents((previous) => mergeRunEvents([event], previous, 120));
    },
    onFinish: (state) => {
      setRunEvents((previous) => mergeRunEvents([
        createRunEvent("done", "Run finished", undefined, "success"),
      ], previous, 120));
      // Context handoff: navigate to new thread with continuation
      const handoff = (state as Record<string, unknown>)?._context_handoff as
        | { required: boolean; source_thread_id: string; reason: string }
        | undefined;
      if (handoff?.required && handoff.source_thread_id) {
        router.push(
          `/workspace/chats/new?continue_from=${encodeURIComponent(handoff.source_thread_id)}&fresh=1`,
        );
        return;
      }
      if (document.hidden || !document.hasFocus()) {
        let body = "Conversation finished";
        const lastMessage = state.messages.at(-1);
        if (lastMessage) {
          const textContent = textOfMessage(lastMessage);
          if (textContent) {
            body =
              textContent.length > 200
                ? `${textContent.substring(0, 200)}...`
                : textContent;
          }
        }
        showNotification(state.title, { body });
      }
    },
  });

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      const hiddenContinuationContext = pendingContinuationContext ?? continuationContext;
      if (pendingContinuationContext) {
        setContextCycleBaseTokens(Number(pendingContinuationContext.continue_cycle_base_tokens ?? 0));
        setPendingContinuationContext(undefined);
      }
      void sendMessage(threadId, message, hiddenContinuationContext);
    },
    [continuationContext, pendingContinuationContext, sendMessage, threadId],
  );

  useEffect(() => {
    if (
      autoContinuationStartedRef.current ||
      !isFreshRoute ||
      !isNewThread ||
      !continueFromThreadId ||
      !continuationContext ||
      thread.isLoading ||
      thread.messages.length > 0
    ) {
      return;
    }
    autoContinuationStartedRef.current = true;
    pushSystemEvent({
      level: "info",
      message: t.systemEvents.autoContinueResume,
      source: "context-handoff",
    });
    void sendMessage(
      threadId,
      {
        text: "继续执行上一段对话中尚未完成的任务。请根据隐藏的接续记忆、todo 状态和最近三轮双方对话，立即从下一步开始工作，不要要求用户重复说明。",
        files: [],
      },
      continuationContext,
    );
  }, [
    continuationContext,
    continueFromThreadId,
    isFreshRoute,
    isNewThread,
    sendMessage,
    t.systemEvents.autoContinueResume,
    thread.isLoading,
    thread.messages.length,
    threadId,
  ]);

  useEffect(() => {
    if (!isFreshRoute || !isNewThread || thread.isLoading) {
      return;
    }
    const hasAssistantMessage = thread.messages.some((message) =>
      message.type === "ai",
    );
    if (!hasAssistantMessage) {
      return;
    }
    const url = new URL(window.location.href);
    url.pathname = `/workspace/chats/${threadId}`;
    url.searchParams.delete("fresh");
    url.searchParams.delete("draft");
    history.replaceState(null, "", url.pathname + url.search);
    setIsNewThread(false);
  }, [isFreshRoute, isNewThread, setIsNewThread, thread.isLoading, thread.messages, threadId]);

  useEffect(() => {
    setRunEvents([]);
  }, [threadId]);

  useEffect(() => {
    const persisted = mergeRunEvents(
      normalizeRunEvents(thread.values.runtime?.run_events),
      normalizeWorkflowRunEvents(thread.values.workflow_events),
      120,
    );
    if (persisted.length === 0) {
      return;
    }
    setRunEvents((previous) => mergeRunEvents(persisted, previous, 120));
  }, [thread.values.runtime?.run_events, thread.values.workflow_events]);

  useEffect(() => {
    setContextCycleBaseTokens(Number(thread.values.runtime?.context_cycle_base_tokens ?? 0));
  }, [threadId, thread.values.runtime?.context_cycle_base_tokens]);

  const handleStop = useCallback(async () => {
    setRunEvents((previous) => mergeRunEvents([
      createRunEvent("planning", "User stopped the run", "Stop requested from chat controls.", "warning"),
    ], previous, 120));
    pushSystemEvent({
      level: "info",
      message: t.systemEvents.userAborted,
      source: "session",
    });
    await thread.stop();
  }, [t.systemEvents.userAborted, thread]);

  const lastUserText = useMemo(() => {
    for (let index = thread.messages.length - 1; index >= 0; index -= 1) {
      const message = thread.messages[index];
      if (!message || message.type !== "human") continue;
      const text = (textOfMessage(message) ?? "").trim();
      if (text) return text;
    }
    return null;
  }, [thread.messages]);

  const runControlState = useMemo(
    () =>
      resolveRunControlState({
        isLoading: thread.isLoading,
        runtime: thread.values.runtime,
        error: thread.error,
        lastUserText,
      }),
    [lastUserText, thread.error, thread.isLoading, thread.values.runtime],
  );

  const handleRetryLastTurn = useCallback(() => {
    if (!lastUserText || thread.isLoading) {
      return;
    }
    pushSystemEvent({
      level: "info",
      message: "Retrying the last user turn.",
      source: "session",
    });
    const controlEvent = createRunEvent("planning", "User retried the last turn", "Retry requested from chat controls.");
    setRunEvents((previous) => mergeRunEvents([controlEvent], previous, 120));
    void sendMessage(threadId, { text: lastUserText, files: [] }, {
      client_control_event: {
        id: controlEvent.id,
        action: "retry",
        title: controlEvent.title,
        detail: controlEvent.detail,
      },
    });
  }, [lastUserText, sendMessage, thread.isLoading, threadId]);

  const handleResumeRun = useCallback(() => {
    if (thread.isLoading) {
      return;
    }
    pushSystemEvent({
      level: "info",
      message: "Resuming from the current runtime state.",
      source: "session",
    });
    const controlEvent = createRunEvent("planning", "User resumed the run", "Resume requested from chat controls.");
    setRunEvents((previous) => mergeRunEvents([controlEvent], previous, 120));
    void sendMessage(threadId, {
      text: "Continue the unfinished work in this conversation. Use the existing runtime state, todos, tool results, and recent context. Start from the next concrete step; if a failure exists, first name the recovery point and then continue.",
      files: [],
    }, {
      client_control_event: {
        id: controlEvent.id,
        action: "resume",
        title: controlEvent.title,
        detail: controlEvent.detail,
      },
    });
  }, [sendMessage, thread.isLoading, threadId]);

  const handleContextThreshold = useCallback((usage: ContextTokenUsage) => {
    if (thread.isLoading) {
      return;
    }
    // If context is critically full (>= 95%), navigate to new thread directly
    if (usage.ratio >= 0.95 && thread.messages.length > 0 && !isNewThread) {
      console.info(`[octoagent] Context usage ${usage.percent}% (critical) — switching to new thread`);
      router.push(
        `/workspace/chats/new?continue_from=${encodeURIComponent(threadId)}&fresh=1`,
      );
      return;
    }
    const cycleId = `context-cycle-${threadId}-${Date.now()}`;
    const cycleStartedAt = new Date().toISOString();
    const continuationSource = thread.messages.length > 0 && !isNewThread
      ? buildContinuationContext(threadId, thread.values)
      : {};
    setPendingContinuationContext({
      ...continuationSource,
      continue_cycle_id: cycleId,
      continue_cycle_started_at: cycleStartedAt,
      continue_cycle_base_tokens: usage.rawUsedTokens,
    });
    console.info(`[octoagent] Context usage reached ${usage.percent}%; next turn will use hidden compaction context in-place.`);
  }, [isNewThread, router, thread.isLoading, thread.messages.length, thread.values, threadId]);

  const handleContextChange = useCallback(
    (context: ChatInputContext) => setSettings("context", context),
    [setSettings],
  );

  const threadContextValue = useMemo(
    () => ({ thread, isMock }),
    [isMock, thread],
  );

  const welcomeContinuation = useMemo(() => {
    if (!continueFromThreadId) {
      return undefined;
    }

    return {
      sourceTitle: continuationSourceState?.title ?? continueFromThreadId,
      messageCount: continuationSourceState?.messages?.length ?? 0,
      recentMessages: (continuationSourceState?.messages ?? [])
        .slice(-6)
        .map((m) => ({
          role: m.type,
          content:
            typeof m.content === "string"
              ? m.content
              : "",
        }))
        .filter((m) => m.content.trim().length > 0),
    };
  }, [continueFromThreadId, continuationSourceState]);

  useEffect(() => {
    if (!thread.error || isNewThread) return;
    if (thread.isLoading) return;
    const msg =
      thread.error instanceof Error
        ? thread.error.message
        : typeof thread.error === "string"
          ? thread.error
          : typeof thread.error === "object" &&
              thread.error !== null &&
              "message" in thread.error &&
              typeof thread.error.message === "string"
            ? thread.error.message
            : "";
    if (msg.includes("not found") || msg.includes("404")) {
      // "Run not found" comes from reconnectOnMount trying to rejoin a
      // completed run — this is normal, not a thread expiry.
      if (msg.includes("Run not found")) return;
      // If thread already has messages, the error is from a stale reconnect.
      // This is the normal case for historical conversations — we have local
      // state and just failed to reconnect to a live run.
      if (thread.messages.length > 0) return;
      // Don't redirect threads that were just created — the first checkpoint
      // may not have been written yet, causing a spurious 404.
      if (threadCreatedAtRef.current && Date.now() - threadCreatedAtRef.current < 15_000) return;
      // 2026-05-16: Also check if the thread was loaded from sidebar/history
      // navigation — give it more time before declaring it unavailable.
      // The SDK onError handler already swallows recoverable 404s and treats
      // the thread as a readable history view.
      if (isRecoverableThreadMissingError(thread.error)) return;
      // Diagnostic: log the conditions that led to this redirect so future
      // accidental thread-resets are traceable from the browser console.
      console.warn("[ChatThreadView] redirecting stale thread to /new", {
        threadId,
        threadError: thread.error,
        threadErrorMessage: msg,
        threadCreatedAt: threadCreatedAtRef.current,
        ageMs: threadCreatedAtRef.current ? Date.now() - threadCreatedAtRef.current : null,
        isNewThread,
        messagesLength: thread.messages.length,
      });
      toast.info("Chat session is no longer available. Starting fresh.");
      router.replace("/workspace/chats/new");
    }
  }, [thread.error, thread.isLoading, isNewThread, router, thread.messages.length, threadId]);

  return (
    <ThreadContext.Provider value={threadContextValue}>
      <ChatBox contextModelName={typeof settings.context.model_name === "string" ? settings.context.model_name : undefined} isNewThread={isNewThread} mode={settings.context.mode} runEvents={runEvents} threadId={threadId}>
        <div className="relative flex size-full min-h-0 justify-between overflow-hidden">
          <div className="octo-grid pointer-events-none absolute inset-0 opacity-65" />
          <h1 className="sr-only">{isNewThread ? t.pages.newChat : thread.values.title}</h1>
          <header
            className="absolute top-0 right-0 left-0 z-30 flex h-14 shrink-0 items-center px-5"
          >
            <div className="flex min-w-0 flex-1 items-center text-sm font-medium">
              <ThreadTitle isNewThread={isNewThread} threadId={threadId} thread={thread} />
            </div>
            <div className="flex shrink-0 items-center">
            </div>
          </header>
          <div className="relative flex min-h-0 max-w-full grow flex-col">
            <div className="flex size-full justify-center">
              <MessageList
                className="size-full px-4 pb-32 pt-12"
                runEvents={runEvents}
                threadId={threadId}
                thread={thread}
                emptyState={
                  isNewThread ? (
                    <Welcome
                      mode={settings.context.mode}
                      continuation={welcomeContinuation}
                    />
                  ) : undefined
                }
              />
            </div>
            <div className="absolute right-0 bottom-0 left-0 z-30 flex justify-center px-3 pb-5 sm:px-4">
              <div className="relative w-full max-w-5xl">
                <div className="absolute right-0 bottom-full left-0 z-0 translate-y-px">
                  <TodoList
                    className="octo-panel"
                    todos={thread.values.todos ?? []}
                    hidden={
                      !thread.values.todos || thread.values.todos.length === 0
                    }
                  />
                </div>
                <RunControlBar
                  state={runControlState}
                  onStop={() => void handleStop()}
                  onRetry={handleRetryLastTurn}
                  onResume={handleResumeRun}
                />
                <InputBox
                  className={cn(
                    "octo-panel w-full rounded-[1.75rem]",
                    thread.values.todos?.length ? "rounded-t-none" : "",
                    isNewThread ? "pb-2" : "",
                  )}
                  isNewThread={isNewThread}
                  threadId={threadId}
                  threadState={thread.values}
                  autoFocus={false}
                  status={thread.isLoading ? "streaming" : "ready"}
                  context={settings.context}
                  contextCycleBaseTokens={contextCycleBaseTokens}
                  disabled={env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"}
                  onContextChange={handleContextChange}
                  onContextThreshold={handleContextThreshold}
                  onSubmit={handleSubmit}
                  onStop={handleStop}
                />
                {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" && (
                  <div className="text-muted-foreground w-full translate-y-12 text-center text-xs">
                    {t.common.notAvailableInDemoMode}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </ChatBox>
    </ThreadContext.Provider>
  );
}
