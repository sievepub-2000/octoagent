"use client";

import { MoonIcon, SunIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { useTheme } from "@/components/theme-provider";
import { Separator } from "@/components/ui/separator";
import { enUS, isLocale, ja, ko, zhCN, zhTW, type Locale } from "@/core/i18n";
import { useI18n } from "@/core/i18n/hooks";
import {
  APPEARANCE_PRESETS,
  DEFAULT_APPEARANCE_PRESET,
  type AppearancePresetId,
} from "@/core/settings/appearance-presets";
import { useLocalSettings } from "@/core/settings/hooks";
import { cn } from "@/lib/utils";

import { SettingsSection } from "./settings-section";

const languageOptions: { value: Locale; label: string; flag: string }[] = [
  { value: "en-US", label: enUS.locale.localName, flag: "🇺🇸" },
  { value: "ja", label: ja.locale.localName, flag: "🇯🇵" },
  { value: "ko", label: ko.locale.localName, flag: "🇰🇷" },
  { value: "zh-CN", label: zhCN.locale.localName, flag: "🇨🇳" },
  { value: "zh-TW", label: zhTW.locale.localName, flag: "🇹🇼" },
];

const LOCALE_TO_LANGUAGE: Record<Locale, string> = {
  "en-US": "English",
  ja: "Japanese",
  ko: "Korean",
  "zh-CN": "Simplified Chinese",
  "zh-TW": "Traditional Chinese",
};

const PRESET_LABELS: Record<Locale, Record<string, string>> = {
  "en-US": {
    "pure-light": "Light",
    "neumorphic-light": "Purple Blue",
    "verdant-solar": "Blue Gold",
    "sunlit-canopy": "Lime Sun",
    "midnight-indigo": "Copper Ink",
    "vanilla-cream": "Cream Tan",
    "terracotta-sand": "Clay Sand",
    "stone-olive": "Stone Olive",
    "cactus-green": "Cactus",
    "fresh-pink": "Fresh Pink",
    "earth-ink": "Earth Ink",
  },
  ja: {
    "pure-light": "淡色",
    "neumorphic-light": "紫藍",
    "verdant-solar": "藍金",
    "sunlit-canopy": "黄緑",
    "midnight-indigo": "銅墨",
    "vanilla-cream": "乳茶",
    "terracotta-sand": "陶砂",
    "stone-olive": "石橄",
    "cactus-green": "墨緑",
    "fresh-pink": "萬粉",
    "earth-ink": "土墨",
  },
  ko: {
    "pure-light": "라이트",
    "neumorphic-light": "보라파랑",
    "verdant-solar": "블루골드",
    "sunlit-canopy": "황록",
    "midnight-indigo": "동묵",
    "vanilla-cream": "크림",
    "terracotta-sand": "토사",
    "stone-olive": "석올",
    "cactus-green": "선인장",
    "fresh-pink": "핀크",
    "earth-ink": "토묵",
  },
  "zh-CN": {
    "pure-light": "浅色",
    "neumorphic-light": "紫蓝",
    "verdant-solar": "蓝金",
    "sunlit-canopy": "黄绿",
    "midnight-indigo": "铜墨",
    "vanilla-cream": "米棕",
    "terracotta-sand": "陶砂",
    "stone-olive": "石橄",
    "cactus-green": "墨绿",
    "fresh-pink": "萌粉",
    "earth-ink": "土墨",
  },
  "zh-TW": {
    "pure-light": "淺色",
    "neumorphic-light": "紫藍",
    "verdant-solar": "藍金",
    "sunlit-canopy": "黃綠",
    "midnight-indigo": "銅墨",
    "vanilla-cream": "米棕",
    "terracotta-sand": "陶砂",
    "stone-olive": "石橄",
    "cactus-green": "墨綠",
    "fresh-pink": "萌粉",
    "earth-ink": "土墨",
  },
};

export function AppearanceSettingsPage() {
  const { t, locale, changeLocale } = useI18n();
  const [settings, setSettings] = useLocalSettings();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const currentPreset = settings.appearance.preset;
  const presetLabels = PRESET_LABELS[locale];

  // Active-state helpers — deferred until mounted to avoid hydration mismatch
  const isPresetActive = (id: AppearancePresetId) => {
    if (!mounted) return false;
    const def = APPEARANCE_PRESETS.find((p) => p.id === id);
    const expectedTheme = def?.isDark ? "dark" : "light";
    return theme === expectedTheme && currentPreset === id;
  };
  const isDarkActive = mounted && theme === "dark" && currentPreset === DEFAULT_APPEARANCE_PRESET;
  const isLightActive = mounted && theme === "light" && currentPreset === DEFAULT_APPEARANCE_PRESET;

  const handlePresetClick = (id: AppearancePresetId) => {
    const def = APPEARANCE_PRESETS.find((p) => p.id === id);
    setTheme(def?.isDark ? "dark" : "light");
    setSettings("appearance", { preset: id });
  };

  return (
    <div className="space-y-6">
      {/* Language – clickable tab cards */}
      <SettingsSection
        title={t.settings.appearance.languageTitle}
        description={t.settings.appearance.languageDescription}
      >
        <div className="flex flex-wrap gap-2">
          {languageOptions.map((item) => {
            const active = locale === item.value;
            return (
              <button
                key={item.value}
                type="button"
                onClick={() => {
                  if (isLocale(item.value) && item.value !== locale) {
                    changeLocale(item.value);
                    setSettings("context", {
                      conversation_language: LOCALE_TO_LANGUAGE[item.value],
                    });
                    window.location.reload();
                  }
                }}
                className={cn(
                  "flex items-center gap-2 rounded-lg border px-3 py-2 transition-all",
                  active
                    ? "border-primary bg-primary/5 ring-primary/30 shadow-sm ring-2"
                    : "hover:border-border hover:shadow-sm",
                )}
              >
                <span className="text-base">{item.flag}</span>
                <span className="text-xs font-medium">{item.label}</span>
              </button>
            );
          })}
        </div>
      </SettingsSection>
      <Separator />

      <SettingsSection
        title={t.settings.appearance.themeTitle}
        description={t.settings.appearance.themeDescription}
      >
        <div className="flex max-w-[18rem] flex-col gap-2">
          {/* Light (浅色) */}
          <button
            type="button"
            onClick={() => {
              setTheme("light");
              setSettings("appearance", { preset: DEFAULT_APPEARANCE_PRESET });
            }}
            className={cn(
              "flex min-h-10 w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-all",
              isLightActive
                ? "border-primary ring-primary/30 shadow-sm ring-2"
                : "hover:border-border hover:shadow-sm",
            )}
          >
            <SunIcon className="size-3.5 shrink-0 text-muted-foreground" />
            <div className="flex gap-1">
              <span className="size-4 rounded-sm border border-black/10 bg-neutral-100" />
              <span className="size-4 rounded-sm border border-black/10 bg-neutral-200" />
              <span className="size-4 rounded-sm border border-black/10 bg-white" />
            </div>
            <span className="text-xs font-medium">
              {t.settings.appearance.light}
            </span>
          </button>

          {/* Dark */}
          <button
            type="button"
            onClick={() => {
              setTheme("dark");
              setSettings("appearance", { preset: DEFAULT_APPEARANCE_PRESET });
            }}
            className={cn(
              "flex min-h-10 w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-all",
              isDarkActive
                ? "border-primary ring-primary/30 shadow-sm ring-2"
                : "hover:border-border hover:shadow-sm",
            )}
          >
            <MoonIcon className="size-3.5 shrink-0 text-muted-foreground" />
            <div className="flex gap-1">
              <span className="size-4 rounded-sm border border-white/10" style={{ backgroundColor: '#68442C' }} />
              <span className="size-4 rounded-sm border border-white/10" style={{ backgroundColor: '#A17248' }} />
              <span className="size-4 rounded-sm border border-white/10" style={{ backgroundColor: '#5C4A3C' }} />
            </div>
            <span className="text-xs font-medium">
              {t.settings.appearance.dark}
            </span>
          </button>

          {/* Color presets — each one sets light mode + that palette */}
          {APPEARANCE_PRESETS.filter((p) => p.id !== DEFAULT_APPEARANCE_PRESET).map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => handlePresetClick(preset.id)}
              className={cn(
                "flex min-h-10 w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-all",
                isPresetActive(preset.id)
                  ? "border-primary ring-primary/30 shadow-sm ring-2"
                  : "hover:border-border hover:shadow-sm",
              )}
            >
              <div className="flex gap-1">
                {preset.swatches.map((swatch) => (
                  <span
                    key={swatch}
                    className="size-4 rounded-sm border border-black/10"
                    style={{ backgroundColor: swatch }}
                  />
                ))}
              </div>
              <span className="text-xs font-medium">
                {presetLabels[preset.id] ?? preset.name}
              </span>
            </button>
          ))}
        </div>
      </SettingsSection>

    </div>
  );
}
