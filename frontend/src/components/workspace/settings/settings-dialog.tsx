"use client";

import { ActivityIcon, BellIcon, SparklesIcon, BrainIcon, CpuIcon, DnaIcon, DownloadCloudIcon, InfoIcon, LaptopIcon, LayoutDashboardIcon, PaletteIcon, ShieldCheckIcon, WrenchIcon } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

function SettingsSectionFallback() {
  return (
    <div className="space-y-3" aria-busy="true" aria-live="polite">
      <div className="h-6 w-40 rounded-md bg-muted" />
      <div className="h-4 w-72 max-w-full rounded-md bg-muted" />
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="h-28 rounded-xl border border-border/60 bg-background/60" />
        <div className="h-28 rounded-xl border border-border/60 bg-background/60" />
      </div>
    </div>
  );
}

import { AboutSettingsPage } from "@/components/workspace/settings/about-settings-page";
import { AppearanceSettingsPage } from "@/components/workspace/settings/appearance-settings-page";
import { BootstrapSettingsPage } from "@/components/workspace/settings/bootstrap-settings-page";
import EvolutionConfigPage from "@/app/workspace/config/evolution/page";
import { MemorySettingsPage } from "@/components/workspace/settings/memory-settings-page";
import { NotificationSettingsPage } from "@/components/workspace/settings/notification-settings-page";
import { RuntimeHealthSettingsPage } from "@/components/workspace/settings/runtime-health-settings-page";
import { RagSettingsPage } from "@/components/workspace/settings/rag-settings-page";
import { SystemExecutionSettingsPage } from "@/components/workspace/settings/system-execution-settings-page";
import { SystemGuardSettingsPage } from "@/components/workspace/settings/system-guard-settings-page";
import { SystemSettingsPage } from "@/components/workspace/settings/system-settings-page";
import ToolsHubPage from "@/app/workspace/config/tools/page";
import { UpdateSettingsPage } from "@/components/workspace/settings/update-settings-page";

type SettingsSection =
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

export type SettingsSectionId = SettingsSection;

type SettingsPanelProps = {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  defaultSection?: SettingsSection;
};

export function SettingsPanel(props: SettingsPanelProps) {
  const { defaultSection = "overview", open, onOpenChange } = props;
  const { t } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [activeSection, setActiveSection] =
    useState<SettingsSection>(defaultSection);
  const [hasUpdate, setHasUpdate] = useState(false);

  // Check for updates on panel open
  useEffect(() => {
    if (!open) return;
    const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
    fetch(`${API_BASE}/api/system/update/check`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => { if (data?.has_update) setHasUpdate(true); else setHasUpdate(false); })
      .catch(() => undefined);
  }, [open]);

  const handleSectionChange = (nextSection: SettingsSection) => {
    setActiveSection(nextSection);
    const currentSection = searchParams.get("settings");
    if (currentSection === nextSection) {
      return;
    }
    const next = new URLSearchParams(searchParams.toString());
    next.set("settings", nextSection);
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  useEffect(() => {
    if (open) {
      setActiveSection(defaultSection);
    }
  }, [defaultSection, open]);

  const sections = useMemo(
    () => [
      {
        id: "overview",
        label: t.settings.sections.overview,
        icon: LayoutDashboardIcon,
      },
      {
        id: "appearance",
        label: t.settings.sections.appearance,
        icon: PaletteIcon,
      },
      {
        id: "bootstrap",
        label: t.settings.sections.bootstrap,
        icon: CpuIcon,
      },
      {
        id: "evolution",
        label: t.settings.sections.evolution ?? t.sidebar.evolution,
        icon: DnaIcon,
      },
      {
        id: "system-guard",
        label: t.settings.sections.systemGuard,
        icon: ShieldCheckIcon,
      },
      {
        id: "runtime-health",
        label: "Runtime Health",
        icon: ActivityIcon,
      },
      {
        id: "rag",
        label: t.settings.sections.rag,
        icon: SparklesIcon,
      },
      {
        id: "system-execution",
        label: t.settings.sections.systemExecution,
        icon: LaptopIcon,
      },
      {
        id: "tools",
        label: t.settings.tools.title,
        icon: WrenchIcon,
      },
      {
        id: "notification",
        label: t.settings.sections.notification,
        icon: BellIcon,
      },
      {
        id: "memory",
        label: t.settings.sections.memory,
        icon: BrainIcon,
      },
      {
        id: "update",
        label: t.settings.sections.update ?? "Update",
        icon: DownloadCloudIcon,
      },
      {
        id: "about",
        label: t.settings.sections.about,
        icon: InfoIcon,
      },
    ],
    [
      t.settings.sections.overview,
      t.settings.sections.appearance,
      t.settings.sections.bootstrap,
      t.settings.sections.evolution,
      t.sidebar.evolution,
      t.settings.sections.systemGuard,
      t.settings.sections.rag,
      t.settings.sections.systemExecution,
      t.settings.tools.title,
      t.settings.sections.notification,
      t.settings.sections.memory,
      t.settings.sections.update,
      t.settings.sections.about,
    ],
  );
  if (!open) {
    return null;
  }

  return (
    <aside className="octo-panel flex h-full min-h-0 w-[min(540px,58vw)] min-w-0 max-w-[540px] flex-col border-l border-border/40 rounded-none">
      <div className="flex items-start justify-between gap-4 border-b border-border/60 px-5 py-4">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold tracking-[-0.05em]">{t.workspace.settingsAndMore}</h2>
          <p className="text-muted-foreground text-sm">{t.settings.description}</p>
        </div>
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground rounded-full border px-3 py-1 text-xs"
          onClick={() => onOpenChange?.(false)}
        >
          {t.common.close}
        </button>
      </div>
      <div className="grid min-h-0 flex-1 gap-3 p-4 xl:grid-cols-[200px_minmax(0,1fr)]">
        <nav className="octo-surface-soft min-h-0 overflow-y-auto rounded-[1.25rem] p-2">
          <ul className="space-y-1 pr-1">
            {sections.map(({ id, label, icon: Icon }) => {
              const active = activeSection === id;
              return (
                <li key={id}>
                  <button
                    type="button"
                    onClick={() => handleSectionChange(id as SettingsSection)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors",
                      active
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <Icon className="size-4" />
                    <span>{label}</span>
                    {id === "update" && hasUpdate && (
                      <span className="ml-auto text-red-500 text-base font-bold" aria-label="Update available">❗</span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
        <ScrollArea className="octo-surface-soft h-full min-h-0 rounded-[1.25rem]">
          <div className="space-y-7 p-5">
            {activeSection === "overview" && <SystemSettingsPage />}
            {activeSection === "appearance" && <AppearanceSettingsPage />}
            {activeSection === "bootstrap" && <BootstrapSettingsPage />}
            {activeSection === "evolution" && <EvolutionConfigPage />}
            {activeSection === "system-guard" && <SystemGuardSettingsPage />}
            {activeSection === "runtime-health" && <RuntimeHealthSettingsPage />}
            {activeSection === "rag" && <RagSettingsPage />}
            {activeSection === "system-execution" && <SystemExecutionSettingsPage />}
            {activeSection === "tools" && <ToolsHubPage />}
            {activeSection === "memory" && <MemorySettingsPage />}
            {activeSection === "notification" && <NotificationSettingsPage />}
            {activeSection === "update" && <UpdateSettingsPage />}
            {activeSection === "about" && <AboutSettingsPage />}
          </div>
        </ScrollArea>
      </div>
    </aside>
  );
}
