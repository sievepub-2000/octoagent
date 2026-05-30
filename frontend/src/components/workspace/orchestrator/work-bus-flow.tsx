"use client";

import {
  ActivityIcon,
  CheckCircle2Icon,
  CircleIcon,
  Loader2Icon,
  XCircleIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { getBackendBaseURL } from "@/core/config";
import { env } from "@/env";
import { cn } from "@/lib/utils";

type WorkBusEvent = {
  event_id: string;
  thread_id: string;
  plan_id?: string | null;
  step_id?: string | null;
  kind: string;
  status?: string | null;
  title?: string | null;
  detail?: string | null;
  role?: string | null;
  tool_name?: string | null;
  duration_ms?: number | null;
  created_at?: string | null;
  sequence?: number | null;
};

type SocketEnvelope =
  | { type: "snapshot"; events?: WorkBusEvent[] }
  | { type: "event"; event?: WorkBusEvent }
  | { type: "heartbeat" };

function buildWorkBusSocketURL(threadId: string) {
  if (typeof window === "undefined") {
    return null;
  }
  if (env.NEXT_PUBLIC_WORKBUS_LIVE_ENABLED !== "true") {
    return null;
  }
  const baseURL = getBackendBaseURL() || window.location.origin;
  const url = new URL(`/api/workflows/live/${encodeURIComponent(threadId)}`, baseURL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

function statusTone(status?: string | null) {
  if (status === "completed") {
    return "text-emerald-500";
  }
  if (status === "failed" || status === "blocked") {
    return "text-destructive";
  }
  if (status === "running") {
    return "text-sky-500";
  }
  return "text-muted-foreground";
}

function StepStatusIcon({ status }: { status?: string | null }) {
  if (status === "completed") {
    return <CheckCircle2Icon className="size-3.5 text-emerald-500" />;
  }
  if (status === "failed" || status === "blocked") {
    return <XCircleIcon className="size-3.5 text-destructive" />;
  }
  if (status === "running") {
    return <Loader2Icon className="size-3.5 animate-spin text-sky-500" />;
  }
  return <CircleIcon className="size-3.5 text-muted-foreground" />;
}

function latestStepEvents(events: WorkBusEvent[]) {
  const byStep = new Map<string, WorkBusEvent>();
  for (const event of events) {
    if (!event.step_id) {
      continue;
    }
    const previous = byStep.get(event.step_id);
    if (!previous || (event.sequence ?? 0) >= (previous.sequence ?? 0)) {
      byStep.set(event.step_id, event);
    }
  }
  return [...byStep.values()].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
}

export function WorkBusFlow({ threadId }: { threadId: string }) {
  const [events, setEvents] = useState<WorkBusEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const url = buildWorkBusSocketURL(threadId);
    if (!url) {
      return;
    }

    let closed = false;
    const socket = new WebSocket(url);
    socket.onopen = () => setConnected(true);
    socket.onclose = () => {
      if (!closed) {
        setConnected(false);
      }
    };
    socket.onerror = () => setConnected(false);
    socket.onmessage = (message) => {
      try {
        const envelope = JSON.parse(String(message.data)) as SocketEnvelope;
        if (envelope.type === "snapshot") {
          setEvents(envelope.events ?? []);
        } else if (envelope.type === "event" && envelope.event) {
          setEvents((prev) => [...prev, envelope.event!].slice(-200));
        }
      } catch {
        setConnected(false);
      }
    };

    return () => {
      closed = true;
      socket.close();
    };
  }, [threadId]);

  const steps = useMemo(() => latestStepEvents(events), [events]);
  const lastEvent = events.at(-1);
  const activeCount = steps.filter((step) => step.status === "running").length;

  if (!events.length && !connected) {
    return null;
  }

  return (
    <section className="mb-4 overflow-hidden rounded-lg border bg-background/70">
      <div className="flex items-center justify-between gap-3 border-b px-3 py-2">
        <div className="flex min-w-0 items-center gap-2 text-xs font-medium">
          <ActivityIcon className="size-3.5 text-sky-500" />
          <span className="truncate">Live Work Bus</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {activeCount > 0 ? (
            <Badge variant="secondary">{activeCount} running</Badge>
          ) : null}
          <span
            className={cn(
              "size-2 rounded-full",
              connected ? "bg-emerald-500" : "bg-muted-foreground/40",
            )}
          />
        </div>
      </div>
      <div className="relative px-3 py-3">
        <div className="work-bus-laser pointer-events-none absolute left-3 right-3 top-1/2 h-px" />
        <div className="relative flex gap-2 overflow-x-auto pb-1">
          {steps.length ? (
            steps.slice(-8).map((step) => (
              <div
                className="min-w-36 max-w-44 rounded-md border bg-muted/20 px-2 py-2"
                key={step.step_id ?? step.event_id}
              >
                <div className="flex items-center gap-1.5">
                  <StepStatusIcon status={step.status} />
                  <span className={cn("truncate text-xs font-medium", statusTone(step.status))}>
                    {step.status ?? "pending"}
                  </span>
                </div>
                <div className="mt-1 line-clamp-2 text-xs text-foreground">
                  {step.title ?? step.tool_name ?? step.kind}
                </div>
                {step.tool_name ? (
                  <div className="mt-1 truncate text-[11px] text-muted-foreground">
                    {step.tool_name}
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <div className="text-xs text-muted-foreground">
              {lastEvent?.title ?? "Waiting for workflow events"}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
