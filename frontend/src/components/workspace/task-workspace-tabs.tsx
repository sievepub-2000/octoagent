"use client";

import { FolderKanbanIcon, PlusIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useCreateTaskWorkspace, useTaskWorkspaces } from "@/core/task-workspaces";
import { cn } from "@/lib/utils";

export function TaskWorkspaceTabs() {
  const pathname = usePathname();
  const router = useRouter();
  const { workspaces } = useTaskWorkspaces();
  const createTaskWorkspaceMutation = useCreateTaskWorkspace();

  const handleCreate = async () => {
    const nextIndex = workspaces.length + 1;
    const workspace = await createTaskWorkspaceMutation.mutateAsync({
      name: `Task ${nextIndex}`,
      mode: "single",
    });
    router.push(`/workspace/workflows/${workspace.task_id}`);
  };

  return (
    <div className="border-b bg-background/90 px-4 py-2">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <FolderKanbanIcon className="size-4" />
          Tasks
        </div>
        <ScrollArea className="min-w-0 flex-1 whitespace-nowrap">
          <div className="flex items-center gap-2 pr-4">
            <Link
              className={cn(
                "rounded-full border px-3 py-1.5 text-sm transition-colors",
                pathname === "/workspace/tasks"
                  || pathname === "/workspace/workflows"
                  ? "border-foreground/30 bg-accent/60"
                  : "hover:bg-accent/30",
              )}
              href="/workspace/workflows"
            >
              Overview
            </Link>
            {workspaces.map((workspace) => {
              const active = pathname === `/workspace/workflows/${workspace.task_id}`;
              return (
                <Link
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-sm transition-colors",
                    active
                      ? "border-foreground/30 bg-accent/60"
                      : "hover:bg-accent/30",
                  )}
                  href={`/workspace/workflows/${workspace.task_id}`}
                  key={workspace.task_id}
                >
                  {workspace.name}
                </Link>
              );
            })}
          </div>
        </ScrollArea>
        <Button
          onClick={handleCreate}
          size="sm"
          variant="outline"
          disabled={createTaskWorkspaceMutation.isPending}
        >
          <PlusIcon className="size-4" />
          New Task
        </Button>
      </div>
    </div>
  );
}

