"use client";

import { usePathname } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

type ThemeName = "light" | "dark" | "system";

type ThemeContextValue = {
  theme: ThemeName;
  resolvedTheme: "light" | "dark";
  setTheme: (theme: ThemeName) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

type ThemeProviderProps = {
  children: ReactNode;
  attribute?: "class" | string;
  defaultTheme?: ThemeName;
  forcedTheme?: ThemeName;
  enableSystem?: boolean;
  disableTransitionOnChange?: boolean;
};

function resolveSystemTheme() {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function readStoredTheme(defaultTheme: ThemeName) {
  if (typeof window === "undefined") return defaultTheme;
  const stored = window.localStorage.getItem("octoagent-theme");
  return stored === "light" || stored === "dark" || stored === "system"
    ? stored
    : defaultTheme;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return context;
}

export function ThemeProvider({
  children,
  attribute = "class",
  defaultTheme = "light",
  forcedTheme,
  enableSystem = true,
}: ThemeProviderProps) {
  const pathname = usePathname();
  const routeForcedTheme = pathname === "/" ? "dark" : forcedTheme;
  const [theme, setThemeState] = useState<ThemeName>(() =>
    readStoredTheme(defaultTheme),
  );
  const selectedTheme = routeForcedTheme ?? theme;
  const resolvedTheme =
    selectedTheme === "system"
      ? enableSystem
        ? resolveSystemTheme()
        : "light"
      : selectedTheme;

  const setTheme = useCallback((nextTheme: ThemeName) => {
    setThemeState(nextTheme);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("octoagent-theme", nextTheme);
    }
  }, []);

  useEffect(() => {
    const root = document.documentElement;

    if (attribute === "class") {
      root.classList.toggle("dark", resolvedTheme === "dark");
      root.style.colorScheme = resolvedTheme;
    } else {
      root.setAttribute(attribute, resolvedTheme);
    }
  }, [attribute, resolvedTheme]);

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
