import type { Thread } from "@langchain/langgraph-sdk";
import type { ThreadsClient } from "@langchain/langgraph-sdk/client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getAPIClient } from "@/core/api/api-client";
import { deleteJSON } from "@/core/api/http";
import { getLangGraphBaseURL } from "@/core/config";
import type { AgentThread, AgentThreadState } from "@/core/threads/types";

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
  const query = useQuery<AgentThreadState | null>({
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
      // and return `null` without ever throwing for missing threads.
      const base = getLangGraphBaseURL();
      const url = `${base}/threads/${encodeURIComponent(threadId)}/state`;
      const response = await fetch(url);
      if (!response.ok) {
        // 404 = thread genuinely missing; 500 = thread exists but state is
        // broken (e.g. error status after backend restart).  Both cases
        // return null so the caller can redirect gracefully instead of
        // TanStack Query entering an error state that blocks rendering.
        return null;
      }
      const state = await response.json();
      return state.values as AgentThreadState | null;
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
  return useMutation({
    mutationFn: async ({ threadId }: { threadId: string }) => {
      await deleteJSON(
        `/api/runtime/langgraph-contract/threads/${encodeURIComponent(threadId)}`,
      );
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
