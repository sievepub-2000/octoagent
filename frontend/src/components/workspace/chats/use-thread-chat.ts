"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { uuid } from "@/core/utils/uuid";

export function useThreadChat() {
  const { agent_name: agentNameFromPath, thread_id: threadIdFromPath } = useParams<{
    agent_name?: string;
    thread_id: string;
  }>();
  const searchParams = useSearchParams();
  const continueFromThreadId = searchParams.get("continue_from");
  const draftKey = searchParams.get("draft") ?? "";
  const isFreshRoute = searchParams.get("fresh") === "1";
  const isRouteNew = threadIdFromPath === "new" || isFreshRoute;
  const newThreadKeyRef = useRef<string | null>(null);

  const nextNewThreadKey = [
    agentNameFromPath ? `agent:${agentNameFromPath}` : "workspace",
    threadIdFromPath,
    continueFromThreadId ?? "",
    draftKey,
    isFreshRoute ? "fresh" : "new",
  ].join("::");

  // Mature chat products allocate a concrete conversation id before the first
  // user turn. Keep that id stable while the route is marked as fresh.
  const stableId = useRef<string | null>(null);
  if (!isRouteNew) {
    stableId.current = threadIdFromPath;
  } else if (threadIdFromPath !== "new") {
    stableId.current = threadIdFromPath;
    newThreadKeyRef.current = nextNewThreadKey;
  } else if (stableId.current === null && typeof window !== "undefined") {
    stableId.current = uuid();
    newThreadKeyRef.current = nextNewThreadKey;
  } else if (newThreadKeyRef.current !== nextNewThreadKey && typeof window !== "undefined") {
    stableId.current = uuid();
    newThreadKeyRef.current = nextNewThreadKey;
  }

  const [threadId, setThreadId] = useState(
    () => stableId.current ?? threadIdFromPath,
  );

  const [isNewThread, setIsNewThread] = useState(
    () => isRouteNew,
  );

  useEffect(() => {
    if (!isRouteNew) {
      stableId.current = threadIdFromPath;
      newThreadKeyRef.current = null;
      setThreadId((current) =>
        current === threadIdFromPath ? current : threadIdFromPath,
      );
      setIsNewThread(false);
      return;
    }

    if (threadIdFromPath !== "new") {
      stableId.current = threadIdFromPath;
      newThreadKeyRef.current = nextNewThreadKey;
      setThreadId((current) =>
        current === threadIdFromPath ? current : threadIdFromPath,
      );
      setIsNewThread(true);
      return;
    }

    const stableThreadId = stableId.current;
    if (newThreadKeyRef.current === null && stableThreadId) {
      newThreadKeyRef.current = nextNewThreadKey;
      setThreadId((current) =>
        current === stableThreadId ? current : stableThreadId,
      );
      setIsNewThread(true);
      return;
    }

    if (newThreadKeyRef.current === nextNewThreadKey && stableThreadId) {
      setThreadId((current) =>
        current === stableThreadId ? current : stableThreadId,
      );
      setIsNewThread(true);
      return;
    }

    const newId = uuid();
    stableId.current = newId;
    newThreadKeyRef.current = nextNewThreadKey;
    setThreadId(newId);
    setIsNewThread(true);
  }, [
    agentNameFromPath,
    continueFromThreadId,
    draftKey,
    isFreshRoute,
    isRouteNew,
    nextNewThreadKey,
    threadIdFromPath,
  ]);

  const isMock = searchParams.get("mock") === "true";
  return {
    threadId,
    isNewThread,
    isFreshRoute,
    setThreadId,
    setIsNewThread,
    isMock,
    continueFromThreadId,
  };
}
