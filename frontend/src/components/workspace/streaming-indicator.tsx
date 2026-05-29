import { latestRunEvent, type RunEvent } from "@/core/runtime";
import { cn } from "@/lib/utils";

export function StreamingIndicator({
  className,
  events = [],
  size = "normal",
}: {
  className?: string;
  events?: RunEvent[];
  size?: "normal" | "sm";
}) {
  const dotSize = size === "sm" ? "w-1.5 h-1.5 mx-0.5" : "w-2 h-2 mx-1";
  const event = latestRunEvent(events);

  return (
    <div className={cn("flex items-center gap-3 text-sm text-muted-foreground", className)} aria-live="polite">
      <div className="flex shrink-0">
        <div
          className={cn(
            dotSize,
            "animate-bouncing rounded-full bg-[#a3a1a1] opacity-100",
          )}
        />
        <div
          className={cn(
            dotSize,
            "animate-bouncing rounded-full bg-[#a3a1a1] opacity-100 [animation-delay:0.2s]",
          )}
        />
        <div
          className={cn(
            dotSize,
            "animate-bouncing rounded-full bg-[#a3a1a1] opacity-100 [animation-delay:0.4s]",
          )}
        />
      </div>
      {event ? (
        <div className="min-w-0">
          <div className="truncate font-medium text-foreground">{event.title}</div>
          {event.detail ? <div className="truncate text-xs">{event.detail}</div> : null}
        </div>
      ) : null}
    </div>
  );
}
