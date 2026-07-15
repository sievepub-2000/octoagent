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
  const { state, toggleSidebar } = useSidebar();
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
          <div className="flex h-12 w-full items-center justify-center">
            <button
              type="button"
              data-testid="sidebar-collapsed-brand-trigger"
              aria-label={t.workspace.inspector.expand}
              title={t.workspace.inspector.expand}
              onClick={toggleSidebar}
              className="flex size-8 shrink-0 items-center justify-center rounded-md outline-hidden transition-colors hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-sidebar-ring"
            >
              <BrandMark priority size={32} />
            </button>
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
