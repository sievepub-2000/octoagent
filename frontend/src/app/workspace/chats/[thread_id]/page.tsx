"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { type PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { ArtifactTrigger } from "@/components/workspace/artifacts";
import {
  ChatBox,
  useSpecificChatMode,
  useThreadChat,
} from "@/components/workspace/chats";
import { InputBox } from "@/components/workspace/input-box";
import { MessageList } from "@/components/workspace/messages";
import { ThreadContext } from "@/components/workspace/messages/context";
import { ThreadTitle } from "@/components/workspace/thread-title";
import { TodoList } from "@/components/workspace/todo-list";
import { Welcome } from "@/components/workspace/welcome";
import { getAPIClient } from "@/core/api";
import { useI18n } from "@/core/i18n/hooks";
import { useNotification } from "@/core/notification/hooks";
import { useLocalSettings } from "@/core/settings";
import { useThreadState, useThreadStream } from "@/core/threads/hooks";
import type { AgentThreadState } from "@/core/threads/types";
import { textOfMessage } from "@/core/threads/utils";
import { createWorkflowEvent, useWorkflows } from "@/core/workflows";
import { env } from "@/env";
import { cn } from "@/lib/utils";

function summarizeMessageContent(content: string, maxLength = 180) {
  const normalized = content.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength)}...`;
}

function buildContinuationBootstrapMessage(state: AgentThreadState): string {
  const normalizedMessages = (state.messages ?? [])
    .map((message) => ({
      role: message.type,
      content: textOfMessage(message) ?? "",
    }))
    .filter((message) => message.content.trim().length > 0);
  const recentSummary = normalizedMessages.slice(-6);
  let lastAssistantMessage: string | null = null;
  let lastUserMessage: string | null = null;

  for (let index = normalizedMessages.length - 1; index >= 0; index -= 1) {
    const current = normalizedMessages[index];
    if (!lastAssistantMessage && current?.role === "ai") {
      lastAssistantMessage = current.content;
      continue;
    }
    if (lastAssistantMessage && current?.role === "human") {
      lastUserMessage = current.content;
      break;
    }
  }

  const openTodos = (state.todos ?? [])
    .filter((todo) => todo.status !== "completed")
    .slice(0, 6)
    .map((todo) => `- ${todo.content ?? "Untitled todo"}`);

  const lines = [
    "这是自动创建的续接对话，请无缝接续之前的工作，不要重新开始。",
    "",
    "上一轮对话摘要：",
    `- 标题：${state.title || "Untitled"}`,
    `- 消息数：${normalizedMessages.length}`,
  ];

  if (recentSummary.length > 0) {
    lines.push("", "最近关键信息：");
    for (const message of recentSummary) {
      const label = message.role === "human" ? "用户" : message.role === "ai" ? "助手" : message.role;
      lines.push(`- ${label}：${summarizeMessageContent(message.content)}`);
    }
  }

  if (openTodos.length > 0) {
    lines.push("", "未完成事项：", ...openTodos);
  }

  if (lastUserMessage || lastAssistantMessage) {
    lines.push("", "最后一次完整往返：");
    if (lastUserMessage) {
      lines.push(`用户：${lastUserMessage}`);
    }
    if (lastAssistantMessage) {
      lines.push(`助手：${lastAssistantMessage}`);
    }
  }

  lines.push("", "请基于以上摘要继续完成剩余工作，并沿用当前工作流上下文。", "");
  return lines.join("\n");
}

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
  const { threadId, isNewThread, setIsNewThread, isMock, continueFromThreadId, autoContinue } =
    useThreadChat();
  useSpecificChatMode();
  const { hydrate } = useWorkflows();
  const continuationHydratedRef = useRef(false);

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

    const recentMessages = (continuationSourceState.messages ?? [])
      .slice(-8)
      .map((message) => ({
        role: message.type,
        content: textOfMessage(message) ?? "",
      }))
      .filter((message) => message.content.trim().length > 0);

    return {
      continue_trigger: "continue" as const,
      continue_from_thread_id: continueFromThreadId,
      continue_from_title: continuationSourceState.title,
      continue_message_count: continuationSourceState.messages?.length ?? 0,
      continue_recent_messages: recentMessages,
      continue_workflows: continuationSourceState.workflows ?? [],
    };
  }, [continueFromThreadId, continuationSourceState, isNewThread]);

  // Only verify existence when the user navigated directly to a thread URL.
  // When transitioning from /new (thread just created), the first checkpoint
  // may not exist yet → GET /state returns 404 → false "expired" redirect.
  // history.replaceState does NOT update useParams, so rawThreadId stays "new".
  const missingExistingThread =
    rawThreadId !== "new" &&
    !isNewThread &&
    !isMock &&
    !isExistingThreadVerifying &&
    !existingThreadState;

  useEffect(() => {
    if (missingExistingThread) {
      toast.info("Chat session is no longer available. Starting fresh.");
      router.replace("/workspace/chats/new");
    }
  }, [missingExistingThread, router]);

  // Block rendering until the thread state has been verified against the server.
  // Using isVerifying (isFetching) instead of isLoading prevents stale cache
  // from letting ChatThreadView mount with a defunct thread ID.
  if (!hydrated || (rawThreadId !== "new" && !isNewThread && !isMock && isExistingThreadVerifying)) {
    return null;
  }

  if (missingExistingThread) {
    return null;
  }

  return (
    <ChatThreadView
      key={threadId}
      autoContinue={autoContinue}
      continuationContext={continuationContext}
      continuationSourceState={continuationSourceState}
      continueFromThreadId={continueFromThreadId ?? undefined}
      isMock={isMock}
      isNewThread={isNewThread}
      router={router}
      settings={settings}
      setIsNewThread={setIsNewThread}
      setSettings={setSettings}
      showNotification={showNotification}
      t={t}
      threadId={threadId}
    />
  );
}

function ChatThreadView({
  autoContinue,
  continuationContext,
  continuationSourceState,
  continueFromThreadId,
  isMock,
  isNewThread,
  router,
  settings,
  setIsNewThread,
  setSettings,
  showNotification,
  t,
  threadId,
}: {
  autoContinue: boolean;
  continuationContext: Record<string, unknown> | undefined;
  continuationSourceState: AgentThreadState | undefined;
  continueFromThreadId?: string;
  isMock: boolean;
  isNewThread: boolean;
  router: ReturnType<typeof useRouter>;
  settings: ReturnType<typeof useLocalSettings>[0];
  setIsNewThread: (value: boolean) => void;
  setSettings: ReturnType<typeof useLocalSettings>[1];
  showNotification: ReturnType<typeof useNotification>["showNotification"];
  t: ReturnType<typeof useI18n>["t"];
  threadId: string;
}) {
  const autoContinuationRef = useRef<string | null>(null);
  const threadCreatedAtRef = useRef<number | null>(null);
  const routeSyncRef = useRef<string | null>(null);
  // Capture initial isNewThread to stabilize loadInitialState across re-renders.
  // When onStart fires setIsNewThread(false), loadInitialState must NOT flip
  // from false→true mid-stream, otherwise useStream reconnects and kills the
  // active SSE stream — causing the first message to get no reply.
  const initialIsNewRef = useRef(isNewThread);
  const activateThreadRoute = useCallback(
    (createdThreadId: string) => {
      threadCreatedAtRef.current ??= Date.now();
      setIsNewThread(false);

      if (routeSyncRef.current === createdThreadId) {
        return;
      }

      routeSyncRef.current = createdThreadId;
      const nextPath = `/workspace/chats/${createdThreadId}`;
      if (window.location.pathname !== nextPath) {
        history.replaceState(null, "", nextPath);
      }
    },
    [setIsNewThread],
  );

  const [thread, sendMessage] = useThreadStream({
    threadId: threadId,
    context: settings.context,
    isMock,
    loadInitialState: !initialIsNewRef.current,
    onStart: (createdThreadId) => {
      activateThreadRoute(createdThreadId);
      if (continuationSourceState && continueFromThreadId && !isMock) {
        const workflowEvents = [
          createWorkflowEvent(
            "workflow_continued",
            "Workflow continued from prior thread",
            `Resumed from ${continueFromThreadId}.`,
            "info",
          ),
          ...(continuationSourceState.workflow_events ?? []),
        ];
        getAPIClient()
          .threads.updateState(createdThreadId, {
            values: {
              continuation: {
                source_thread_id: continueFromThreadId,
                trigger: "continue",
                source_title: continuationSourceState.title,
                message_count: continuationSourceState.messages?.length ?? 0,
                workflow_count: continuationSourceState.workflows?.length ?? 0,
                continued_at: new Date().toISOString(),
              },
              runtime: continuationSourceState.runtime,
              workflows: continuationSourceState.workflows ?? [],
              workflow_events: workflowEvents,
            },
          })
          .catch(() => undefined);
      }
    },
    onFinish: (state) => {
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
      void sendMessage(threadId, message, continuationContext);
    },
    [continuationContext, sendMessage, threadId],
  );

  useEffect(() => {
    if (!isNewThread || !threadId || threadId === "new") {
      return;
    }

    if (thread.messages.length === 0 && !thread.isLoading) {
      return;
    }

    activateThreadRoute(threadId);
  }, [activateThreadRoute, isNewThread, thread.isLoading, thread.messages.length, threadId]);

  const handleStop = useCallback(async () => {
    await thread.stop();
  }, [thread]);

  useEffect(() => {
    if (
      !autoContinue
      || !isNewThread
      || !continuationSourceState
      || autoContinuationRef.current === threadId
      || thread.isLoading
    ) {
      return;
    }

    autoContinuationRef.current = threadId;
    const bootstrapMessage = buildContinuationBootstrapMessage(
      continuationSourceState,
    );
    void sendMessage(
      threadId,
      { text: bootstrapMessage, files: [] },
      continuationContext,
    ).catch((error) => {
      autoContinuationRef.current = null;
      const message = error instanceof Error ? error.message : "Failed to continue conversation automatically.";
      toast.error(message);
    });
  }, [
    autoContinue,
    continuationContext,
    continuationSourceState,
    isNewThread,
    sendMessage,
    thread.isLoading,
    threadId,
  ]);

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
      if (thread.messages.length > 0) return;
      // Don't redirect threads that were just created — the first checkpoint
      // may not have been written yet, causing a spurious 404.
      if (threadCreatedAtRef.current && Date.now() - threadCreatedAtRef.current < 15_000) return;
      toast.info("Chat session is no longer available. Starting fresh.");
      router.replace("/workspace/chats/new");
    }
  }, [thread.error, thread.isLoading, isNewThread, router, thread.messages.length]);

  return (
    <ThreadContext.Provider value={{ thread, isMock }}>
      <ChatBox isNewThread={isNewThread} mode={settings.context.mode} threadId={threadId}>
        <div className="relative flex size-full min-h-0 justify-between overflow-hidden">
          <div className="octo-grid pointer-events-none absolute inset-0 opacity-65" />
          <header
            className="absolute top-0 right-0 left-0 z-30 flex h-14 shrink-0 items-center px-5"
          >
            <div className="flex w-full items-center text-sm font-medium">
              <ThreadTitle isNewThread={isNewThread} threadId={threadId} thread={thread} />
            </div>
            <div>
              <ArtifactTrigger />
            </div>
          </header>
          <main className="relative flex min-h-0 max-w-full grow flex-col">
            <div className="flex size-full justify-center">
              <MessageList
                className="size-full px-4 pb-32 pt-12"
                threadId={threadId}
                thread={thread}
                emptyState={
                  isNewThread ? (
                    <Welcome
                      mode={settings.context.mode}
                      continuation={
                        continueFromThreadId && continuationSourceState
                          ? {
                              sourceTitle: continuationSourceState.title,
                              messageCount:
                                continuationSourceState.messages?.length ?? 0,
                              recentMessages: (
                                continuationSourceState.messages ?? []
                              )
                                .slice(-8)
                                .map((m) => ({
                                  role: m.type,
                                  content:
                                    typeof m.content === "string"
                                      ? m.content
                                      : "",
                                }))
                                .filter((m) => m.content.trim().length > 0),
                            }
                          : undefined
                      }
                    />
                  ) : undefined
                }
              />
            </div>
            <div className="absolute right-0 bottom-0 left-0 z-30 flex justify-center px-4 pb-5">
              <div
                className={cn(
                  "relative w-full",
                  isNewThread
                    ? "max-w-(--container-width-sm)"
                    : "max-w-(--container-width-md)",
                )}
              >
                <div className="absolute -top-4 right-0 left-0 z-0">
                  <div className="absolute right-0 bottom-0 left-0">
                    <TodoList
                      className="octo-panel"
                      todos={thread.values.todos ?? []}
                      hidden={
                        !thread.values.todos || thread.values.todos.length === 0
                      }
                    />
                  </div>
                </div>
                <InputBox
                  className={cn(
                    "octo-panel w-full rounded-[1.75rem]",
                    isNewThread ? "pb-2" : "",
                  )}
                  isNewThread={isNewThread}
                  threadId={threadId}
                  autoFocus={isNewThread}
                  status={thread.isLoading ? "streaming" : "ready"}
                  context={settings.context}
                  disabled={env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"}
                  onContextChange={(context) => setSettings("context", context)}
                  onSubmit={handleSubmit}
                  onStop={handleStop}
                />
                {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" && (
                  <div className="text-muted-foreground/67 w-full translate-y-12 text-center text-xs">
                    {t.common.notAvailableInDemoMode}
                  </div>
                )}
              </div>
            </div>
          </main>
        </div>
      </ChatBox>
    </ThreadContext.Provider>
  );
}
