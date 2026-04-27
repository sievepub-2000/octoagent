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
  const autoContinue = searchParams.get("auto_continue") === "1";
  const newThreadKeyRef = useRef<string | null>(null);

  // Keep a stable provisional UUID for optimistic state, uploads, and the
  // eventual first submit while the page is still on /new.
  const stableId = useRef<string | null>(null);
  if (threadIdFromPath !== "new") {
    stableId.current = threadIdFromPath;
  } else if (stableId.current === null && typeof window !== "undefined") {
    stableId.current = uuid();
  }

  const [threadId, setThreadId] = useState(
    () => stableId.current ?? threadIdFromPath,
  );

  const [isNewThread, setIsNewThread] = useState(
    () => threadIdFromPath === "new",
  );

  useEffect(() => {
    if (threadIdFromPath !== "new") {
      stableId.current = threadIdFromPath;
      newThreadKeyRef.current = null;
      setThreadId((current) =>
        current === threadIdFromPath ? current : threadIdFromPath,
      );
      setIsNewThread(false);
      return;
    }

    // The visible URL can be rewritten from /new to /<thread-id> before
    // Next updates route params. Using pathname here would create a second
    // provisional UUID for the same logical draft thread.
    const nextNewThreadKey = [
      agentNameFromPath ? `agent:${agentNameFromPath}` : "workspace",
      continueFromThreadId ?? "",
      autoContinue ? "1" : "0",
    ].join("::");

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
    autoContinue,
    continueFromThreadId,
    threadIdFromPath,
  ]);

  const isMock = searchParams.get("mock") === "true";
  return {
    threadId,
    isNewThread,
    setIsNewThread,
    isMock,
    continueFromThreadId,
    autoContinue,
  };
}
