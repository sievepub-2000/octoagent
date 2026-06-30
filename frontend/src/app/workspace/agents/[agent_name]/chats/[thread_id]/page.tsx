"use client";

import { PlusSquare } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { AgentAvatar } from "@/components/brand/octo-mark";
import { Button } from "@/components/ui/button";
import { AgentWelcome } from "@/components/workspace/agent-welcome";
import { ChatBox, useThreadChat } from "@/components/workspace/chats";
import { InputBox } from "@/components/workspace/input-box";
import { MessageList } from "@/components/workspace/messages";
import { ThreadContext } from "@/components/workspace/messages/context";
import { ThreadTitle } from "@/components/workspace/thread-title";
import { TodoList } from "@/components/workspace/todo-list";
import { Tooltip } from "@/components/workspace/tooltip";
import { type Agent, useAgent } from "@/core/agents";
import { agentAvatarUrl, archiveAgentConversation } from "@/core/agents/api";
import type { ContextTokenUsage } from "@/core/context/context-token-counter";
import { useI18n } from "@/core/i18n/hooks";
import { useNotification } from "@/core/notification/hooks";
import { useLocalSettings } from "@/core/settings";
import { buildContinuationContext } from "@/core/threads";
import { useThreadState, useThreadStream } from "@/core/threads/hooks";
import { textOfMessage } from "@/core/threads/utils";
import { useWorkflows } from "@/core/workflows";
import { env } from "@/env";
import { cn } from "@/lib/utils";

type ArchivedConversationMessage =
  Parameters<typeof archiveAgentConversation>[2]["messages"][number];

function buildAgentChatPath(
  agentName: string,
  threadSegment: string,
  options: {
    continueFromThreadId?: string;
  } = {},
) {
  const search = new URLSearchParams();
  if (options.continueFromThreadId) {
    search.set("continue_from", options.continueFromThreadId);
  }
  const query = search.toString();
  return `/workspace/agents/${encodeURIComponent(agentName)}/chats/${threadSegment}${query ? `?${query}` : ""}`;
}

