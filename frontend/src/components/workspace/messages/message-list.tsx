import type { Message } from "@langchain/langgraph-sdk";
import type { BaseStream } from "@langchain/langgraph-sdk/react";
import { ArrowDownIcon } from "lucide-react";
import type React from "react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/core/i18n/hooks";
import {
  extractContentFromMessage,
  extractPresentFilesFromMessage,
  groupMessages,
  hasContent,
  hasPresentFiles,
  hasReasoning,
} from "@/core/messages/utils";
import type { MessageGroup } from "@/core/messages/utils";
import { useRehypeSplitWordsIntoSpans } from "@/core/rehype";
import type { Subtask } from "@/core/tasks";
import { useUpdateSubtask } from "@/core/tasks/context";
import type { AgentThreadState } from "@/core/threads";
import { cn } from "@/lib/utils";

import { ArtifactFileList } from "../artifacts/artifact-file-list";
import { StreamingIndicator } from "../streaming-indicator";

import { MarkdownContent } from "./markdown-content";
import { MessageGroup as MessageGroupComponent } from "./message-group";
import { MessageListItem } from "./message-list-item";
import { MessageListSkeleton } from "./skeleton";
import { SubtaskCard } from "./subtask-card";
import { collectSubtaskUpdates, getTaskToolCallIds } from "./subtask-sync";

/** Keep live text smooth without re-rendering more often than a 30fps frame budget. */
const STREAM_THROTTLE_MS = 33;
const ACTIVE_GROUP_WINDOW = 40;
const HISTORY_GROUP_WINDOW = 90;

/**
 * During active streaming, batch message-list updates to max 20fps (50ms).
 * Returns un-throttled messages when streaming has stopped so the final
 * state renders immediately.
 *
 * KEY FIX: Use a callback + ref pattern to avoid creating new message array references
 * on every render, which would cause infinite update loops in effects that depend on messages.
 */
function messagesSignature(messages: Message[]): string {
  // Cheap fingerprint that changes only when the visible content changes.
  // Avoids triggering effects on every re-render when the SDK creates a
  // new array reference for the same messages.
  let lastContentLen = 0;
  const last = messages[messages.length - 1];
  if (last) {
    if (typeof last.content === "string") {
      lastContentLen = last.content.length;
    } else if (Array.isArray(last.content)) {
      for (const part of last.content) {
        if (part && typeof part === "object" && "text" in part && typeof (part as { text: unknown }).text === "string") {
          lastContentLen += ((part as { text: string }).text).length;
        }
      }
    }
  }
  return `${messages.length}:${last?.id ?? ""}:${lastContentLen}`;
}

function useThrottledMessages(
  messages: Message[],
  isLoading: boolean,
) {
  const [flushed, setFlushed] = useState<Message[]>(messages);
  const messagesRef = useRef<Message[]>(messages);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSigRef = useRef<string>(messagesSignature(messages));

  // Always keep ref in sync with latest messages.
  messagesRef.current = messages;

  const signature = messagesSignature(messages);

  useEffect(() => {
    if (signature === lastSigRef.current) {
      // Same content AND same array reference — nothing to flush.
      return;
    }

    if (!isLoading) {
      // Not streaming — flush immediately so hydrated history and final
      // post-stream state both render at once.
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      lastSigRef.current = signature;
      setFlushed(messagesRef.current);
      return;
    }

    // Streaming — schedule a single deferred flush; ignore subsequent
    // re-renders until that timer fires.  This throttles token-by-token
    // updates without dropping the final state (the !isLoading branch
    // above runs once streaming ends).
    if (timerRef.current != null) return;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      lastSigRef.current = messagesSignature(messagesRef.current);
      setFlushed(messagesRef.current);
    }, STREAM_THROTTLE_MS);
  }, [signature, isLoading]);

  // Clean up any pending timer on unmount.
  useEffect(() => () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  return flushed;
}

