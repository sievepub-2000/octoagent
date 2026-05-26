"use client";

import {
  AlertTriangleIcon,
  BellIcon,
  CheckCircle2Icon,
  InfoIcon,
  Trash2Icon,
  XCircleIcon,
} from "lucide-react";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  clearSystemEvents,
  markAllSystemEventsRead,
  useSystemEvents,
  type SystemEvent,
  type SystemEventLevel,
} from "@/core/system-events/store";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

const ICON_BY_LEVEL: Record<SystemEventLevel, typeof InfoIcon> = {
  info: InfoIcon,
  warning: AlertTriangleIcon,
  error: XCircleIcon,
  success: CheckCircle2Icon,
};

const LEVEL_COLOR: Record<SystemEventLevel, string> = {
  info: "text-destructive",
  warning: "text-destructive",
  error: "text-destructive",
  success: "text-emerald-500",
};

const LEVEL_BADGE_BG: Record<SystemEventLevel, string> = {
  info: "bg-destructive",
  warning: "bg-destructive",
  error: "bg-destructive",
  success: "bg-emerald-500",
};

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function EventRow({ event }: { event: SystemEvent }) {
  const Icon = ICON_BY_LEVEL[event.level];
  return (
    <div className="flex items-start gap-2 rounded-lg border border-border/40 bg-muted/10 px-3 py-2">
      <Icon className={cn("mt-0.5 size-4 shrink-0", LEVEL_COLOR[event.level])} />
      <div className="min-w-0 flex-1">
        <div className="break-words text-sm font-medium text-foreground">
          {event.message}
        </div>
        {event.detail ? (
          <p className="mt-0.5 break-words text-xs text-muted-foreground">
            {event.detail}
          </p>
        ) : null}
        <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
          <span>{formatTime(event.timestamp)}</span>
          {event.source ? <span>· {event.source}</span> : null}
        </div>
      </div>
    </div>
  );
}

export function SystemEventsButton({ className }: { className?: string }) {
  const { t } = useI18n();
  const { events, unreadCount } = useSystemEvents();

  const hasEvents = events.length > 0;
  const recentLevel = useMemo<SystemEventLevel | null>(
    () => events[0]?.level ?? null,
    [events],
  );

  return (
    <Sheet
      onOpenChange={(open) => {
        if (open) markAllSystemEventsRead();
      }}
    >
      <SheetTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className={cn("relative", className)}
          aria-label={t.systemEvents.title}
          title={t.systemEvents.title}
        >
          <BellIcon
            className={cn(
              "size-4",
              unreadCount > 0 && recentLevel ? LEVEL_COLOR[recentLevel] : undefined,
            )}
          />
          {unreadCount > 0 ? (
            <span
              className={cn(
                "absolute -top-0.5 -right-0.5 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[10px] font-semibold text-white",
                recentLevel ? LEVEL_BADGE_BG[recentLevel] : "bg-destructive",
              )}
            >
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          ) : null}
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-full sm:max-w-md octo-panel">
        <SheetHeader className="border-b border-border/40 pb-3 pr-10">
          <SheetTitle className="flex items-center gap-2">
            <BellIcon className="size-4" />
            {t.systemEvents.title}
            <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
              {events.length}
            </Badge>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="ml-2"
              onClick={clearSystemEvents}
              disabled={!hasEvents}
              aria-label={t.systemEvents.clear}
              title={t.systemEvents.clear}
            >
              <Trash2Icon className="size-3.5" />
            </Button>
          </SheetTitle>
          <SheetDescription className="text-xs">
            {t.systemEvents.description}
          </SheetDescription>
        </SheetHeader>
        <ScrollArea className="-mx-4 h-[calc(100vh-7rem)] px-4">
          <div className="space-y-2 py-3">
            {hasEvents ? (
              events.map((ev) => <EventRow key={ev.id} event={ev} />)
            ) : (
              <div className="grid h-[40vh] place-items-center text-center text-sm text-muted-foreground">
                {t.systemEvents.empty}
              </div>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
