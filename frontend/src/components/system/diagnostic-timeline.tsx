"use client";

import { ActivitySquareIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useTaskObservationTimeline } from "@/core/observation";

export function DiagnosticTimeline({
  taskId,
  active,
}: {
  taskId: string | null;
  active: boolean;
}) {
  const { events, isLoading } = useTaskObservationTimeline(taskId, {
    enabled: taskId != null,
    refetchInterval: active ? 3000 : false,
  });

  return (
    <Card className="min-h-0 shadow-none">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">Diagnostic timeline</CardTitle>
            <CardDescription>
              Structured task events derived from the workspace execution archive.
            </CardDescription>
          </div>
          <Badge variant="outline">{events.length} events</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[280px] rounded-lg border bg-muted/10 p-3">
          {isLoading ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
              <ActivitySquareIcon className="size-5 animate-pulse" />
              Loading diagnostic timeline…
            </div>
          ) : events.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
              <ActivitySquareIcon className="size-5 opacity-50" />
              No diagnostic events yet.
            </div>
          ) : (
            <div className="space-y-3">
              {events.map((event) => (
                <div key={`${event.timestamp}-${event.title}`} className="rounded-lg border bg-background p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="font-medium text-foreground">{event.title}</div>
                    <div className="shrink-0 text-[11px] text-muted-foreground">
                      {new Date(event.timestamp).toLocaleString()}
                    </div>
                  </div>
                  {event.details.length > 0 ? (
                    <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                      {event.details.map((detail, index) => (
                        <div key={`${event.timestamp}-${index}`}>{detail}</div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}