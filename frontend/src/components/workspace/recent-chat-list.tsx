"use client";

import { FolderIcon, MessageSquareIcon, MoreHorizontalIcon, Trash2Icon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarMenu, SidebarMenuAction, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";
import { useProjects } from "@/core/projects/hooks";
import { useDeleteThread, useThreads } from "@/core/threads/hooks";
import { pathOfThread, titleOfThread } from "@/core/threads/utils";

export function RecentChatList() {
  const { t } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const { data: projects = [] } = useProjects();
  const { data: threads = [] } = useThreads({ limit: 40, sortBy: "updated_at", sortOrder: "desc", select: ["thread_id", "updated_at", "values", "metadata"] });
  const { mutate: deleteThread } = useDeleteThread();
  if (threads.length === 0 && projects.length === 0) return null;

  const groups = projects.map((project) => ({ project, threads: threads.filter((thread) => thread.values?.project_id === project.project_id) }));
  const standalone = threads.filter((thread) => !thread.values?.project_id);

  const renderThread = (thread: (typeof threads)[number]) => <SidebarMenuItem key={thread.thread_id} className="group/thread"><SidebarMenuButton asChild isActive={pathOfThread(thread.thread_id) === pathname}><Link href={pathOfThread(thread.thread_id)}><MessageSquareIcon className="size-3.5" /><span className="truncate">{titleOfThread(thread)}</span></Link></SidebarMenuButton><DropdownMenu><DropdownMenuTrigger asChild><SidebarMenuAction showOnHover><MoreHorizontalIcon /></SidebarMenuAction></DropdownMenuTrigger><DropdownMenuContent side="right"><DropdownMenuItem onSelect={() => deleteThread({ threadId: thread.thread_id }, { onSuccess: () => { if (pathOfThread(thread.thread_id) === pathname) void router.push("/workspace/chats/new"); } })}><Trash2Icon className="size-4" /> {t.common.delete}</DropdownMenuItem></DropdownMenuContent></DropdownMenu></SidebarMenuItem>;

  return <SidebarGroup><SidebarGroupLabel>{t.sidebar.projects} &amp; {t.sidebar.tasks}</SidebarGroupLabel><SidebarGroupContent className="group-data-[collapsible=icon]:hidden"><SidebarMenu>{groups.map(({ project, threads: projectThreads }) => <div key={project.project_id} className="mb-2"><SidebarMenuItem><SidebarMenuButton asChild isActive={pathname === `/workspace/projects/${project.project_id}`}><Link href={`/workspace/projects/${project.project_id}`}><FolderIcon className="size-4" /><span className="truncate font-medium">{project.name}</span></Link></SidebarMenuButton></SidebarMenuItem><div className="ml-3 border-l pl-2">{projectThreads.slice(0, 6).map(renderThread)}</div></div>)}{standalone.length > 0 && <div><p className="px-2 py-1 text-xs text-muted-foreground">{t.sidebar.chats}</p>{standalone.slice(0, 8).map(renderThread)}</div>}</SidebarMenu></SidebarGroupContent></SidebarGroup>;
}
