"use client";

import { SettingsIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";

export function WorkspaceNavMenu() {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const { open: isSidebarOpen } = useSidebar();
  const { t } = useI18n();

  // Build the URL for the settings panel
  const next = new URLSearchParams(searchParams.toString());
  next.set("settings", "appearance");
  const settingsHref = `${pathname}?${next.toString()}`;

  const isActive = searchParams.has("settings");

  return (
    <SidebarMenu className="w-full">
      <SidebarMenuItem>
        <SidebarMenuButton
          id="workspace-system-settings-trigger"
          size="lg"
          isActive={isActive}
          asChild
        >
          <Link href={settingsHref}>
            {isSidebarOpen ? (
              <div className="text-muted-foreground flex w-full items-center gap-2 text-left text-sm">
                <SettingsIcon className="size-4" />
                <span>{t.workspace.settingsAndMore}</span>
              </div>
            ) : (
              <div className="flex size-full items-center justify-center">
                <SettingsIcon className="text-muted-foreground size-4" />
              </div>
            )}
          </Link>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
