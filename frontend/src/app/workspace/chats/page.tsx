"use client";

import { CornerDownRight, FilterIcon, SearchIcon, Trash2Icon } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { AgentAvatar } from "@/components/brand/octo-mark";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { useAgents, agentAvatarUrl } from "@/core/agents";
import { useI18n } from "@/core/i18n/hooks";
import { useDeleteThread, useThreads } from "@/core/threads/hooks";
import {
  pathOfThread,
  pathToContinueThread,
  titleOfThread,
} from "@/core/threads/utils";
import { formatTimeAgo } from "@/core/utils/datetime";

export default function ChatsPage() {
  const { t } = useI18n();
  const { data: threads } = useThreads();
  const { agents } = useAgents();
  const deleteThread = useDeleteThread();
  const [search, setSearch] = useState("");
  const [agentFilter, setAgentFilter] = useState("all");
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    document.title = `${t.pages.chats} - ${t.pages.appName}`;
  }, [t.pages.chats, t.pages.appName]);

  // Build agent lookup map
  const agentMap = useMemo(() => {
    const map = new Map<string, { name: string; avatar?: string | null }>();
    for (const a of agents) {
      map.set(a.name, { name: a.name, avatar: a.avatar });
    }
    return map;
  }, [agents]);

  // Get unique agent names from threads that have agent_name in metadata
  const threadAgentNames = useMemo(() => {
    const names = new Set<string>();
    threads?.forEach((thread) => {
      const agentName = (thread.metadata as Record<string, unknown> | undefined)?.agent_name;
      if (typeof agentName === "string") names.add(agentName);
    });
    return Array.from(names).sort();
  }, [threads]);

  const filteredThreads = useMemo(() => {
    return threads?.filter((thread) => {
      const matchesSearch = titleOfThread(thread).toLowerCase().includes(search.toLowerCase());
      const threadAgent = (thread.metadata as Record<string, unknown> | undefined)?.agent_name;
      const matchesAgent = agentFilter === "all" || threadAgent === agentFilter;
      return matchesSearch && matchesAgent;
    });
  }, [threads, search, agentFilter]);

  const handleDeleteAll = async () => {
    if (!threads?.length) return;
    if (!window.confirm(t.common.deleteAllConfirm)) return;
    setDeleting(true);
    try {
      for (const thread of threads) {
        await deleteThread.mutateAsync({ threadId: thread.thread_id });
      }
      toast.success(t.common.deleteAllSuccess);
    } catch {
      toast.error("Failed to delete some threads");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <WorkspaceContainer>
      <WorkspaceHeader></WorkspaceHeader>
      <WorkspaceBody>
        <div className="flex size-full flex-col">
          <header className="flex shrink-0 flex-col items-center gap-3 pt-8">
            <div className="flex w-full max-w-(--container-width-md) items-center gap-2">
              {/* Agent filter */}
              <Select value={agentFilter} onValueChange={setAgentFilter}>
                <SelectTrigger className="h-12 w-40 shrink-0">
                  <FilterIcon className="mr-1.5 size-4 opacity-50" />
                  <SelectValue placeholder="All Agents" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Agents</SelectItem>
                  {threadAgentNames.map((name) => (
                    <SelectItem key={name} value={name}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {/* Search bar with micro-convex neumorphic style */}
              <div className="relative flex-1" style={{
                borderRadius: "0.75rem",
                background: "var(--card)",
                boxShadow: "inset 2px 2px 4px rgba(0,0,0,0.06), inset -2px -2px 4px rgba(255,255,255,0.8), 2px 2px 6px rgba(0,0,0,0.08)",
              }}>
                <Input
                  type="search"
                  className="h-12 border-none bg-transparent pr-10 text-xl shadow-none focus-visible:ring-0"
                  placeholder={t.chats.searchChats}
                  autoFocus
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
                />
                <SearchIcon className="text-muted-foreground pointer-events-none absolute right-3 top-1/2 size-5 -translate-y-1/2" />
              </div>
              {threads && threads.length > 0 && (
                <Button
                  size="sm"
                  variant="destructive"
                  className="h-12 shrink-0"
                  disabled={deleting}
                  onClick={handleDeleteAll}
                >
                  <Trash2Icon className="mr-1 size-3.5" />
                  {t.common.deleteAll}
                </Button>
              )}
            </div>
          </header>
          <main className="min-h-0 flex-1">
            <ScrollArea className="size-full py-4">
              <div className="mx-auto flex size-full max-w-(--container-width-md) flex-col">
                {filteredThreads?.map((thread) => {
                  const threadAgentName = (thread.metadata as Record<string, unknown> | undefined)?.agent_name as string | undefined;
                  const agentInfo = threadAgentName ? agentMap.get(threadAgentName) : undefined;
                  const avatarUrl = agentInfo?.avatar && threadAgentName
                    ? `${agentAvatarUrl(threadAgentName)}?v=1`
                    : undefined;
                  return (
                  <div
                    key={thread.thread_id}
                    className="flex items-center justify-between gap-4 border-b p-4"
                  >
                    <div className="flex min-w-0 flex-1 items-center gap-3">
                      <AgentAvatar size={32} avatarUrl={avatarUrl} className="shrink-0" />
                      <Link className="min-w-0 flex-1" href={pathOfThread(thread.thread_id)}>
                        <div className="flex flex-col gap-1.5">
                          <div className="flex items-center gap-2">
                            <span className="truncate">{titleOfThread(thread)}</span>
                            {threadAgentName && (
                              <Badge variant="secondary" className="shrink-0 text-xs">
                                {threadAgentName}
                              </Badge>
                            )}
                          </div>
                          {thread.updated_at && (
                            <div className="text-muted-foreground text-sm">
                              {formatTimeAgo(thread.updated_at)}
                            </div>
                          )}
                        </div>
                      </Link>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Button asChild size="sm" variant="outline">
                        <Link href={pathToContinueThread(thread.thread_id)}>
                          <CornerDownRight />
                          {t.chats.continueFromHere}
                        </Link>
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-muted-foreground hover:text-destructive"
                        onClick={() => {
                          if (window.confirm(t.common.deleteConfirm)) {
                            deleteThread.mutate({ threadId: thread.thread_id });
                          }
                        }}
                      >
                        <Trash2Icon className="size-4" />
                      </Button>
                    </div>
                  </div>
                  );
                })}
              </div>
            </ScrollArea>
          </main>
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}
