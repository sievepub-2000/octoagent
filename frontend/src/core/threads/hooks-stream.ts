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

import {
  contextHandoffMatches,
  DEFAULT_STREAM_MODE,
  detectRecoverableIncompleteState,
  isDuplicateOptimisticHuman,
  isUnfinishedActionAnnouncement,
  lastMessage,
  MAX_PREPLAN_MESSAGE_CHARS,
  messageText,
  normalizeRuntimeMode,
  resolvePermissionMode,
  shouldEnableThinking,
} from "./hooks-utils";

// Thread stream hook wrapping langgraph-sdk useStream with thread-specific logic
export interface UseThreadStreamOptions {
  threadId: string;
  context?: Record<string, unknown>;
  isMock?: boolean;
  loadInitialState?: boolean;
  onStart?: (createdThreadId: string) => void;
  onRunEvent?: (event: RunEvent) => void;
  onFinish?: (state: Record<string, unknown>) => void;
}

export function useThreadStream(options: UseThreadStreamOptions): [any, (message: PromptInputMessage) => Promise<void>] {
  const {
    threadId,
    context = {},
    isMock = false,
    loadInitialState = true,
    onStart,
    onRunEvent,
    onFinish,
  } = options;

  const [thread, setThread] = useState(null);

  // Use langgraph-sdk useStream internally
  const streamResult = useStream({
    apiUrl: getLangGraphBaseURL(),
    threadId,
    streamMode: DEFAULT_STREAM_MODE as StreamMode,
    initialSnapshot: loadInitialState ? undefined : null,
    fetch: async (url, init) => {
      return fetch(url, init);
    },
  });

  useEffect(() => {
    if (streamResult.thread && onStart) {
      onStart(streamResult.thread.thread_id || threadId);
    }
  }, [streamResult.thread]);

  const handleSendMessage = useCallback(async (message: PromptInputMessage) => {
    if (!streamResult.sendMessage) return;
    
    pushSystemEvent({ type: "user_message", timestamp: new Date().toISOString() });
    
    await streamResult.sendMessage(message);
  }, [streamResult.sendMessage]);

  return [thread || streamResult.thread, handleSendMessage];
}