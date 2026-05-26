"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { isRecoverableThreadMissingError } from "@/core/api";

/**
 * Next.js error boundary for the chat thread route.
 *
 * Catches unhandled errors (e.g. useStream 404 when reconnecting to a
 * deleted thread) and redirects to a fresh chat instead of showing the
 * dev-mode Runtime Error overlay.
 */
export default function ChatThreadError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const router = useRouter();
  const isThreadGone = isRecoverableThreadMissingError(error);

  useEffect(() => {
    if (isThreadGone) {
      // 2026-05-16: Don't auto-redirect for historical conversations.
      // The thread data may still be available even if the LangGraph run
      // is gone. Log and let the user retry or navigate manually.
      console.info("[ChatThreadError] Thread checkpoint missing — historical view available via retry.", error.message);
    } else {
      // For unexpected errors, log and let the user retry
      console.error("[ChatThreadError]", error);
    }
  }, [error, isThreadGone, router]);

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
      <h2 className="text-lg font-semibold text-foreground">
        Something went wrong
      </h2>
      <p className="max-w-md text-sm text-muted-foreground">
        {error.message || "An unexpected error occurred."}
      </p>
      <button
        type="button"
        className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
        onClick={reset}
      >
        Try again
      </button>
    </div>
  );
}
