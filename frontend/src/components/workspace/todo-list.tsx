import { ChevronUpIcon, ListTodoIcon } from "lucide-react";
import { useId, useState } from "react";

import type { Todo } from "@/core/todos";
import { cn } from "@/lib/utils";

import {
  QueueItem,
  QueueItemContent,
  QueueItemIndicator,
} from "../ai-elements/queue";

export function TodoList({
  className,
  todos,
  collapsed: controlledCollapsed,
  hidden = false,
  onToggle,
}: {
  className?: string;
  todos: Todo[];
  collapsed?: boolean;
  hidden?: boolean;
  onToggle?: () => void;
}) {
  const [internalCollapsed, setInternalCollapsed] = useState(true);
  const panelId = useId();
  const isControlled = controlledCollapsed !== undefined;
  const collapsed = isControlled ? controlledCollapsed : internalCollapsed;

  const handleToggle = () => {
    if (isControlled) {
      onToggle?.();
    } else {
      setInternalCollapsed((prev) => !prev);
    }
  };

  if (hidden) {
    return null;
  }

  return (
    <div
      className={cn(
        "bg-background/95 flex h-fit w-full origin-bottom flex-col overflow-hidden rounded-t-[1.75rem] border border-b-0 transition-all duration-200 ease-out",
        className,
      )}
    >
      <button
        aria-controls={panelId}
        aria-expanded={!collapsed}
        className={cn(
          "bg-muted/60 flex min-h-10 shrink-0 cursor-pointer items-center justify-between rounded-t-[1.75rem] px-5 text-sm transition-all duration-300 ease-out",
        )}
        onClick={handleToggle}
        type="button"
      >
        <div className="text-muted-foreground">
          <div className="flex items-center justify-center gap-2">
            <ListTodoIcon className="size-4" />
            <div>To-dos</div>
          </div>
        </div>
        <div>
          <ChevronUpIcon
            className={cn(
              "text-muted-foreground size-4 transition-transform duration-300 ease-out",
              collapsed ? "" : "rotate-180",
            )}
          />
        </div>
      </button>
      <div
        id={panelId}
        className={cn(
          "bg-muted/30 flex grow px-2 transition-all duration-300 ease-out",
          collapsed ? "h-0 pb-0" : "h-28 pb-4",
        )}
      >
        <div className="bg-background mt-0 w-full overflow-y-auto rounded-t-md">
          <div className="max-h-40 pr-4">
            <ul>
              {todos.map((todo, i) => (
                <QueueItem key={i + (todo.content ?? "")}>
                  <div className="flex items-center gap-2">
                    <QueueItemIndicator
                      className={
                        todo.status === "in_progress" ? "bg-primary/70" : ""
                      }
                      completed={todo.status === "completed"}
                    />
                    <QueueItemContent
                      className={
                        todo.status === "in_progress" ? "text-primary/70" : ""
                      }
                      completed={todo.status === "completed"}
                    >
                      {todo.content}
                    </QueueItemContent>
                  </div>
                </QueueItem>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
