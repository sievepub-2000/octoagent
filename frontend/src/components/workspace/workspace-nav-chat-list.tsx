"use client";

import { FolderKanbanIcon, MessagesSquare } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";

export function WorkspaceNavChatList() {
  const { t } = useI18n();
  const pathname = usePathname();
  return (
    <>
      <SidebarGroup className="pt-1">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={pathname === "/workspace/chats"}
              asChild
            >
              <Link className="text-sidebar-foreground" href="/workspace/chats">
                <MessagesSquare size={18} />
                <span>{t.sidebar.chats}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={pathname.startsWith("/workspace/projects")}
              asChild
            >
              <Link
                className="text-sidebar-foreground"
                href="/workspace/projects"
                prefetch={false}
              >
                <FolderKanbanIcon size={18} />
                <span>{t.sidebar.projects}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>
    </>
  );
}
