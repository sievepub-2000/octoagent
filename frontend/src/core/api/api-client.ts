"use client";

import { Client as LangGraphClient } from "@langchain/langgraph-sdk/client";

import { getLangGraphBaseURL } from "../config";

import { sanitizeRunStreamOptions } from "./stream-mode";

function createEmptyThreadState() {
  return {
    values: {},
    next: [],
    tasks: [],
    metadata: {},
    created_at: "",
    updated_at: "",
    config: {},
    checkpoint: null,
  };
}

const provisionalThreadIds = new Set<string>();

export function markThreadProvisional(threadId?: string | null) {
  if (!threadId) {
    return;
  }
  provisionalThreadIds.add(threadId);
}

export function markThreadPersisted(threadId?: string | null) {
  if (!threadId) {
    return;
  }
  provisionalThreadIds.delete(threadId);
}

/**
 * Check whether an error represents a 404 "thread not found" from the
 * LangGraph server.  The SDK's AsyncCaller wraps non-OK responses in an
 * HTTPError with a `.status` property; fall back to message matching.
 */
export function isRecoverableThreadMissingError(error: unknown): boolean {
  if (
    error &&
    typeof error === "object" &&
    "status" in error &&
    (error as { status: number }).status === 404
  ) {
    return true;
  }

  const msg = error instanceof Error ? error.message : String(error);
  const lower = msg.toLowerCase();
  if (lower.includes("run not found")) {
    return false;
  }

  return (
    lower.includes("filenotfounderror") ||
    lower.includes("file not found") ||
    lower.includes("no such file") ||
    lower.includes("enoent") ||
    lower.includes("404") ||
    (lower.includes("not found") && lower.includes("thread")) ||
    (lower.includes("internal error") && lower.includes("not found"))
  );
}

function isThread404(error: unknown): boolean {
  return isRecoverableThreadMissingError(error);
}

/**
 * Wrap every own method of `target` whose name matches `nameTest` so that
 * any HTTPError-404 containing "Thread…not found" resolves to `fallback()`
 * instead of rejecting.  This covers getState, getHistory, updateState,
 * patchState, delete, get — and any future methods the SDK adds.
 *
 * We intentionally patch at the *method* level (not the lower asyncCaller)
 * because different methods need different fallback return shapes, and the
 * method level is the narrowest spot we control without modifying
 * node_modules.
 */
function patchThread404<T extends object>(
  target: T,
  nameTest: (name: string) => boolean,
  fallbackFor: (name: string) => unknown,
): void {
  // Walk prototype chain to pick up inherited BaseClient methods too
  const seen = new Set<string>();

  let proto: any = target;
  while (proto && proto !== Object.prototype) {
    for (const name of Object.getOwnPropertyNames(proto)) {
      if (seen.has(name) || name === "constructor") continue;
      seen.add(name);

      const descriptor = Object.getOwnPropertyDescriptor(proto, name) as any;
      if (typeof descriptor?.value !== "function") continue;
      if (!nameTest(name)) continue;


      const orig = descriptor.value.bind(target) as (...args: unknown[]) => Promise<unknown>;
      const fb = fallbackFor(name);

      (target as any)[name] = async (...args: any[]) => {
        try {
          return await orig(...args);
        } catch (error: unknown) {
          if (isThread404(error)) return fb;
          throw error;
        }
      };
    }
    proto = Object.getPrototypeOf(proto);
  }
}

function createCompatibleClient(isMock?: boolean): LangGraphClient {
  const apiUrl = getLangGraphBaseURL(isMock);
  const client = new LangGraphClient({
    apiUrl,
  });

  const getJson = async <T>(path: string): Promise<T> => {
    const response = await fetch(`${apiUrl}${path}`);
    if (!response.ok) {
      const error = new Error(`HTTP ${response.status} for ${path}`) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }
    return response.json() as Promise<T>;
  };

  const originalRunStream = client.runs.stream.bind(client.runs);
  client.runs.stream = ((threadId, assistantId, payload) =>
    originalRunStream(
      threadId,
      assistantId,
      sanitizeRunStreamOptions(payload),
    )) as typeof client.runs.stream;

  const originalJoinStream = client.runs.joinStream.bind(client.runs);
  client.runs.joinStream = ((threadId, runId, options) =>
    originalJoinStream(
      threadId,
      runId,
      sanitizeRunStreamOptions(options),
    )) as typeof client.runs.joinStream;

  client.threads.getState = (async (threadId) => {
    if (provisionalThreadIds.has(threadId)) {
      return createEmptyThreadState();
    }
    return getJson(`/threads/${encodeURIComponent(threadId)}/state`);
  }) as typeof client.threads.getState;

  client.threads.getHistory = (async (threadId) => {
    if (provisionalThreadIds.has(threadId)) {
      return [];
    }
    return getJson(`/threads/${encodeURIComponent(threadId)}/history`);
  }) as typeof client.threads.getHistory;

  const originalUpdateState = client.threads.updateState.bind(client.threads);
  client.threads.updateState = (async (threadId, payload) => {
    if (provisionalThreadIds.has(threadId)) {
      return undefined;
    }
    return originalUpdateState(threadId, payload);
  }) as typeof client.threads.updateState;

  // ── Thread-404 safety patches ──────────────────────────────────────────
  //
  // Multiple code paths in the app (ChatBox workflow sync via
  // `void threads.updateState()`, the SDK's internal `useThreadHistory`
  // hook, etc.) call LangGraph SDK methods that go through AsyncCaller.
  // When the thread no longer exists (server restart, manual deletion),
  // AsyncCaller throws HTTPError(404) whose rejection is never caught,
  // surfacing as a Runtime Error in the Next.js dev overlay.
  //
  // The Next.js dev overlay registers its `unhandledrejection` listener
  // at module-load time (via handleGlobalErrors()) — before any
  // useEffect-based handler — and unconditionally captures the error.
  // So the ONLY reliable fix is to prevent the error from ever being
  // thrown, by wrapping every threads-client method that touches a
  // thread endpoint.

  patchThread404(
    client.threads,
    // Patch every mutating / reading method on ThreadsClient.
    // Skips 'create', 'search', 'count' which don't fetch a specific thread.
    (name) =>
      [
        "get",
        "copy",
        "update",
        "getState",
        "getHistory",
        "updateState",
        "patchState",
        "delete",
      ].includes(name),
    (name) => {
      if (name === "getHistory") return [];
      if (name === "getState") return createEmptyThreadState();
      // updateState, patchState, delete, get → return undefined (void result)
      return undefined;
    },
  );

  return client;
}

let _singleton: LangGraphClient | null = null;
export function getAPIClient(isMock?: boolean): LangGraphClient {
  _singleton ??= createCompatibleClient(isMock);
  return _singleton;
}
