import type { Message, StreamMode } from "@langchain/langgraph-sdk";
import { useStream } from "@langchain/langgraph-sdk/react";
import { useCallback, useMemo } from "react";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { pushSystemEvent } from "@/core/system-events/store";

import { getLangGraphBaseURL } from "../config";
import type { LocalSettings } from "../settings";
import type { RunEvent } from "../runtime/run-events";
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

function buildMessagePayload(message: PromptInputMessage): Record<string, unknown> {
  return {
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
    context = {},
    loadInitialState = true,
    onStart,
    onFinish,
  } = options;

  const shouldLoadThreadHistory = loadInitialState && threadId !== "new";

  const stream = useStream<AgentThreadState>({
    assistantId: DEFAULT_ASSISTANT_ID,
    apiUrl: getLangGraphBaseURL(),
    threadId: shouldLoadThreadHistory ? threadId : null,
    onThreadId: onStart,
    onFinish: (state) => {
      onFinish?.((state.values ?? {}) as AgentThreadState);
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

      await stream.submit(buildMessagePayload(message) as never, {
        context: {
          ...context,
          ...extraContext,
        },
        streamMode: DEFAULT_STREAM_MODE,
        threadId: shouldLoadThreadHistory && targetThreadId !== "new"
          ? targetThreadId
          : undefined,
      } as never);
    },
    [context, shouldLoadThreadHistory, stream],
  );

  return [thread, sendMessage];
}
