import type { Message, StreamMode } from "@langchain/langgraph-sdk";
import { useStream } from "@langchain/langgraph-sdk/react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState } from "react";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { pushSystemEvent } from "@/core/system-events/store";

import { getLangGraphBaseURL } from "../config";
import type { RunEvent } from "../runtime/run-events";
import type { LocalSettings } from "../settings";

import { classifyDialogueRoute } from "./dialogue-routing";
import type { AgentThreadState } from "./types";

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

export interface UseThreadStreamOptions {
  threadId: string;
  projectId?: string | null;
  context?: Record<string, unknown>;
  isMock?: boolean;
  loadInitialState?: boolean;
  onStart?: (createdThreadId: string) => void;
  onRunEvent?: (event: RunEvent) => void;
  onFinish?: (state: AgentThreadState) => void;
}

type SendThreadMessage = (
  threadId: string,
  message: PromptInputMessage,
  context?: Record<string, unknown>,
) => Promise<void>;

const DEFAULT_STREAM_MODE: StreamMode[] = ["messages-tuple", "updates", "custom"];
const DEFAULT_ASSISTANT_ID = "lead_agent";

function invalidateThreadSearchQueries(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
}

function buildMessagePayload(message: PromptInputMessage, projectId?: string | null): Record<string, unknown> {
  return {
    ...(projectId ? { project_id: projectId } : {}),
    messages: [
      {
        type: "human",
        content: message.text,
        additional_kwargs: message.files.length > 0 ? { files: message.files } : {},
      },
    ],
  };
}

export function useThreadStream(options: UseThreadStreamOptions): [any, SendThreadMessage] {
  const {
    threadId,
    projectId,
    context = {},
    loadInitialState = true,
    onStart,
    onFinish,
  } = options;

  const queryClient = useQueryClient();
  const shouldLoadThreadHistory = loadInitialState && threadId !== "new";
  const [createdThreadId, setCreatedThreadId] = useState<string | null>(null);
  const effectiveThreadId = shouldLoadThreadHistory ? threadId : createdThreadId;
  const activeThreadIdRef = useRef<string | null>(effectiveThreadId);
  if (effectiveThreadId && activeThreadIdRef.current !== effectiveThreadId) {
    activeThreadIdRef.current = effectiveThreadId;
  }

  const handleThreadId = useCallback(
    (nextThreadId: string) => {
      activeThreadIdRef.current = nextThreadId;
      setCreatedThreadId(nextThreadId);
      onStart?.(nextThreadId);
      invalidateThreadSearchQueries(queryClient);
    },
    [onStart, queryClient],
  );

  const stream = useStream<AgentThreadState>({
    assistantId: DEFAULT_ASSISTANT_ID,
    apiUrl: getLangGraphBaseURL(),
    threadId: effectiveThreadId,
    onThreadId: handleThreadId,
    onFinish: (state) => {
      onFinish?.((state.values ?? {}) as AgentThreadState);
      invalidateThreadSearchQueries(queryClient);
    },
    fetchStateHistory: true,
    initialValues: loadInitialState ? undefined : null,
  });

  const thread = useMemo(() => {
    const values = (stream.values ?? {}) as AgentThreadState;
    const messages = ((stream.messages ?? values.messages ?? []) as Message[]);
    return {
      values,
      messages,
      isLoading: Boolean(stream.isLoading || stream.isThreadLoading),
      isThreadLoading: stream.isThreadLoading,
      error: stream.error,
      stop: stream.stop,
    };
  }, [stream]);

  const sendMessage = useCallback<SendThreadMessage>(
    async (targetThreadId, message, extraContext = {}) => {
      pushSystemEvent({
        level: "info",
        message: "Sending user message.",
        source: "session",
      });

      const submitThreadId = activeThreadIdRef.current ?? (
        shouldLoadThreadHistory && targetThreadId !== "new"
          ? targetThreadId
          : undefined
      );
      const route = classifyDialogueRoute({
        text: message.text,
        mode: typeof context.mode === "string" ? context.mode : undefined,
        hasFiles: message.files.length > 0,
      });
      const threadMessages = ((stream.messages ?? stream.values?.messages ?? []) as Message[]);

      await stream.submit(buildMessagePayload(message, projectId) as never, {
        context: {
          ...context,
          ...(projectId ? { project_id: projectId } : {}),
          ...extraContext,
          dialogue_text: message.text,
          last_user_message: message.text,
          dialogue_route: {
            kind: route.kind,
            reason: route.reason,
            needs_tools: route.needsTools,
            needs_memory: route.needsMemory,
            needs_deep_agent: route.needsDeepAgent,
          },
          has_files: message.files.length > 0,
          thread_message_count: threadMessages.length,
        },
        streamMode: DEFAULT_STREAM_MODE,
        threadId: submitThreadId,
      } as never);
    },
    [context, projectId, shouldLoadThreadHistory, stream],
  );

  return [thread, sendMessage];
}
