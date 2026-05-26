"use client";

import { cn } from "@/lib/utils";
import { ChevronDownIcon, SearchIcon } from "lucide-react";
import type { ComponentProps } from "react";

export type TaskItemFileProps = ComponentProps<"div">;

export const TaskItemFile = ({
  children,
  className,
  ...props
}: TaskItemFileProps) => (
  <div
    className={cn(
      "inline-flex items-center gap-1 rounded-md border bg-secondary px-1.5 py-0.5 text-foreground text-xs",
      className
    )}
    {...props}
  >
    {children}
  </div>
);

export type TaskItemProps = ComponentProps<"div">;

export const TaskItem = ({ children, className, ...props }: TaskItemProps) => (
  <div className={cn("text-muted-foreground text-sm", className)} {...props}>
    {children}
  </div>
);

export type TaskProps = ComponentProps<"div"> & {
  defaultOpen?: boolean;
};

export const Task = ({
  defaultOpen: _defaultOpen = true,
  className,
  ...props
}: TaskProps) => (
  <div className={cn(className)} {...props} />
);

export type TaskTriggerProps = ComponentProps<"div"> & {
  title: string;
};

export const TaskTrigger = ({
  children,
  className,
  title,
  ...props
}: TaskTriggerProps) => (
  <div className={cn("group", className)} {...props}>
    {children ?? (
      <div className="flex w-full cursor-pointer items-center gap-2 text-muted-foreground text-sm transition-colors hover:text-foreground">
        <SearchIcon className="size-4" />
        <p className="text-sm">{title}</p>
        <ChevronDownIcon className="size-4" />
      </div>
    )}
  </div>
);

export type TaskContentProps = ComponentProps<"div">;

export const TaskContent = ({
  children,
  className,
  ...props
}: TaskContentProps) => (
  <div className={cn("text-popover-foreground outline-none", className)} {...props}>
    <div className="mt-4 space-y-2 border-muted border-l-2 pl-4">
      {children}
    </div>
  </div>
);
