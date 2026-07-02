"use client";

import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { toast, Toaster } from "sonner";

import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { getLocalSettings, useLocalSettings } from "@/core/settings";

type SettingsSectionId =
  | "overview"
  | "appearance"
  | "bootstrap"
  | "evolution"
  | "system-guard"
  | "runtime-health"
  | "rag"
  | "system-execution"
  | "memory"
  | "notification"
  | "tools"
  | "update"
  | "about";

import { WorkspaceSidebar } from "@/components/workspace/workspace-sidebar";

import { SystemStatusBar } from "@/components/workspace/system-status-bar";

import { SettingsPanel } from "@/components/workspace/settings";

const SETTINGS_SECTIONS: SettingsSectionId[] = [
  "overview",
  "appearance",
  "bootstrap",
  "evolution",
  "system-guard",
  "runtime-health",
  "rag",
  "system-execution",
  "memory",
  "notification",
  "tools",
  "update",
  "about",
];

export default function WorkspaceLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,        // 1 min — avoid redundant re-fetches
            gcTime: 10 * 60_000,      // 10 min — keep unused data in cache longer
          },
        },
        mutationCache: new MutationCache({
          onError: (error) => {
            toast.error(error.message || "Operation failed");
          },
        }),
      }),
  );
  const [settings, setSettings] = useLocalSettings();
  const [open, setOpen] = useState(true); // SSR default: open (matches expected state)
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  useLayoutEffect(() => {
    // Runs synchronously before first paint on the client — no visual flash
    setOpen(!getLocalSettings().layout.sidebar_collapsed);
  }, []);
  useEffect(() => {
    setOpen(!settings.layout.sidebar_collapsed);
  }, [settings.layout.sidebar_collapsed]);
  const handleOpenChange = useCallback(
    (open: boolean) => {
      setOpen(open);
      setSettings("layout", { sidebar_collapsed: !open });
    },
    [setSettings],
  );

  const settingsSection = searchParams.get("settings");
  const isSettingsSection = SETTINGS_SECTIONS.includes(
    settingsSection as SettingsSectionId,
  );

  const closeSettings = useCallback(() => {
    const next = new URLSearchParams(searchParams.toString());
    next.delete("settings");
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  }, [pathname, router, searchParams]);

  return (
    <QueryClientProvider client={queryClient}>
      <SidebarProvider
        className="h-screen"
        open={open}
        onOpenChange={handleOpenChange}
      >
        <a href="#maincontent" className="skip-link">
          Skip to main content
        </a>
        <WorkspaceSidebar />
        <SidebarInset id="maincontent" tabIndex={-1} className="min-w-0 flex flex-col">
          <SystemStatusBar />
          <div className="min-h-0 flex-1 overflow-hidden">
            <div className="flex h-full min-h-0">
              <div className="min-w-0 flex-1">{children}</div>
              {isSettingsSection ? (
                <SettingsPanel
                  open
                  defaultSection={settingsSection as SettingsSectionId}
                  onOpenChange={(nextOpen) => {
                    if (!nextOpen) {
                      closeSettings();
                    }
                  }}
                />
              ) : null}
            </div>
          </div>
        </SidebarInset>
      </SidebarProvider>
      <Toaster position="top-center" />
    </QueryClientProvider>
  );
}
