"use client";

import { useEffect, useRef } from "react";

import { useTheme } from "@/components/theme-provider";
import { useLocalSettings } from "@/core/settings";
import {
  APPEARANCE_PRESETS,
  DEFAULT_APPEARANCE_PRESET,
  SYSTEM_DARK_TOKENS,
  getPresetTokens,
} from "@/core/settings/appearance-presets";

export function ThemePresetController() {
  const [settings] = useLocalSettings();
  const { theme, setTheme } = useTheme();
  const styleRef = useRef<HTMLStyleElement | null>(null);

  useEffect(() => {
    const presetId = settings.appearance.preset;
    const def = APPEARANCE_PRESETS.find((p) => p.id === presetId);
    if (!def) return;

    document.documentElement.dataset.appearance = presetId;

    // Determine which tokens to inject
    const isSystemDark =
      presetId === DEFAULT_APPEARANCE_PRESET && theme === "dark";
    const tokens = isSystemDark ? SYSTEM_DARK_TOKENS : getPresetTokens(def);
    const colorScheme = def.isDark || isSystemDark ? "dark" : "light";

    // Generate CSS rule from tokens
    let css = `:root[data-appearance="${presetId}"] {\n  color-scheme: ${colorScheme};\n`;
    for (const [key, value] of Object.entries(tokens)) {
      css += `  --${key}: ${value};\n`;
    }
    css += "}\n";

    // Inject/update <style> element
    if (!styleRef.current) {
      styleRef.current = document.createElement("style");
      styleRef.current.id = "preset-theme-css";
      document.head.appendChild(styleRef.current);
    }
    styleRef.current.textContent = css;

    // Sync the document theme (avoid no-op calls to prevent loops)
    const expectedTheme = colorScheme;
    if (!isSystemDark && theme !== expectedTheme) {
      setTheme(expectedTheme);
    }
  }, [settings.appearance.preset, theme, setTheme]);

  return null;
}