export function MessageList({
  className,
  threadId,
  thread,
  paddingBottom = 160,
  emptyState,
}: {
  className?: string;
  threadId: string;
  thread: BaseStream<AgentThreadState>;
  paddingBottom?: number;
  emptyState?: React.ReactNode;
}) {
  const { t } = useI18n();
  const rehypePlugins = useRehypeSplitWordsIntoSpans(false);
  const updateSubtask = useUpdateSubtask();
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const scrollContentRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const lastScrollHeightRef = useRef(0);
  const [atBottom, setAtBottom] = useState(true);
  const [historyGroupLimit, setHistoryGroupLimit] = useState(HISTORY_GROUP_WINDOW);

  // Throttle streaming re-renders to STREAM_THROTTLE_MS
  const messages = useThrottledMessages(thread.messages, thread.isLoading);
  const liveAssistantMessageId = useMemo(() => {
    if (!thread.isLoading) return undefined;
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message?.type === "ai") return message.id;
    }
    return undefined;
  }, [messages, thread.isLoading]);
  const scrollContentSignature = useMemo(
    () => messagesSignature(messages),
    [messages],
  );

  // Compute groups once per messages change (not per streaming token re-render)
  const groups = useMemo(
    () => groupMessages(messages, (g) => g),
    [messages],
  );
  const renderWindowSize = thread.isLoading
    ? ACTIVE_GROUP_WINDOW
    : historyGroupLimit;
  const hiddenGroupCount =
    groups.length > renderWindowSize
      ? groups.length - renderWindowSize
      : 0;
  const visibleGroups = useMemo(
    () => (hiddenGroupCount > 0 ? groups.slice(hiddenGroupCount) : groups),
    [groups, hiddenGroupCount],
  );

  const groupsRef = useRef(groups);
  useEffect(() => {
    groupsRef.current = groups;
  }, [groups]);

  useEffect(() => {
    setHistoryGroupLimit(HISTORY_GROUP_WINDOW);
    stickToBottomRef.current = true;
    lastScrollHeightRef.current = 0;
    setAtBottom(true);
  }, [threadId]);

  // Keep subtask store in sync based on message stream, but do it in an
  // effect to avoid triggering state updates during render.
  const subtaskSignature = useMemo(() => {
    const ids: string[] = [];
    for (const message of messages) {
      if (message.type !== "ai") continue;
      for (const toolCall of message.tool_calls ?? []) {
        if (toolCall.name === "task" && toolCall.id) ids.push(toolCall.id);
      }
    }
    return ids.join("|");
  }, [messages]);

  useEffect(() => {
    for (const update of collectSubtaskUpdates(messages)) {
      updateSubtask(update);
    }
  }, [messages, subtaskSignature, updateSubtask]);

  const renderGroup = useCallback(
    (_index: number, group: MessageGroup): React.ReactNode => {
      const itemClass =
        "mx-auto w-full max-w-(--container-width-md) px-0 pb-8 [contain-intrinsic-size:1px_180px] [content-visibility:auto]";
      if (group.type === "human" || group.type === "assistant") {
        return (
          <div className={itemClass}>
            <div className="flex flex-col gap-8" key={group.id}>
              {group.messages.map((msg) => (
                <MessageListItem
                  key={`${group.id}/${msg.id}`}
                  message={msg}
                  isLoading={thread.isLoading}
                  isLiveStreaming={Boolean(liveAssistantMessageId && msg.id === liveAssistantMessageId)}
                />
              ))}
            </div>
          </div>
        );
      } else if (group.type === "assistant:clarification") {
        const message = group.messages[0];
        if (message && hasContent(message)) {
          return (
            <div className={itemClass}>
              <MarkdownContent
                key={group.id}
                content={extractContentFromMessage(message)}
                isLoading={thread.isLoading}
                rehypePlugins={rehypePlugins}
              />
            </div>
          );
        }
        return null;
      } else if (group.type === "assistant:present-files") {
        const files: string[] = [];
        for (const message of group.messages) {
          if (hasPresentFiles(message)) {
            const presentFiles = extractPresentFilesFromMessage(message);
            files.push(...presentFiles);
          }
        }
        return (
          <div className={itemClass}>
            <div className="w-full" key={group.id}>
              {group.messages[0] && hasContent(group.messages[0]) && (
                <MarkdownContent
                  content={extractContentFromMessage(group.messages[0])}
                  isLoading={thread.isLoading}
                  rehypePlugins={rehypePlugins}
                  className="mb-4"
                />
              )}
              <ArtifactFileList files={files} threadId={threadId} />
            </div>
          </div>
        );
      } else if (group.type === "assistant:subagent") {
        const tasks = new Set<Subtask>();
        for (const message of group.messages) {
          if (message.type === "ai") {
            for (const toolCall of message.tool_calls ?? []) {
              if (toolCall.name === "task") {
                const task: Subtask = {
                  id: toolCall.id!,
                  subagent_type: toolCall.args.subagent_type,
                  description: toolCall.args.description,
                  prompt: toolCall.args.prompt,
                  status: "in_progress",
                };
                tasks.add(task);
              }
            }
          }
        }
        const results: React.ReactNode[] = [];
        for (const message of group.messages.filter(
          (message) => message.type === "ai",
        )) {
          if (hasReasoning(message)) {
            results.push(
              <MessageGroupComponent
                key={"thinking-group-" + message.id}
                messages={[message]}
                isLoading={thread.isLoading}
              />,
            );
          }
          results.push(
            <div
              key="subtask-count"
              className="text-muted-foreground font-norma pt-2 text-sm"
            >
              {t.subtasks.executing(tasks.size)}
            </div>,
          );
          for (const taskId of getTaskToolCallIds(message)) {
            results.push(
              <SubtaskCard
                key={"task-group-" + taskId}
                taskId={taskId}
                isLoading={thread.isLoading}
              />,
            );
          }
        }
        return (
          <div className={itemClass}>
            <div
              key={"subtask-group-" + group.id}
              className="relative z-1 flex flex-col gap-2"
            >
              {results}
            </div>
          </div>
        );
      }
      return (
        <div className={itemClass}>
          <MessageGroupComponent
            key={"group-" + group.id}
            messages={group.messages}
            isLoading={thread.isLoading}
          />
        </div>
      );
    },
    [thread.isLoading, liveAssistantMessageId, rehypePlugins, threadId, t],
  );

  const handleScroll = useCallback(() => {
    const element = scrollContainerRef.current;
    if (!element) {
      return;
    }
    const distanceFromBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    const nextAtBottom = distanceFromBottom < 80;
    const scrollHeightChanged =
      element.scrollHeight !== lastScrollHeightRef.current;
    if (scrollHeightChanged && stickToBottomRef.current) {
      lastScrollHeightRef.current = element.scrollHeight;
      element.scrollTo({ top: element.scrollHeight, behavior: "auto" });
      setAtBottom((previous) => (previous ? previous : true));
      return;
    }

    // Auto-load older history when the user scrolls near the top. Preserves
    // the current visual anchor by capturing scroll height before the React
    // commit and restoring scrollTop after it. This mirrors how VS Code /
    // Slack lazily mount older virtualised messages.
    if (element.scrollTop < 240) {
      // Defer until the next paint so we use the freshest state value.
      window.requestAnimationFrame(() => {
        const beforeHeight = element.scrollHeight;
        const beforeTop = element.scrollTop;
        const expand = () => {
          requestAnimationFrame(() => {
            const afterHeight = element.scrollHeight;
            const delta = afterHeight - beforeHeight;
            if (delta > 0) {
              element.scrollTop = beforeTop + delta;
              lastScrollHeightRef.current = element.scrollHeight;
            }
          });
        };
        setHistoryGroupLimit((current) => {
          if (current >= groupsRef.current.length) return current;
          expand();
          return Math.min(current + HISTORY_GROUP_WINDOW, groupsRef.current.length);
        });
      });
    }

    lastScrollHeightRef.current = element.scrollHeight;
    stickToBottomRef.current = nextAtBottom;
    setAtBottom((previous) =>
      previous === nextAtBottom ? previous : nextAtBottom,
    );
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const element = scrollContainerRef.current;
    if (!element) {
      return;
    }
    stickToBottomRef.current = true;
    lastScrollHeightRef.current = element.scrollHeight;
    setAtBottom((previous) => (previous ? previous : true));
    element.scrollTo({
      top: element.scrollHeight,
      behavior,
    });
  }, []);

  useEffect(() => {
    if (!atBottom && !stickToBottomRef.current) {
      return;
    }
    scrollToBottom("auto");
    const frame = window.requestAnimationFrame(() => scrollToBottom("auto"));
    return () => window.cancelAnimationFrame(frame);
  }, [
    atBottom,
    scrollContentSignature,
    scrollToBottom,
    thread.isLoading,
    visibleGroups.length,
  ]);

  useEffect(() => {
    const contentElement = scrollContentRef.current;
    if (!contentElement || typeof ResizeObserver === "undefined") {
      return;
    }

    let frame: number | null = null;
    const scheduleScroll = () => {
      if (!stickToBottomRef.current) {
        return;
      }
      if (frame !== null) {
        window.cancelAnimationFrame(frame);
      }
      frame = window.requestAnimationFrame(() => {
        frame = null;
        scrollToBottom("auto");
      });
    };

    const observer = new ResizeObserver(scheduleScroll);
    observer.observe(contentElement);
    return () => {
      if (frame !== null) {
        window.cancelAnimationFrame(frame);
      }
      observer.disconnect();
    };
  }, [messages.length, scrollToBottom]);

  if (thread.isThreadLoading && messages.length === 0) {
    return <MessageListSkeleton />;
  }

  // Empty threads only need the welcome view; keeping this path minimal avoids
  // layout feedback loops during initial /workspace/chats/new renders.
  if (messages.length === 0 && emptyState) {
    return (
      <div className={cn("relative flex size-full flex-col", className)}>
        <div className="flex-1 overflow-y-auto">
          <div className="pt-12">{emptyState}</div>
          {thread.isLoading && (
            <StreamingIndicator className="my-4 mx-auto w-full max-w-(--container-width-md) px-0" />
          )}
          <div style={{ height: `${paddingBottom}px` }} />
        </div>
      </div>
    );
  }

  return (
    <div className={cn("relative flex size-full flex-col", className)}>
      {/* Scroll-to-bottom button */}
      {!atBottom && (
        <Button
          variant="secondary"
          size="icon"
          className="absolute bottom-6 right-6 z-10 rounded-full shadow-md"
          onClick={() => scrollToBottom("smooth")}
        >
          <ArrowDownIcon className="h-4 w-4" />
        </Button>
      )}
      <div
        ref={scrollContainerRef}
        data-chat-scroll-container="true"
        className="flex-1 overflow-y-auto"
        onScroll={handleScroll}
      >
        <div ref={scrollContentRef}>
          <div className="pt-12">{emptyState}</div>
          {hiddenGroupCount > 0 && (
          <div className="mx-auto w-full max-w-(--container-width-md) px-0 pb-6">
            <Button
              variant="ghost"
              size="sm"
              className="w-full text-muted-foreground"
              onClick={() =>
                setHistoryGroupLimit((current) =>
                  Math.min(current + HISTORY_GROUP_WINDOW, groups.length),
                )
              }
            >
              显示更早消息 ({hiddenGroupCount})
            </Button>
          </div>
        )}
          {visibleGroups.map((group, index) => (
            <div key={group.id}>{renderGroup(index, group)}</div>
          ))}
          {thread.isLoading && (
            <StreamingIndicator className="my-4 mx-auto w-full max-w-(--container-width-md) px-0" />
          )}
          <div style={{ height: `${paddingBottom}px` }} />
        </div>
      </div>
    </div>
  );
}
