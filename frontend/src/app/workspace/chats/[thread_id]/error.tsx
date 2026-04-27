"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";

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

  useEffect(() => {
    const isThreadGone = isRecoverableThreadMissingError(error);

    if (isThreadGone) {
      toast.info("Chat session is no longer available. Starting fresh.");
      router.replace("/workspace/chats/new");
    } else {
      // For unexpected errors, log and let the user retry
      console.error("[ChatThreadError]", error);
    }
  }, [error, router]);

  const isThreadGone = isRecoverableThreadMissingError(error);

  if (isThreadGone) {
    // Don't render anything — the useEffect will redirect
    return null;
  }

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
