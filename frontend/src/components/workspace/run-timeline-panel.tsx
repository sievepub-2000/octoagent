"use client";

import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  ChevronRightIcon,
  CircleDotIcon,
  ClipboardCopyIcon,
  Loader2Icon,
  WrenchIcon,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { RunEvent, RunEventKind, RunEventLevel } from "@/core/runtime";
import { copyTextToClipboard } from "@/lib/clipboard";
import { cn } from "@/lib/utils";

const KIND_LABELS: Record<RunEventKind, string> = {
  queued: "Queued",
  planning: "Planning",
  tool_call: "Tool",
  tool_result: "Result",
  workflow: "Workflow",
  subagent: "Subagent",
  answer_delta: "Writing",
  artifact: "Artifact",
  done: "Done",
  error: "Error",
};

function iconForEvent(kind: RunEventKind, level: RunEventLevel) {
  if (level === "error" || kind === "error") return AlertTriangleIcon;
  if (level === "success" || kind === "done" || kind === "tool_result") return CheckCircle2Icon;
  if (kind === "tool_call" || kind === "workflow" || kind === "subagent") return WrenchIcon;
  if (kind === "queued" || kind === "planning") return Loader2Icon;
  return CircleDotIcon;
}

function levelClass(level: RunEventLevel, kind: RunEventKind) {
  if (level === "error" || kind === "error") return "border-destructive/30 text-destructive";
  if (level === "success" || kind === "done" || kind === "tool_result") return "border-emerald-500/30 text-emerald-600 dark:text-emerald-400";
  if (level === "warning") return "border-amber-500/30 text-amber-600 dark:text-amber-400";
  return "border-border/70 text-muted-foreground";
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function eventText(event: RunEvent) {
  return [
    `[${event.kind}] ${event.title}`,
    event.detail,
    event.taskId ? `task: ${event.taskId}` : undefined,
    event.runId ? `run: ${event.runId}` : undefined,
  ].filter(Boolean).join("\n");
}

export function RunTimelinePanel({
  className,
  events,
  isLoading,
}: {
  className?: string;
  events: RunEvent[];
  isLoading: boolean;
}) {
  const [open, setOpen] = useState(isLoading);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const visibleEvents = useMemo(() => events.slice(0, open ? 12 : 4), [events, open]);
  const errorCount = events.filter((event) => event.level === "error" || event.kind === "error").length;
  const latest = events[0];

  const copyAll = useCallback(async () => {
    await copyTextToClipboard(JSON.stringify(events, null, 2));
  }, [events]);

  if (events.length === 0) return null;

  return (
    <Collapsible
      className={cn("rounded-md border border-border/70 bg-background/80 text-sm shadow-sm backdrop-blur", className)}
      open={open}
      onOpenChange={setOpen}
    >
      <div className="flex min-h-11 items-center gap-2 px-3">
        <CollapsibleTrigger asChild>
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Toggle run timeline" title="Toggle run timeline">
            {open ? <ChevronDownIcon className="size-4" /> : <ChevronRightIcon className="size-4" />}
          </Button>
        </CollapsibleTrigger>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 font-medium text-foreground">Run timeline</span>
            <Badge variant="outline" className="h-5 px-1.5 text-[10px]">{events.length}</Badge>
            {errorCount > 0 ? (
              <Badge variant="outline" className="h-5 border-destructive/30 px-1.5 text-[10px] text-destructive">
                {errorCount} error
              </Badge>
            ) : null}
          </div>
          {latest ? (
            <div className="truncate text-xs text-muted-foreground">{latest.title}</div>
          ) : null}
        </div>
        <Button type="button" variant="ghost" size="icon-sm" aria-label="Copy timeline" title="Copy timeline" onClick={() => void copyAll()}>
          <ClipboardCopyIcon className="size-3.5" />
        </Button>
      </div>
      <CollapsibleContent>
        <div className="border-t border-border/60 px-3 py-2">
          <ol className="space-y-1.5">
            {visibleEvents.map((event) => {
              const Icon = iconForEvent(event.kind, event.level);
              const expanded = expandedIds.has(event.id);
              const hasDetails = Boolean(event.detail || event.taskId || event.runId || event.payload);
              return (
                <li key={`${event.id}-${event.kind}-${event.taskId ?? ""}`} className="rounded-md border border-border/45 bg-muted/20">
                  <button
                    type="button"
                    className="grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 px-2.5 py-2 text-left"
                    onClick={() => {
                      if (!hasDetails) return;
                      setExpandedIds((current) => {
                        const next = new Set(current);
                        if (next.has(event.id)) next.delete(event.id);
                        else next.add(event.id);
                        return next;
                      });
                    }}
                  >
                    <Icon className={cn("size-4", levelClass(event.level, event.kind), event.kind === "planning" && isLoading ? "animate-spin" : "")} />
                    <div className="min-w-0">
                      <div className="flex min-w-0 items-center gap-2">
                        <Badge variant="outline" className={cn("h-5 px-1.5 text-[10px]", levelClass(event.level, event.kind))}>
                          {KIND_LABELS[event.kind]}
                        </Badge>
                        <span className="truncate font-medium text-foreground">{event.title}</span>
                      </div>
                      {event.detail ? <div className="truncate text-xs text-muted-foreground">{event.detail}</div> : null}
                    </div>
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <span>{formatTime(event.createdAt)}</span>
                      {hasDetails ? expanded ? <ChevronDownIcon className="size-3.5" /> : <ChevronRightIcon className="size-3.5" /> : null}
                    </div>
                  </button>
                  {expanded ? (
                    <div className="border-t border-border/50 px-2.5 py-2">
                      <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded bg-background/80 p-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
                        {eventText(event)}
                        {event.payload ? `\n\n${JSON.stringify(event.payload, null, 2)}` : ""}
                      </pre>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ol>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
