"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import {
  isChunkLoadFailure,
  recoverFromChunkLoadFailure,
} from "@/core/runtime/chunk-recovery";

export default function WorkspaceError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const isChunkError = isChunkLoadFailure(error.message) || isChunkLoadFailure(error.stack);

  useEffect(() => {
    recoverFromChunkLoadFailure(`${error.message}\n${error.stack ?? ""}`);
  }, [error.message, error.stack]);

  return (
    <div className="flex min-h-full items-center justify-center p-6">
      <section className="octo-panel w-full max-w-xl space-y-4 rounded-lg border p-6">
        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-foreground">
            {isChunkError ? "Workspace refreshed" : "Workspace could not load"}
          </h1>
          <p className="text-sm leading-6 text-muted-foreground">
            {isChunkError
              ? "A stale workspace bundle was detected after the local service restarted. OctoAgent is refreshing this page with the current build."
              : "The workspace page hit an unexpected error. Try reloading the route; if it repeats, check the runtime logs before continuing."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={reset}>Try again</Button>
          <Button variant="outline" onClick={() => window.location.reload()}>
            Reload page
          </Button>
        </div>
      </section>
    </div>
  );
}