export default function AgentChatPage() {
  const { t } = useI18n();
  const [settings, setSettings] = useLocalSettings();
  const router = useRouter();

  const [hydrated, setHydrated] = useState(false);
  useEffect(() => { setHydrated(true); }, []);

  const { agent_name, thread_id: rawThreadId } = useParams<{
    agent_name: string;
    thread_id: string;
  }>();

  const { threadId, isNewThread, setIsNewThread, continueFromThreadId } =
    useThreadChat();
  const { agent: routeAgent } = useAgent(agent_name);
  const { agent } = useAgent(agent_name);
  const { hydrate } = useWorkflows();
  const continuationHydratedRef = useRef(false);

  // Sync agent_name and agent's model into local settings when entering agent chat
  useEffect(() => {
    if (!agent_name) return;
    const needsAgentSync = settings.context.agent_name !== agent_name;
    const needsModelSync = routeAgent?.model && settings.context.model_name !== routeAgent.model;
    if (needsAgentSync || needsModelSync) {
      setSettings("context", {
        ...settings.context,
        agent_name,
        ...(routeAgent?.model ? { model_name: routeAgent.model } : {}),
      });
    }
  }, [agent_name, routeAgent?.model]); // eslint-disable-line react-hooks/exhaustive-deps

  const { showNotification } = useNotification();
  const { data: continuationSourceState } = useThreadState(
    continueFromThreadId,
    Boolean(isNewThread && continueFromThreadId),
  );
  const {
    data: existingThreadState,
    isVerifying: isExistingThreadVerifying,
  } = useThreadState(
    isNewThread ? null : threadId,
    Boolean(!isNewThread && threadId),
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

    return buildContinuationContext(continueFromThreadId, continuationSourceState);
  }, [continueFromThreadId, continuationSourceState, isNewThread]);

  // Only verify existence when the user navigated directly to a thread URL.
  // When transitioning from /new (thread just created), the first checkpoint
  // may not exist yet → GET /state returns 404 → false "expired" redirect.
  const missingExistingThread =
    rawThreadId !== "new" &&
    !isNewThread &&
    !isExistingThreadVerifying &&
    !existingThreadState;

  useEffect(() => {
    if (missingExistingThread) {
      toast.info("Chat session is no longer available. Starting fresh.");
      router.replace(`/workspace/agents/${agent_name}/chats/new`);
    }
  }, [agent_name, missingExistingThread, router]);

  if (!hydrated || (rawThreadId !== "new" && !isNewThread && isExistingThreadVerifying)) {
    return null;
  }

  if (missingExistingThread) {
    return null;
  }

  return (
    <AgentChatThreadView
      key={threadId}
      agent={agent}
      agent_name={agent_name}
      continuationContext={continuationContext}
      continueFromThreadId={continueFromThreadId ?? undefined}
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

function AgentChatThreadView({
  agent,
  agent_name,
  continuationContext,
  continueFromThreadId,
  isNewThread,
  router,
  settings,
  setIsNewThread,
  setSettings,
  showNotification,
  t,
  threadId,
}: {
  agent: Agent | null | undefined;
  agent_name: string;
  continuationContext: Record<string, unknown> | undefined;
  continueFromThreadId?: string;
  isNewThread: boolean;
  router: ReturnType<typeof useRouter>;
  settings: ReturnType<typeof useLocalSettings>[0];
  setIsNewThread: (value: boolean) => void;
  setSettings: ReturnType<typeof useLocalSettings>[1];
  showNotification: ReturnType<typeof useNotification>["showNotification"];
  t: ReturnType<typeof useI18n>["t"];
  threadId: string;
}) {
  const archiveSignatureRef = useRef<string | null>(null);
  const routeSyncRef = useRef<string | null>(null);
  const [pendingContinuationContext, setPendingContinuationContext] = useState<Record<string, unknown> | undefined>();
  const [contextCycleBaseTokens, setContextCycleBaseTokens] = useState(0);
  const agentAvatar = agent?.avatar ? agentAvatarUrl(agent_name) : null;
  // Capture initial isNewThread to stabilize loadInitialState across re-renders.
  // Prevents setIsNewThread(false) in onStart from flipping useStream options
  // mid-stream, which would kill the SSE connection for the first message.
  const initialIsNewRef = useRef(isNewThread);
  const activateThreadRoute = useCallback(
    (createdThreadId: string) => {
      setIsNewThread(false);

      if (routeSyncRef.current === createdThreadId) {
        return;
      }

      routeSyncRef.current = createdThreadId;
      const nextPath = buildAgentChatPath(agent_name, createdThreadId);
      if (`${window.location.pathname}${window.location.search}` !== nextPath) {
        history.replaceState(null, "", nextPath);
      }
    },
    [agent_name, setIsNewThread],
  );

  const [thread, sendMessage] = useThreadStream({
    threadId: threadId,
    context: { ...settings.context, agent_name },
    loadInitialState: !initialIsNewRef.current,
    onStart: (createdThreadId) => {
      activateThreadRoute(createdThreadId);
    },
    onFinish: (state) => {
      if (document.hidden || !document.hasFocus()) {
        let body = "Conversation finished";
        const lastMessage = state.messages[state.messages.length - 1];
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
      void sendMessage(threadId, message, {
        agent_name,
        ...hiddenContinuationContext,
      });
    },
    [agent_name, continuationContext, pendingContinuationContext, sendMessage, threadId],
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

  useEffect(() => {
    setContextCycleBaseTokens(Number(thread.values.runtime?.context_cycle_base_tokens ?? 0));
  }, [threadId, thread.values.runtime?.context_cycle_base_tokens]);

  const handleStop = useCallback(async () => {
    await thread.stop();
  }, [thread]);

  const handleContextThreshold = useCallback((usage: ContextTokenUsage) => {
    if (thread.isLoading) {
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
    console.info(`[octoagent] Agent context usage reached ${usage.percent}%; next turn will use hidden compaction context in-place.`);
  }, [isNewThread, thread.isLoading, thread.messages.length, thread.values, threadId]);

  const handleContextChange = useCallback(
    (nextContext: typeof settings.context) => {
      setSettings("context", nextContext);
      if (!isNewThread) {
        return;
      }
      const nextAgentName =
        typeof nextContext.agent_name === "string"
          ? nextContext.agent_name
          : agent_name;
      if (nextAgentName === agent_name) {
        return;
      }
      router.replace(buildAgentChatPath(nextAgentName, "new", { continueFromThreadId }));
    },
    [agent_name, continueFromThreadId, isNewThread, router, setSettings, settings],
  );

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
      toast.info("Chat session is no longer available. Starting fresh.");
      router.replace(`/workspace/agents/${agent_name}/chats/new`);
    }
  }, [thread.error, thread.isLoading, isNewThread, router, agent_name, thread.messages.length]);

  useEffect(() => {
    if (isNewThread || thread.isLoading || thread.messages.length === 0) {
      return;
    }
    const archivedMessages = thread.messages
      .map((message): ArchivedConversationMessage => {
        const role: ArchivedConversationMessage["role"] =
          message.type === "human"
            ? "user"
            : message.type === "ai"
              ? "assistant"
              : message.type === "tool"
                ? "tool"
                : "system";
        return {
          role,
          content: textOfMessage(message) ?? "",
          created_at: (() => {
            if (!(typeof message === "object" && message !== null && "created_at" in message)) {
              return undefined;
            }
            const createdAt = message.created_at;
            if (typeof createdAt === "string") {
              return createdAt;
            }
            if (typeof createdAt === "number") {
              return String(createdAt);
            }
            return undefined;
          })(),
        };
      })
      .filter((message) => message.content.trim().length > 0);
    if (archivedMessages.length === 0) {
      return;
    }
    const lastMessageId = thread.messages.at(-1)?.id ?? `count-${archivedMessages.length}`;
    const signature = [
      agent_name,
      threadId,
      archivedMessages.length,
      lastMessageId,
      thread.values.title ?? "",
    ].join("::");
    if (archiveSignatureRef.current === signature) {
      return;
    }
    archiveSignatureRef.current = signature;
    void archiveAgentConversation(agent_name, threadId, {
      title: thread.values.title ?? agent?.name ?? agent_name,
      updated_at: new Date().toISOString(),
      continuation: (thread.values.continuation as Record<string, unknown> | undefined) ?? null,
      messages: archivedMessages,
    }).catch((error) => {
      archiveSignatureRef.current = null;
      console.warn("Failed to archive agent conversation", error);
    });
  }, [
    agent?.name,
    agent_name,
    isNewThread,
    thread.isLoading,
    thread.messages,
    thread.values.continuation,
    thread.values.title,
    threadId,
  ]);

  return (
    <ThreadContext.Provider value={{ thread }}>
      <ChatBox contextModelName={typeof settings.context.model_name === "string" ? settings.context.model_name : undefined} isNewThread={isNewThread} mode={settings.context.mode} threadId={threadId}>
        <div className="relative flex size-full min-h-0 justify-between overflow-hidden">
          <div className="octo-grid pointer-events-none absolute inset-0 opacity-65" />
          <h1 className="sr-only">{isNewThread ? t.pages.newChat : thread.values.title}</h1>
          <header
            className={cn(
              "absolute top-0 right-0 left-0 z-30 flex h-14 shrink-0 items-center gap-2 px-5",
              isNewThread
                ? "bg-background/0 backdrop-blur-none"
                : "bg-background/65 shadow-[0_10px_40px_var(--emboss-shadow)] backdrop-blur-xl",
            )}
          >
            <div className="octo-panel flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1">
              <AgentAvatar avatarUrl={agentAvatar} size={18} />
              <span className="text-xs font-medium">
                {agent?.name ?? agent_name}
              </span>
            </div>

            <div className="flex w-full items-center text-sm font-medium">
              <ThreadTitle isNewThread={isNewThread} threadId={threadId} thread={thread} />
            </div>
            <div className="mr-4 flex items-center">
              <Tooltip content={t.agents.newChat}>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    router.push(buildAgentChatPath(agent_name, "new"));
                  }}
                >
                  <PlusSquare /> {t.agents.newChat}
                </Button>
              </Tooltip>
            </div>
          </header>

          <div className="relative flex min-h-0 max-w-full grow flex-col">
            <div className="flex size-full justify-center">
              <MessageList
                className={cn("size-full px-2 pb-32", !isNewThread && "pt-12")}
                emptyState={
                  isNewThread && thread.messages.length === 0 ? (
                    <AgentWelcome agent={agent} agentName={agent_name} />
                  ) : undefined
                }
                threadId={threadId}
                thread={thread}
              />
            </div>

            <div className="absolute right-0 bottom-0 left-0 z-30 flex justify-center px-3 pb-5 sm:px-4">
              <div className="relative w-full max-w-(--container-width-md)">
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
