"use client";

import { ActivityIcon, BellIcon, BlocksIcon, BrainIcon, DownloadCloudIcon, InfoIcon, LaptopIcon, PaletteIcon, PlugZapIcon, SparklesIcon, WebhookIcon, WrenchIcon } from "lucide-react";
import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

const RuntimeHealthSettingsPage = dynamic(() => import("./runtime-health-settings-page").then((module) => module.RuntimeHealthSettingsPage));
const AppearanceSettingsPage = dynamic(() => import("./appearance-settings-page").then((module) => module.AppearanceSettingsPage));
const ModelsConfigPage = dynamic(() => import("@/app/workspace/config/models/page"));
const SkillsConfigPage = dynamic(() => import("@/app/workspace/config/skills/page"));
const MCPConfigPage = dynamic(() => import("@/app/workspace/config/mcp/page"));
const PluginsConfigPage = dynamic(() => import("@/app/workspace/config/plugins/page"));
const HooksSettingsPage = dynamic(() => import("./hooks-settings-page").then((module) => module.HooksSettingsPage));
const ToolsHubPage = dynamic(() => import("@/app/workspace/config/tools/page"));
const MemorySettingsPage = dynamic(() => import("./memory-settings-page").then((module) => module.MemorySettingsPage));
const SystemExecutionSettingsPage = dynamic(() => import("./system-execution-settings-page").then((module) => module.SystemExecutionSettingsPage));
const NotificationSettingsPage = dynamic(() => import("./notification-settings-page").then((module) => module.NotificationSettingsPage));
const UpdateSettingsPage = dynamic(() => import("./update-settings-page").then((module) => module.UpdateSettingsPage));
const AboutSettingsPage = dynamic(() => import("./about-settings-page").then((module) => module.AboutSettingsPage));

export type SettingsSectionId =
  | "general"
  | "appearance"
  | "models"
  | "skills"
  | "mcp"
  | "plugins"
  | "hooks"
  | "tools"
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
    { group: t.settings.sections.overview, id: "general", label: t.settings.sections.overview, icon: ActivityIcon },
    { group: t.settings.sections.overview, id: "appearance", label: t.settings.sections.appearance, icon: PaletteIcon },
    { group: t.sidebar.configuration, id: "models", label: t.settings.sections.models, icon: SparklesIcon },
    { group: t.sidebar.configuration, id: "skills", label: t.settings.sections.skills, icon: BrainIcon },
    { group: t.sidebar.configuration, id: "mcp", label: t.settings.sections.mcp, icon: PlugZapIcon },
    { group: t.sidebar.configuration, id: "plugins", label: t.settings.sections.plugins, icon: BlocksIcon },
    { group: t.sidebar.configuration, id: "hooks", label: t.settings.sections.hooks, icon: WebhookIcon },
    { group: t.sidebar.configuration, id: "tools", label: t.settings.sections.tools, icon: WrenchIcon },
    { group: t.settings.system.title, id: "memory", label: t.settings.sections.memory, icon: BrainIcon },
    { group: t.settings.system.title, id: "permissions", label: t.settings.sections.systemExecution, icon: LaptopIcon },
    { group: t.settings.system.title, id: "notifications", label: t.settings.sections.notification, icon: BellIcon },
    { group: t.settings.system.title, id: "update", label: t.settings.sections.update, icon: DownloadCloudIcon },
    { group: t.settings.system.title, id: "about", label: t.settings.sections.about, icon: InfoIcon },
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
          <h2 className="text-lg font-semibold tracking-[-0.03em]">{t.settings.title}</h2>
          <p className="text-sm text-muted-foreground">{t.settings.description}</p>
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
                    {id === "update" && hasUpdate ? <span className="ml-auto size-2 rounded-full bg-red-500" aria-label={t.settings.sections.update} /> : null}
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
          {activeSection === "tools" && <ToolsHubPage />}
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
