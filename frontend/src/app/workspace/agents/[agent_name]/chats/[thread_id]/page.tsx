"use client";

import { PlusSquare } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { AgentAvatar } from "@/components/brand/octo-mark";
import { Button } from "@/components/ui/button";
import { AgentWelcome } from "@/components/workspace/agent-welcome";
import { ArtifactTrigger } from "@/components/workspace/artifacts";
import { ChatBox, useThreadChat } from "@/components/workspace/chats";
import { InputBox } from "@/components/workspace/input-box";
import { MessageList } from "@/components/workspace/messages";
import { ThreadContext } from "@/components/workspace/messages/context";
import { ThreadTitle } from "@/components/workspace/thread-title";
import { Tooltip } from "@/components/workspace/tooltip";
import { type Agent, useAgent } from "@/core/agents";
import { agentAvatarUrl, archiveAgentConversation } from "@/core/agents/api";
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

type ArchivedConversationMessage =
  Parameters<typeof archiveAgentConversation>[2]["messages"][number];

function buildAgentChatPath(
  agentName: string,
  threadSegment: string,
  options: {
    continueFromThreadId?: string;
    autoContinue?: boolean;
  } = {},
) {
  const search = new URLSearchParams();
  if (options.continueFromThreadId) {
    search.set("continue_from", options.continueFromThreadId);
  }
  if (options.autoContinue) {
    search.set("auto_continue", "1");
  }
  const query = search.toString();
  return `/workspace/agents/${encodeURIComponent(agentName)}/chats/${threadSegment}${query ? `?${query}` : ""}`;
}

function summarizeMessageContent(content: string, maxLength = 180) {
  const normalized = content.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength)}...`;
}

function buildContinuationBootstrapMessage(
  state: AgentThreadState,
  agentName: string,
): string {
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
    `这是为 agent ${agentName} 自动创建的续接对话，请无缝接续之前的工作，不要重新开始。`,
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

  lines.push("", "请基于以上摘要继续完成剩余工作，并沿用当前 agent 的身份设定与提示词。", "");
  return lines.join("\n");
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

  const { threadId, isNewThread, setIsNewThread, continueFromThreadId, autoContinue } =
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
      autoContinue={autoContinue}
      agent={agent}
      agent_name={agent_name}
      continuationContext={continuationContext}
      continuationSourceState={continuationSourceState}
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
  autoContinue,
  agent,
  agent_name,
  continuationContext,
  continuationSourceState,
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
  autoContinue: boolean;
  agent: Agent | null | undefined;
  agent_name: string;
  continuationContext: Record<string, unknown> | undefined;
  continuationSourceState: AgentThreadState | undefined;
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
  const autoContinuationRef = useRef<string | null>(null);
  const compactRedirectRef = useRef<string | null>(null);
  const archiveSignatureRef = useRef<string | null>(null);
  const routeSyncRef = useRef<string | null>(null);
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
      if (continuationSourceState && continueFromThreadId) {
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
      void sendMessage(threadId, message, {
        agent_name,
        ...continuationContext,
      });
    },
    [sendMessage, threadId, agent_name, continuationContext],
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
      router.replace(
        buildAgentChatPath(nextAgentName, "new", {
          autoContinue,
          continueFromThreadId,
        }),
      );
    },
    [agent_name, autoContinue, continueFromThreadId, isNewThread, router, setSettings, settings],
  );

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
      agent_name,
    );
    void sendMessage(
      threadId,
      { text: bootstrapMessage, files: [] },
      {
        agent_name,
        ...continuationContext,
      },
    ).catch((error) => {
      autoContinuationRef.current = null;
      const message = error instanceof Error ? error.message : "Failed to continue conversation automatically.";
      toast.error(message);
    });
  }, [
    agent_name,
    autoContinue,
    continuationContext,
    continuationSourceState,
    isNewThread,
    sendMessage,
    thread.isLoading,
    threadId,
  ]);

  useEffect(() => {
    const runtime = thread.values.runtime;
    const shouldContinue =
      !isNewThread
      && !continueFromThreadId
      && !thread.isLoading
      && (thread.messages.length ?? 0) >= 6
      && runtime?.context_pressure === "high"
      && runtime?.recommended_memory_action === "compact";
    if (!shouldContinue) {
      return;
    }
    if (compactRedirectRef.current === threadId) {
      return;
    }
    compactRedirectRef.current = threadId;
    router.push(
      buildAgentChatPath(agent_name, "new", {
        autoContinue: true,
        continueFromThreadId: threadId,
      }),
    );
  }, [
    agent_name,
    continueFromThreadId,
    isNewThread,
    router,
    thread.isLoading,
    thread.messages.length,
    thread.values.runtime,
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
      <ChatBox threadId={threadId}>
        <div className="relative flex size-full min-h-0 justify-between overflow-hidden">
          <div className="octo-grid pointer-events-none absolute inset-0 opacity-65" />
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
              <ArtifactTrigger />
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

          <main className="relative flex min-h-0 max-w-full grow flex-col">
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

            <div className="absolute right-0 bottom-0 left-0 z-30 flex justify-center px-4 pb-5">
              <div
                className={cn(
                  "relative w-full",
                  isNewThread
                    ? "max-w-(--container-width-sm)"
                    : "max-w-(--container-width-md)",
                )}
              >
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
                  activeModelName={thread.values.runtime?.active_model}
                  onContextChange={handleContextChange}
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
