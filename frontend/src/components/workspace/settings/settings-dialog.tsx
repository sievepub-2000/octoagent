"use client";

import { ActivityIcon, BellIcon, BlocksIcon, BrainIcon, DownloadCloudIcon, InfoIcon, LaptopIcon, PaletteIcon, PlugZapIcon, SparklesIcon, WebhookIcon } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import MCPConfigPage from "@/app/workspace/config/mcp/page";
import ModelsConfigPage from "@/app/workspace/config/models/page";
import PluginsConfigPage from "@/app/workspace/config/plugins/page";
import SkillsConfigPage from "@/app/workspace/config/skills/page";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AboutSettingsPage } from "@/components/workspace/settings/about-settings-page";
import { AppearanceSettingsPage } from "@/components/workspace/settings/appearance-settings-page";
import { HooksSettingsPage } from "@/components/workspace/settings/hooks-settings-page";
import { MemorySettingsPage } from "@/components/workspace/settings/memory-settings-page";
import { NotificationSettingsPage } from "@/components/workspace/settings/notification-settings-page";
import { RuntimeHealthSettingsPage } from "@/components/workspace/settings/runtime-health-settings-page";
import { SystemExecutionSettingsPage } from "@/components/workspace/settings/system-execution-settings-page";
import { UpdateSettingsPage } from "@/components/workspace/settings/update-settings-page";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

export type SettingsSectionId =
  | "general"
  | "appearance"
  | "models"
  | "skills"
  | "mcp"
  | "plugins"
  | "hooks"
  | "memory"
  | "permissions"
  | "notifications"
  | "update"
  | "about";

type SettingsPanelProps = {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  defaultSection?: SettingsSectionId;
};

export function SettingsPanel({ defaultSection = "general", open, onOpenChange }: SettingsPanelProps) {
  const { t } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [activeSection, setActiveSection] = useState<SettingsSectionId>(defaultSection);
  const [hasUpdate, setHasUpdate] = useState(false);

  useEffect(() => {
    if (!open) return;
    fetch(`${process.env.NEXT_PUBLIC_API_URL ?? ""}/api/system/update/check`)
      .then((response) => response.ok ? response.json() : null)
      .then((data) => setHasUpdate(Boolean(data?.has_update)))
      .catch(() => undefined);
  }, [open]);

  useEffect(() => {
    if (open) setActiveSection(defaultSection);
  }, [defaultSection, open]);

  const sections = useMemo(() => [
    { group: "General", id: "general", label: "General", icon: ActivityIcon },
    { group: "General", id: "appearance", label: t.settings.sections.appearance, icon: PaletteIcon },
    { group: "AI & capabilities", id: "models", label: "Models", icon: SparklesIcon },
    { group: "AI & capabilities", id: "skills", label: "Skills", icon: BrainIcon },
    { group: "AI & capabilities", id: "mcp", label: "MCP servers", icon: PlugZapIcon },
    { group: "AI & capabilities", id: "plugins", label: "Plugins", icon: BlocksIcon },
    { group: "AI & capabilities", id: "hooks", label: "Hooks", icon: WebhookIcon },
    { group: "System", id: "memory", label: t.settings.sections.memory, icon: BrainIcon },
    { group: "System", id: "permissions", label: "Permissions", icon: LaptopIcon },
    { group: "System", id: "notifications", label: t.settings.sections.notification, icon: BellIcon },
    { group: "System", id: "update", label: t.settings.sections.update ?? "Update", icon: DownloadCloudIcon },
    { group: "System", id: "about", label: t.settings.sections.about, icon: InfoIcon },
  ] as const, [t]);

  if (!open) return null;

  const changeSection = (section: SettingsSectionId) => {
    setActiveSection(section);
    const next = new URLSearchParams(searchParams.toString());
    next.set("settings", section);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  let lastGroup = "";
  return (
    <aside className="octo-panel flex h-full min-h-0 w-[min(960px,78vw)] min-w-0 max-w-[960px] flex-col rounded-none border-l border-border/40 max-lg:w-[min(760px,86vw)] max-sm:w-full">
      <div className="flex items-start justify-between gap-4 border-b border-border/60 px-5 py-4">
        <div>
          <h2 className="text-lg font-semibold tracking-[-0.03em]">Settings</h2>
          <p className="text-sm text-muted-foreground">Configure models, capabilities, integrations and system behavior.</p>
        </div>
        <button type="button" className="rounded-full border px-3 py-1 text-xs text-muted-foreground hover:text-foreground" onClick={() => onOpenChange?.(false)}>{t.common.close}</button>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-[190px_minmax(0,1fr)] gap-3 p-4 max-sm:grid-cols-1 max-sm:grid-rows-[auto_minmax(0,1fr)]">
        <nav className="octo-surface-soft min-h-0 overflow-y-auto rounded-[1.25rem] p-2 max-sm:max-h-40">
          <ul className="space-y-1">
            {sections.map(({ group, id, label, icon: Icon }) => {
              const showGroup = group !== lastGroup;
              lastGroup = group;
              return (
                <li key={id}>
                  {showGroup ? <div className="px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground first:pt-1">{group}</div> : null}
                  <button type="button" onClick={() => changeSection(id)} className={cn("flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors", activeSection === id ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
                    <Icon className="size-4 shrink-0" /><span className="truncate">{label}</span>
                    {id === "update" && hasUpdate ? <span className="ml-auto size-2 rounded-full bg-red-500" aria-label="Update available" /> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
        <ScrollArea className="octo-surface-soft h-full min-h-0 rounded-[1.25rem]">
          {activeSection === "general" && <div className="p-5"><RuntimeHealthSettingsPage /></div>}
          {activeSection === "appearance" && <div className="p-5"><AppearanceSettingsPage /></div>}
          {activeSection === "models" && <ModelsConfigPage />}
          {activeSection === "skills" && <SkillsConfigPage />}
          {activeSection === "mcp" && <MCPConfigPage />}
          {activeSection === "plugins" && <PluginsConfigPage />}
          {activeSection === "hooks" && <div className="p-5"><HooksSettingsPage /></div>}
          {activeSection === "memory" && <div className="p-5"><MemorySettingsPage /></div>}
          {activeSection === "permissions" && <div className="p-5"><SystemExecutionSettingsPage /></div>}
          {activeSection === "notifications" && <div className="p-5"><NotificationSettingsPage /></div>}
          {activeSection === "update" && <div className="p-5"><UpdateSettingsPage /></div>}
          {activeSection === "about" && <div className="p-5"><AboutSettingsPage /></div>}
        </ScrollArea>
      </div>
    </aside>
  );
}
