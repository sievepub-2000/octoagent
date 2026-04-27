"use client";

import { GripVerticalIcon } from "lucide-react";
import * as React from "react";
import * as ResizablePrimitive from "react-resizable-panels";

import { cn } from "@/lib/utils";

function ResizablePanelGroup({
  className,
  ...props
}: React.ComponentProps<typeof ResizablePrimitive.Group>) {
  return (
    <ResizablePrimitive.Group
      data-slot="resizable-panel-group"
      className={cn(
        "flex h-full w-full data-[panel-group-direction=vertical]:flex-col",
        className,
      )}
      {...props}
    />
  );
}

function ResizablePanel({
  ...props
}: React.ComponentProps<typeof ResizablePrimitive.Panel>) {
  return <ResizablePrimitive.Panel data-slot="resizable-panel" {...props} />;
}

function ResizableHandle({
  withHandle,
  className,
  onWheel,
  ...props
}: React.ComponentProps<typeof ResizablePrimitive.Separator> & {
  withHandle?: boolean;
}) {
  const handleWheel = React.useCallback<React.WheelEventHandler<HTMLDivElement>>(
    (event) => {
      onWheel?.(event);
      if (event.defaultPrevented || Math.abs(event.deltaY) < 1) {
        return;
      }

      const groupDirection = event.currentTarget.getAttribute("data-panel-group-direction");
      const key =
        groupDirection === "vertical"
          ? event.deltaY < 0
            ? "ArrowUp"
            : "ArrowDown"
          : event.deltaY < 0
            ? "ArrowLeft"
            : "ArrowRight";

      event.preventDefault();
      event.currentTarget.focus();
      event.currentTarget.dispatchEvent(
        new KeyboardEvent("keydown", {
          key,
          bubbles: true,
        }),
      );
    },
    [onWheel],
  );

  return (
    <ResizablePrimitive.Separator
      data-slot="resizable-handle"
      className={cn(
        "group/resizable bg-border/70 focus-visible:ring-ring relative flex w-px items-center justify-center after:absolute after:inset-y-0 after:left-1/2 after:w-2 after:-translate-x-1/2 focus-visible:ring-1 focus-visible:ring-offset-1 focus-visible:outline-hidden data-[panel-group-direction=vertical]:h-px data-[panel-group-direction=vertical]:w-full data-[panel-group-direction=vertical]:after:left-0 data-[panel-group-direction=vertical]:after:h-2 data-[panel-group-direction=vertical]:after:w-full data-[panel-group-direction=vertical]:after:translate-x-0 data-[panel-group-direction=vertical]:after:-translate-y-1/2 [&[data-panel-group-direction=vertical]>div]:rotate-90",
        className,
      )}
      onWheel={handleWheel}
      {...props}
    >
      {withHandle && (
        <div className="bg-background/92 border-border/80 text-muted-foreground group-hover/resizable:text-foreground z-10 flex h-9 w-5 items-center justify-center rounded-full border shadow-[0_8px_24px_rgba(0,0,0,0.08)] backdrop-blur-sm transition-colors duration-200">
          <GripVerticalIcon className="size-3" />
        </div>
      )}
    </ResizablePrimitive.Separator>
  );
}

export { ResizablePanelGroup, ResizablePanel, ResizableHandle };
