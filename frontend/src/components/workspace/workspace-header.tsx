"use client";

import { MessageSquarePlus } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { BrandMark } from "@/components/brand/octo-mark";
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";
import { uuid } from "@/core/utils/uuid";
import { cn } from "@/lib/utils";

export function WorkspaceHeader({ className }: { className?: string }) {
  const { t } = useI18n();
  const { state } = useSidebar();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const startNewChat = () => {
    router.push(`/workspace/chats/${uuid()}?fresh=1&draft=${Date.now()}`);
  };
  return (
    <>
      <div
        className={cn(
          "group/workspace-header flex h-12 flex-col justify-center",
          className,
        )}
      >
        {state === "collapsed" ? (
          <div className="group-has-data-[collapsible=icon]/sidebar-wrapper:-translate-y flex w-max cursor-default items-center gap-1 pl-1">
            <BrandMark priority size={38} />
            <SidebarTrigger className="shrink-0" />
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2">
            <div className="ml-2 flex cursor-default items-center gap-2">
              <BrandMark priority size={38} />
              <span className="text-primary text-base font-semibold tracking-[-0.05em]">OctoAgent</span>
            </div>
            <SidebarTrigger />
          </div>
        )}
      </div>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            isActive={pathname === "/workspace/chats/new" || searchParams.get("fresh") === "1"}
            onClick={startNewChat}
          >
            <span className="contents text-muted-foreground">
              <MessageSquarePlus size={16} />
              <span>{t.sidebar.newChat}</span>
            </span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </>
  );
}
