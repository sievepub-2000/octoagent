import type { AIMessage, Message } from "@langchain/langgraph-sdk";
import type { ThreadsClient } from "@langchain/langgraph-sdk/client";
import { useStream } from "@langchain/langgraph-sdk/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";

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
import type { LocalSettings } from "../settings";
import { useUpdateSubtask } from "../tasks/context";
import type { UploadedFileInfo } from "../uploads";
import { uploadFiles } from "../uploads";
import { createWorkflowEvent, useWorkflows } from "../workflows";

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
  onToolEnd?: (event: ToolEndEvent) => void;
};

function resolvePermissionMode(
  mode: LocalSettings["context"]["mode"],
): "workspace" | "system" | "yolo" {
  if (mode === "ultra") {
    return "system";
  }
  return "workspace";
}

export function useThreadStream({
  threadId,
  context,
  isMock,
  loadInitialState = true,
  onStart,
  onFinish,
  onToolEnd,
}: ThreadStreamOptions) {
  const { t } = useI18n();
  // Track the thread ID that is currently streaming to handle thread changes during streaming
  const [onStreamThreadId, setOnStreamThreadId] = useState(() => threadId);
  // Ref to track current thread ID across async callbacks without causing re-renders,
  // and to allow access to the current thread id in onUpdateEvent
  const threadIdRef = useRef<string | null>(threadId ?? null);
  const startedRef = useRef(false);

  const listeners = useRef({
    onStart,
    onFinish,
    onToolEnd,
  });

  // Keep listeners ref updated with latest callbacks
  useEffect(() => {
    listeners.current = { onStart, onFinish, onToolEnd };
  }, [onStart, onFinish, onToolEnd]);

  useEffect(() => {
    const normalizedThreadId = threadId ?? null;
    threadIdRef.current = normalizedThreadId;
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
      console.error("[useThreadStream] Stream error:", error);
    },
    onCreated(meta) {
      handleStreamStart(meta.thread_id);
      setOnStreamThreadId(meta.thread_id);
    },
    onLangChainEvent(event) {
      if (event.event === "on_tool_end") {
        listeners.current.onToolEnd?.({
          name: event.name,
          data: event.data,
        });
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
        }
      }
    },
    onFinish(state) {
      listeners.current.onFinish?.(state.values);
      void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
    },
  });

  // Optimistic messages shown before the server stream responds
  const [optimisticMessages, setOptimisticMessages] = useState<Message[]>([]);
  // Track message count before sending so we know when server has responded
  const prevMsgCountRef = useRef(thread.messages.length);

  // Clear optimistic when server messages arrive (count increases)
  useEffect(() => {
    if (
      optimisticMessages.length > 0 &&
      thread.messages.length > prevMsgCountRef.current
    ) {
      setOptimisticMessages([]);
    }
  }, [thread.messages.length, optimisticMessages.length]);

  const sendMessage = useCallback(
    async (
      threadId: string,
      message: PromptInputMessage,
      extraContext?: Record<string, unknown>,
    ) => {
      const text = message.text.trim();

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

      // Notify the UI as soon as the thread exists server-side so the first
      // user message immediately leaves /new and binds the provisional thread
      // to its stable route.  The page components now freeze loadInitialState
      // on first render, so this no longer flips useStream options mid-flight.
      _handleOnStart(threadId);

      let uploadedFileInfo: UploadedFileInfo[] = [];
      let operationPlan: Awaited<ReturnType<typeof planQueryOperation>> | null = null;

      try {
        if (text) {
          try {
            operationPlan = await planQueryOperation({
              user_message: text,
              continuation_source:
                typeof extraContext?.continue_from_title === "string"
                  ? extraContext.continue_from_title
                  : typeof extraContext?.continue_from_thread_id === "string"
                    ? extraContext.continue_from_thread_id
                    : undefined,
              permission_mode: resolvePermissionMode(context.mode),
            });
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
              setOptimisticMessages((messages) => {
                if (messages.length > 1 && messages[0]) {
                  const humanMessage: Message = messages[0];
                  return [
                    {
                      ...humanMessage,
                      additional_kwargs: { files: uploadedFiles },
                    },
                    ...messages.slice(1),
                  ];
                }
                return messages;
              });
            }
          } catch (error) {
            console.error("Failed to upload files:", error);
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

        const buildSubmitOptions = (targetThreadId?: string | null) => {
          const permissionMode = resolvePermissionMode(context.mode);
          const mlInternProfile = resolveMlInternProfile({
            permissionMode,
            mode: "dialogue",
          });
          return {
            threadId: targetThreadId ?? undefined,
            streamSubgraphs: true,
            streamResumable: true,
            config: {
              recursion_limit: 1000,
            },
            context: {
              ...context,
              ...extraContext,
              ...buildMlInternThreadContext(mlInternProfile),
              client_command: operationPlan?.command,
              session_governance: operationPlan?.governance,
              permission_mode: permissionMode,
              thinking_enabled: context.mode !== "flash",
              is_plan_mode: context.mode === "pro" || context.mode === "ultra",
              subagent_enabled: context.mode === "ultra",
              thread_id: targetThreadId ?? undefined,
            },
          };
        };

        try {
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
            toast.info("Chat session was refreshed. Sending your message in a new chat.");

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
        setOptimisticMessages([]);
        throw error;
      }
    },
    [thread, _handleOnStart, t.uploads.uploadingFiles, context, queryClient],
  );

  // Merge thread with optimistic messages for display
  const mergedThread =
    optimisticMessages.length > 0
      ? ({
          ...thread,
          messages: [...thread.messages, ...optimisticMessages],
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
  const query = useQuery<AgentThreadState | undefined>({
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
      // and return `undefined` without ever throwing for missing threads.
      const base = getLangGraphBaseURL();
      const url = `${base}/threads/${encodeURIComponent(threadId)}/state`;
      const response = await fetch(url);
      if (!response.ok) {
        // 404 = thread genuinely missing; 500 = thread exists but state is
        // broken (e.g. error status after backend restart).  Both cases
        // return undefined so the caller can redirect gracefully instead of
        // TanStack Query entering an error state that blocks rendering.
        return undefined;
      }
      const state = await response.json();
      return state.values as AgentThreadState;
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
  const apiClient = getAPIClient();
  return useMutation({
    mutationFn: async ({ threadId }: { threadId: string }) => {
      await apiClient.threads.delete(threadId);
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
