import type { Message } from "@langchain/langgraph-sdk";
import type { BaseStream } from "@langchain/langgraph-sdk/react";
import { ArrowDownIcon } from "lucide-react";
import type React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/core/i18n/hooks";
import {
  extractContentFromMessage,
  extractPresentFilesFromMessage,
  extractTextFromMessage,
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

/** Throttle streaming re-renders to at most once per STREAM_THROTTLE_MS. */
const STREAM_THROTTLE_MS = 50;

/**
 * During active streaming, batch message-list updates to max 20fps (50ms).
 * Returns un-throttled messages when streaming has stopped so the final
 * state renders immediately.
 *
 * KEY FIX: Use a callback + ref pattern to avoid creating new message array references
 * on every render, which would cause infinite update loops in effects that depend on messages.
 */
function useThrottledMessages(
  messages: Message[],
  isLoading: boolean,
) {
  const [flushed, setFlushed] = useState<Message[]>(messages);
  const messagesRef = useRef<Message[]>(messages);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Always keep ref in sync with latest messages
  messagesRef.current = messages;

  useEffect(() => {
    if (!isLoading) {
      // Not streaming — flush immediately so hydrated history and final
      // post-stream state both render at once.
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      setFlushed(messages);
      return;
    }

    // Streaming — schedule a single deferred flush; ignore subsequent
    // re-renders until that timer fires.  This throttles token-by-token
    // updates without dropping the final state (the !isLoading branch
    // above runs once streaming ends).
    if (timerRef.current != null) return;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      setFlushed(messagesRef.current);
    }, STREAM_THROTTLE_MS);
  }, [messages, isLoading]);

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
  const rehypePlugins = useRehypeSplitWordsIntoSpans(thread.isLoading);
  const updateSubtask = useUpdateSubtask();
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const [atBottom, setAtBottom] = useState(true);

  // Throttle streaming re-renders to STREAM_THROTTLE_MS
  const messages = useThrottledMessages(thread.messages, thread.isLoading);

  // Compute groups once per messages change (not per streaming token re-render)
  const groups = useMemo(
    () => groupMessages(messages, (g) => g),
    [messages],
  );

  // Keep subtask store in sync based on message stream, but do it in an
  // effect to avoid triggering state updates during render.
  useEffect(() => {
    for (const message of messages) {
      if (message.type === "ai") {
        for (const toolCall of message.tool_calls ?? []) {
          if (toolCall.name !== "task" || !toolCall.id) {
            continue;
          }
          const task: Subtask = {
            id: toolCall.id,
            subagent_type: toolCall.args.subagent_type,
            description: toolCall.args.description,
            prompt: toolCall.args.prompt,
            status: "in_progress",
          };
          updateSubtask(task);
        }
        continue;
      }

      if (message.type !== "tool") {
        continue;
      }

      const taskId = message.tool_call_id;
      if (!taskId) {
        continue;
      }

      const result = extractTextFromMessage(message);
      if (result.startsWith("Task Succeeded. Result:")) {
        updateSubtask({
          id: taskId,
          status: "completed",
          result: result.split("Task Succeeded. Result:")[1]?.trim(),
        });
      } else if (result.startsWith("Task failed.")) {
        updateSubtask({
          id: taskId,
          status: "failed",
          error: result.split("Task failed.")[1]?.trim(),
        });
      } else if (result.startsWith("Task timed out")) {
        updateSubtask({
          id: taskId,
          status: "failed",
          error: result,
        });
      } else {
        updateSubtask({
          id: taskId,
          status: "in_progress",
        });
      }
    }
  }, [messages, updateSubtask]);

  const renderGroup = useCallback(
    (_index: number, group: MessageGroup): React.ReactNode => {
      const itemClass = "mx-auto w-full max-w-(--container-width-md) px-0 pb-8";
      if (group.type === "human" || group.type === "assistant") {
        return (
          <div className={itemClass}>
            <div className="flex flex-col gap-8" key={group.id}>
              {group.messages.map((msg) => (
                <MessageListItem
                  key={`${group.id}/${msg.id}`}
                  message={msg}
                  isLoading={thread.isLoading}
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
          const taskIds = message.tool_calls?.map(
            (toolCall) => toolCall.id,
          );
          for (const taskId of taskIds ?? []) {
            results.push(
              <SubtaskCard
                key={"task-group-" + taskId}
                taskId={taskId!}
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
    [thread.isLoading, rehypePlugins, threadId, t],
  );

  if (thread.isThreadLoading && messages.length === 0) {
    return <MessageListSkeleton />;
  }

  // Avoid mounting Virtuoso for an empty thread. In this state we only need
  // the welcome view, and skipping Virtuoso prevents layout-store feedback
  // loops observed on initial /workspace/chats/new renders.
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
          onClick={() => virtuosoRef.current?.scrollToIndex({ index: "LAST", behavior: "smooth" })}
        >
          <ArrowDownIcon className="h-4 w-4" />
        </Button>
      )}
      <Virtuoso
        ref={virtuosoRef}
        data={groups}
        itemContent={renderGroup}
        followOutput="auto"
        atBottomStateChange={setAtBottom}
        className="flex-1"
        style={{ height: "100%" }}
        increaseViewportBy={{ top: 400, bottom: 400 }}
        components={{
          Header: emptyState
            ? () => <div className="pt-12">{emptyState}</div>
            : () => <div className="pt-12" />,
          Footer: () => (
            <>
              {thread.isLoading && <StreamingIndicator className="my-4 mx-auto w-full max-w-(--container-width-md) px-0" />}
              <div style={{ height: `${paddingBottom}px` }} />
            </>
          ),
        }}
      />
    </div>
  );
}
