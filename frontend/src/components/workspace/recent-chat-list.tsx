"use client";

import { CornerDownRight, MoreHorizontal, Pencil, Share2, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { AgentAvatar } from "@/components/brand/octo-mark";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useAgents, agentAvatarUrl } from "@/core/agents";
import { useI18n } from "@/core/i18n/hooks";
import {
  useDeleteThread,
  useRenameThread,
  useThreads,
} from "@/core/threads/hooks";
import type { AgentThread } from "@/core/threads/types";
import { pathOfThread, pathToContinueThread, titleOfThread } from "@/core/threads/utils";
import { env } from "@/env";

const RECENT_CHAT_LIMIT = 12;

function titleOfRecentThread(thread: AgentThread) {
  const title = titleOfThread(thread);
  return title;
}

export function RecentChatList() {
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const { thread_id: threadIdFromPath } = useParams<{ thread_id: string }>();
  const { data: threads = [] } = useThreads({
    limit: RECENT_CHAT_LIMIT,
    sortBy: "updated_at",
    sortOrder: "desc",
    select: ["thread_id", "updated_at", "values", "metadata"],
  });
  const { agents } = useAgents();
  const { mutate: deleteThread } = useDeleteThread();
  const { mutate: renameThread } = useRenameThread();

  // Build agent lookup map
  const agentMap = useMemo(() => {
    const map = new Map<string, { name: string; avatar?: string | null }>();
    for (const a of agents) {
      map.set(a.name, { name: a.name, avatar: a.avatar });
    }
    return map;
  }, [agents]);

  // Rename dialog state
  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [renameThreadId, setRenameThreadId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const handleDelete = useCallback(
    (threadId: string) => {
      deleteThread({ threadId });
      if (threadId === threadIdFromPath) {
        const threadIndex = threads.findIndex((t) => t.thread_id === threadId);
        let nextThreadId = "new";
        if (threadIndex > -1) {
          if (threads[threadIndex + 1]) {
            nextThreadId = threads[threadIndex + 1]!.thread_id;
          } else if (threads[threadIndex - 1]) {
            nextThreadId = threads[threadIndex - 1]!.thread_id;
          }
        }
        void router.push(`/workspace/chats/${nextThreadId}`);
      }
    },
    [deleteThread, router, threadIdFromPath, threads],
  );

  const handleRenameClick = useCallback(
    (threadId: string, currentTitle: string) => {
      setRenameThreadId(threadId);
      setRenameValue(currentTitle);
      setRenameDialogOpen(true);
    },
    [],
  );

  const handleRenameSubmit = useCallback(() => {
    if (renameThreadId && renameValue.trim()) {
      renameThread({ threadId: renameThreadId, title: renameValue.trim() });
      setRenameDialogOpen(false);
      setRenameThreadId(null);
      setRenameValue("");
    }
  }, [renameThread, renameThreadId, renameValue]);

  const handleShare = useCallback(
    async (threadId: string) => {
      const shareUrl = `${window.location.origin}/workspace/chats/${threadId}`;
      try {
        await navigator.clipboard.writeText(shareUrl);
        toast.success(t.clipboard.linkCopied);
      } catch {
        toast.error(t.clipboard.failedToCopyToClipboard);
      }
    },
    [t],
  );
  if (threads.length === 0) {
    return null;
  }
  return (
    <>
      <SidebarGroup>
        <SidebarGroupLabel>
          {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true"
            ? t.sidebar.recentChats
            : t.sidebar.demoChats}
        </SidebarGroupLabel>
        <SidebarGroupContent className="group-data-[collapsible=icon]:pointer-events-none group-data-[collapsible=icon]:-mt-8 group-data-[collapsible=icon]:opacity-0">
          <SidebarMenu className="gap-1">
            {threads.map((thread) => {
                const isActive = pathOfThread(thread.thread_id) === pathname;
                const threadAgentName = (thread.metadata as Record<string, unknown> | undefined)?.agent_name as string | undefined;
                const agentInfo = threadAgentName ? agentMap.get(threadAgentName) : undefined;
                const avatarUrl = agentInfo?.avatar && threadAgentName
                  ? `${agentAvatarUrl(threadAgentName)}?v=1`
                  : undefined;
                const title = titleOfRecentThread(thread);
                return (
                  <SidebarMenuItem
                    key={thread.thread_id}
                    className="group/side-menu-item"
                  >
                    <SidebarMenuButton isActive={isActive} asChild>
                      <Link
                        className="text-muted-foreground block w-full whitespace-nowrap group-hover/side-menu-item:overflow-hidden"
                        href={pathOfThread(thread.thread_id)}
                      >
                        <AgentAvatar priority size={18} className="-ml-0.5 shrink-0" avatarUrl={avatarUrl} />
                        <span className="truncate">{title}</span>
                      </Link>
                    </SidebarMenuButton>
                    {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true" && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <SidebarMenuAction
                            showOnHover
                            className="bg-background/50 hover:bg-background"
                          >
                            <MoreHorizontal />
                            <span className="sr-only">{t.common.more}</span>
                          </SidebarMenuAction>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent
                          className="w-48 rounded-lg"
                          side={"right"}
                          align={"start"}
                        >
                          <DropdownMenuItem
                            onSelect={() =>
                              router.push(pathToContinueThread(thread.thread_id))
                            }
                          >
                            <CornerDownRight className="text-muted-foreground" />
                            <span>{t.common.continueTask}</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onSelect={() =>
                              handleRenameClick(
                                thread.thread_id,
                                title,
                              )
                            }
                          >
                            <Pencil className="text-muted-foreground" />
                            <span>{t.common.rename}</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onSelect={() => handleShare(thread.thread_id)}
                          >
                            <Share2 className="text-muted-foreground" />
                            <span>{t.common.share}</span>
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onSelect={() => handleDelete(thread.thread_id)}
                          >
                            <Trash2 className="text-muted-foreground" />
                            <span>{t.common.delete}</span>
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      {/* Rename Dialog */}
      <Dialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>{t.common.rename}</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Input
              aria-label={t.common.rename}
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              placeholder={t.common.rename}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleRenameSubmit();
                }
              }}
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRenameDialogOpen(false)}
            >
              {t.common.cancel}
            </Button>
            <Button onClick={handleRenameSubmit}>{t.common.save}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
