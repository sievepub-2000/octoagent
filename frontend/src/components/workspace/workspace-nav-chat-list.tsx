"use client";

import {
  BotIcon,
  BoxesIcon,
  CpuIcon,
  GitBranchIcon,
  MessagesSquare,
  RadioTowerIcon,
  SparklesIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";

export function WorkspaceNavChatList() {
  const { t } = useI18n();
  const pathname = usePathname();
  const { open: isSidebarOpen } = useSidebar();
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
              isActive={pathname.startsWith("/workspace/projects") || pathname.startsWith("/workspace/tasks")}
              asChild
            >
              <Link
                className="text-sidebar-foreground"
                href="/workspace/projects"
                prefetch={false}
              >
                <GitBranchIcon size={18} />
                <span>{t.sidebar.projects}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>
      {isSidebarOpen && (
        <SidebarGroup className="pt-0">
          <SidebarGroupLabel className="text-xs font-medium text-sidebar-foreground">
            {t.sidebar.configuration}
          </SidebarGroupLabel>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={pathname === "/workspace/config/models"}
                asChild
              >
                <Link
                  className="text-sidebar-foreground"
                  href="/workspace/config/models"
                >
                  <CpuIcon size={18} />
                  <span>{t.sidebar.models}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={pathname.startsWith("/workspace/agents")}
                asChild
              >
                <Link
                  className="text-sidebar-foreground"
                  href="/workspace/agents"
                  prefetch={false}
                >
                  <BotIcon size={18} />
                  <span>{t.sidebar.agents}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={pathname === "/workspace/config/skills"}
                asChild
              >
                <Link
                  className="text-sidebar-foreground"
                  href="/workspace/config/skills"
                >
                  <SparklesIcon size={18} />
                  <span>{t.sidebar.skills}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={pathname === "/workspace/config/mcp"}
                asChild
              >
                <Link
                  className="text-sidebar-foreground"
                  href="/workspace/config/mcp"
                >
                  <BoxesIcon size={18} />
                  <span>{t.sidebar.mcp}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={pathname === "/workspace/config/channels"}
                asChild
              >
                <Link
                  className="text-sidebar-foreground"
                  href="/workspace/config/channels"
                >
                  <RadioTowerIcon size={18} />
                  <span>{t.sidebar.channels}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
      )}
    </>
  );
}
