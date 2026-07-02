"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { uuid } from "@/core/utils/uuid";

function currentThreadIdFromLocation() {
  if (typeof window === "undefined") return null;
  const match = window.location.pathname.match(/\/chats\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function useThreadChat() {
  const { agent_name: agentNameFromPath, thread_id: threadIdFromPath } = useParams<{
    agent_name?: string;
    thread_id: string;
  }>();
  const routeThreadId = currentThreadIdFromLocation() ?? threadIdFromPath ?? "new";
  const searchParams = useSearchParams();
  const continueFromThreadId = searchParams.get("continue_from");
  const draftKey = searchParams.get("draft") ?? "";
  const isFreshRoute = searchParams.get("fresh") === "1";
  const isRouteNew = routeThreadId === "new" || isFreshRoute;
  const newThreadKeyRef = useRef<string | null>(null);

  const nextNewThreadKey = [
    agentNameFromPath ? `agent:${agentNameFromPath}` : "workspace",
    routeThreadId,
    continueFromThreadId ?? "",
    draftKey,
    isFreshRoute ? "fresh" : "new",
  ].join("::");

  // Mature chat products allocate a concrete conversation id before the first
  // user turn. Keep that id stable while the route is marked as fresh.
  const stableId = useRef<string | null>(null);
  if (!isRouteNew) {
    stableId.current = routeThreadId;
  } else if (routeThreadId !== "new") {
    const hasServerCreatedFreshThread =
      isFreshRoute &&
      stableId.current &&
      newThreadKeyRef.current === nextNewThreadKey &&
      stableId.current !== routeThreadId;
    if (!hasServerCreatedFreshThread) {
      stableId.current = routeThreadId;
      newThreadKeyRef.current = nextNewThreadKey;
    }
  } else if (stableId.current === null && typeof window !== "undefined") {
    stableId.current = uuid();
    newThreadKeyRef.current = nextNewThreadKey;
  } else if (newThreadKeyRef.current !== nextNewThreadKey && typeof window !== "undefined") {
    stableId.current = uuid();
    newThreadKeyRef.current = nextNewThreadKey;
  }

  const [threadId, setThreadId] = useState(
    () => stableId.current ?? routeThreadId,
  );

  const [isNewThread, setIsNewThread] = useState(
    () => isRouteNew,
  );

  useEffect(() => {
    if (!isRouteNew) {
      stableId.current = routeThreadId;
      newThreadKeyRef.current = null;
      setThreadId((current) =>
        current === routeThreadId ? current : routeThreadId,
      );
      setIsNewThread(false);
      return;
    }

    if (routeThreadId !== "new") {
      const stableThreadId = stableId.current;
      if (
        isFreshRoute &&
        stableThreadId &&
        newThreadKeyRef.current === nextNewThreadKey &&
        stableThreadId !== routeThreadId
      ) {
        setThreadId((current) =>
          current === stableThreadId ? current : stableThreadId,
        );
        setIsNewThread(true);
        return;
      }

      stableId.current = routeThreadId;
      newThreadKeyRef.current = nextNewThreadKey;
      setThreadId((current) =>
        current === routeThreadId ? current : routeThreadId,
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
    routeThreadId,
  ]);

  const updateThreadId = useCallback((nextThreadId: string) => {
    stableId.current = nextThreadId;
    setThreadId(nextThreadId);
  }, []);

  const isMock = searchParams.get("mock") === "true";
  return {
    threadId,
    isNewThread,
    isFreshRoute,
    setThreadId: updateThreadId,
    setIsNewThread,
    isMock,
    continueFromThreadId,
  };
}
