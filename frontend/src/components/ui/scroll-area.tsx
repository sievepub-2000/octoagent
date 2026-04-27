"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

function ScrollArea({
  className,
  children,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="scroll-area"
      className={cn(
        "relative overflow-auto overscroll-contain [scrollbar-gutter:stable]",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}

function ScrollBar({
  orientation: _orientation = "vertical",
}: React.ComponentProps<"div"> & { orientation?: "vertical" | "horizontal" }) {
  return null
}

export { ScrollArea, ScrollBar }
