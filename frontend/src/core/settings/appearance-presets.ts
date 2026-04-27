// ═══════════════════════════════════════════════════════════════
// Appearance Preset System — Unified Seed-Based Template
// ═══════════════════════════════════════════════════════════════
//
// To add a new preset:
//   1. Add its ID to AppearancePresetId
//   2. Add a preset entry to APPEARANCE_PRESETS with seeds
//   3. (Optional) add overrides for fine-tuning
//   That's it — no CSS editing needed.
//
// The ThemePresetController reads getPresetTokens() and injects
// a <style> tag dynamically. globals.css only has :root defaults.
// ═══════════════════════════════════════════════════════════════

export type AppearancePresetId =
  | "pure-light"
  | "neumorphic-light"
  | "verdant-solar"
  | "sunlit-canopy"
  | "midnight-indigo"
  | "vanilla-cream"
  | "terracotta-sand"
  | "stone-olive"
  | "cactus-green"
  | "fresh-pink"
  | "earth-ink";

// ─── Seed Types ───

/** oklch L, C, H tuple */
type LCH = [number, number, number];
/** RGB 0-255 tuple */
type RGB = [number, number, number];

export interface ThemeSeeds {
  bg: LCH;
  fg: LCH;
  primary: LCH;
  accent: LCH;
  bgRgb: RGB;
  glowRgb: RGB;
  shadowRgb: RGB;
}

export type AppearancePreset = {
  id: AppearancePresetId;
  name: string;
  description: string;
  swatches: [string, string, string, string];
  isDark?: boolean;
  seeds: ThemeSeeds;
  overrides?: Record<string, string>;
};

// ─── Utility Functions ───

function o(l: number, c: number, h: number): string {
  return `oklch(${Math.max(0, Math.min(1, l)).toFixed(3)} ${Math.max(0, c).toFixed(4)} ${h.toFixed(1)})`;
}

function rgba(r: number, g: number, b: number, a: number): string {
  const clamp = (v: number) => Math.round(Math.min(255, Math.max(0, v)));
  return `rgba(${clamp(r)}, ${clamp(g)}, ${clamp(b)}, ${a})`;
}

// ─── Dark Theme Template ───

function darkTokens(s: ThemeSeeds): Record<string, string> {
  const [bL, bC, bH] = s.bg;
  const [fL, fC, fH] = s.fg;
  const [pL, pC, pH] = s.primary;
  const [aL, aC, aH] = s.accent;
  const [bR, bG, bB] = s.bgRgb;
  const [gR, gG, gB] = s.glowRgb;
  const [sR, sG, sB] = s.shadowRgb;

  return {
    background: o(bL, bC, bH),
    foreground: o(fL, fC, fH),
    card: o(bL + 0.04, bC + 0.003, bH),
    "card-foreground": o(fL, fC, fH),
    popover: o(bL + 0.04, bC + 0.003, bH),
    "popover-foreground": o(fL, fC, fH),
    primary: o(pL, pC, pH),
    "primary-foreground": o(bL - 0.02, bC * 0.6, bH),
    secondary: o(bL + 0.06, bC * 0.9, bH),
    "secondary-foreground": o(fL - 0.04, fC * 0.8, fH),
    muted: o(bL + 0.04, bC * 0.75, bH),
    "muted-foreground": o((bL + fL) * 0.54, fC * 0.5, fH),
    accent: o(aL, aC, aH),
    "accent-foreground": o(fL, fC * 0.7, fH),
    destructive: "oklch(0.600 0.2000 25.0)",
    border: o(bL + 0.10, bC * 1.1, bH),
    input: o(bL + 0.02, bC, bH),
    ring: o(pL, pC, pH),
    "chart-1": o(pL, pC, pH),
    "chart-2": o(aL, aC, aH),
    "chart-3": o(0.60, 0.06, (aH + 140) % 360),
    "chart-4": o(0.50, 0.06, 330),
    "chart-5": o(0.65, 0.06, 120),
    sidebar: o(bL - 0.02, bC * 0.85, bH),
    "sidebar-foreground": o(fL, fC, fH),
    "sidebar-primary": o(pL, pC, pH),
    "sidebar-primary-foreground": o(bL - 0.02, bC * 0.6, bH),
    "sidebar-accent": o(bL + 0.06, bC * 0.9, bH),
    "sidebar-accent-foreground": o(fL, fC * 0.7, fH),
    "sidebar-border": o(bL + 0.10, bC * 1.1, bH),
    "sidebar-ring": o(pL, pC, pH),
    "page-glow-1": rgba(gR, gG, gB, 0.08),
    "page-glow-2": rgba(sR, sG, sB, 0.10),
    "page-bg-start": rgba(bR, bG, bB, 0.99),
    "page-bg-end": rgba(bR, bG, bB, 0.99),
    "panel-start": rgba(bR + 8, bG + 8, bB + 8, 0.94),
    "panel-end": rgba(bR + 4, bG + 4, bB + 4, 0.90),
    "panel-border": rgba(gR, gG, gB, 0.16),
    "panel-shadow": rgba(0, 0, 0, 0.35),
    "grid-line": rgba(sR, sG, sB, 0.06),
    "grid-radial": rgba(sR, sG, sB, 0.04),
    "emboss-top": rgba(255, 255, 255, 0.06),
    "emboss-bottom": rgba(0, 0, 0, 0.30),
    "emboss-shadow": rgba(0, 0, 0, 0.30),
    "emboss-shadow-strong": rgba(0, 0, 0, 0.40),
    "neu-light": rgba(255, 255, 255, 0.08),
    "neu-dark": rgba(0, 0, 0, 0.45),
    "neu-light-strong": rgba(255, 255, 255, 0.14),
    "neu-dark-strong": rgba(0, 0, 0, 0.55),
    "neu-inset-light": rgba(255, 255, 255, 0.05),
    "neu-inset-dark": rgba(0, 0, 0, 0.30),
  };
}

// ─── Light Theme Template ───

function lightTokens(s: ThemeSeeds): Record<string, string> {
  const [bL, bC, bH] = s.bg;
  const [fL, fC, fH] = s.fg;
  const [pL, pC, pH] = s.primary;
  const [aL, aC, aH] = s.accent;
  const [bR, bG, bB] = s.bgRgb;
  const [gR, gG, gB] = s.glowRgb;
  const [sR, sG, sB] = s.shadowRgb;

  return {
    background: o(bL, bC, bH),
    foreground: o(fL, fC, fH),
    card: o(bL + 0.015, bC * 0.85, bH),
    "card-foreground": o(fL, fC, fH),
    popover: o(bL + 0.015, bC * 0.85, bH),
    "popover-foreground": o(fL, fC, fH),
    primary: o(pL, pC, pH),
    "primary-foreground": o(Math.min(0.99, bL + 0.03), bC * 0.4, bH),
    secondary: o(bL - 0.025, bC * 1.1, bH),
    "secondary-foreground": o(fL, fC, fH),
    muted: o(bL - 0.035, bC * 0.9, bH),
    "muted-foreground": o((bL + fL) * 0.52, fC * 0.5, fH),
    accent: o(aL, aC, aH),
    "accent-foreground": o(fL + 0.02, fC, fH),
    destructive: "oklch(0.600 0.2000 25.0)",
    border: o(bL - 0.08, bC * 1.3, bH),
    input: o(bL, bC, bH),
    ring: o(pL, pC, pH),
    "chart-1": o(pL, pC, pH),
    "chart-2": o(aL, aC, aH),
    "chart-3": o(0.65, 0.01, 180),
    "chart-4": o(0.52, 0.01, 330),
    "chart-5": o(0.70, 0.01, 120),
    sidebar: o(bL - 0.01, bC, bH),
    "sidebar-foreground": o(fL, fC, fH),
    "sidebar-primary": o(pL, pC, pH),
    "sidebar-primary-foreground": o(Math.min(0.99, bL + 0.03), bC * 0.4, bH),
    "sidebar-accent": o(bL - 0.03, bC * 1.1, bH),
    "sidebar-accent-foreground": o(fL + 0.02, fC, fH),
    "sidebar-border": o(bL - 0.08, bC * 1.3, bH),
    "sidebar-ring": o(pL, pC, pH),
    "page-glow-2": rgba(sR, sG, sB, 0.28),
    "page-bg-end": rgba(bR, bG, bB, 0.99),
    "page-glow-1": rgba(gR, gG, gB, 0.45),
    "page-bg-start": rgba(bR, bG, bB, 0.99),
    "panel-start": rgba(Math.min(255, bR + 14), Math.min(255, bG + 14), Math.min(255, bB + 14), 0.92),
    "panel-end": rgba(Math.min(255, bR + 4), Math.min(255, bG + 4), Math.min(255, bB + 4), 0.86),
    "panel-border": rgba(sR, sG, sB, 0.06),
    "panel-shadow": rgba(sR, sG, sB, 0.65),
    "grid-line": rgba(sR, sG, sB, 0.06),
    "grid-radial": rgba(Math.min(255, bR + 15), Math.min(255, bG + 15), Math.min(255, bB + 15), 0.45),
    "emboss-top": rgba(255, 255, 255, 0.85),
    "emboss-bottom": rgba(sR, sG, sB, 0.28),
    "emboss-shadow": rgba(sR, sG, sB, 0.38),
    "emboss-shadow-strong": rgba(sR, sG, sB, 0.52),
    "neu-light": rgba(255, 255, 255, 0.92),
    "neu-dark": rgba(sR, sG, sB, 0.52),
    "neu-light-strong": rgba(255, 255, 255, 1),
    "neu-dark-strong": rgba(sR, sG, sB, 0.70),
    "neu-inset-light": rgba(255, 255, 255, 0.70),
    "neu-inset-dark": rgba(sR, sG, sB, 0.25),
  };
}

// ─── Public API ───

export function getPresetTokens(preset: AppearancePreset): Record<string, string> {
  const base = preset.isDark ? darkTokens(preset.seeds) : lightTokens(preset.seeds);
  return preset.overrides ? { ...base, ...preset.overrides } : base;
}

/** System dark mode tokens — used when pure-light + dark toggle */
export const SYSTEM_DARK_TOKENS: Record<string, string> = {
  background: "oklch(0.230 0.0120 55.0)",
  foreground: "oklch(0.920 0.0100 55.0)",
  card: "oklch(0.270 0.0140 55.0)",
  "card-foreground": "oklch(0.920 0.0100 55.0)",
  popover: "oklch(0.260 0.0130 55.0)",
  "popover-foreground": "oklch(0.920 0.0100 55.0)",
  primary: "oklch(0.580 0.0900 55.0)",
  "primary-foreground": "oklch(0.200 0.0100 55.0)",
  secondary: "oklch(0.310 0.0150 55.0)",
  "secondary-foreground": "oklch(0.920 0.0100 55.0)",
  muted: "oklch(0.290 0.0130 55.0)",
  "muted-foreground": "oklch(0.650 0.0200 55.0)",
  accent: "oklch(0.540 0.0600 55.0)",
  "accent-foreground": "oklch(0.920 0.0100 55.0)",
  destructive: "oklch(0.700 0.1900 22.0)",
  border: "oklch(0.380 0.0300 55.0 / 30%)",
  input: "oklch(0.380 0.0300 55.0 / 35%)",
  ring: "oklch(0.580 0.0900 55.0)",
  "chart-1": "oklch(0.580 0.0900 55.0)",
  "chart-2": "oklch(0.540 0.0600 55.0)",
  "chart-3": "oklch(0.600 0.0700 180.0)",
  "chart-4": "oklch(0.550 0.0800 330.0)",
  "chart-5": "oklch(0.600 0.0800 120.0)",
  sidebar: "oklch(0.220 0.0110 55.0)",
  "sidebar-foreground": "oklch(0.920 0.0100 55.0)",
  "sidebar-primary": "oklch(0.580 0.0900 55.0)",
  "sidebar-primary-foreground": "oklch(0.200 0.0100 55.0)",
  "sidebar-accent": "oklch(0.310 0.0150 55.0)",
  "sidebar-accent-foreground": "oklch(0.920 0.0100 55.0)",
  "sidebar-border": "oklch(0.380 0.0300 55.0 / 30%)",
  "sidebar-ring": "oklch(0.580 0.0900 55.0)",
  "page-glow-1": "rgba(161, 114, 72, 0.10)",
  "page-glow-2": "rgba(104, 68, 44, 0.14)",
  "page-bg-start": "rgba(40, 36, 32, 0.98)",
  "page-bg-end": "rgba(40, 36, 32, 0.98)",
  "panel-start": "rgba(52, 46, 40, 0.85)",
  "panel-end": "rgba(44, 40, 36, 0.78)",
  "panel-border": "rgba(161, 114, 72, 0.10)",
  "panel-shadow": "rgba(0, 0, 0, 0.32)",
  "grid-line": "rgba(255, 255, 255, 0.04)",
  "grid-radial": "rgba(255, 255, 255, 0.03)",
  "emboss-top": "rgba(255, 255, 255, 0.06)",
  "emboss-bottom": "rgba(0, 0, 0, 0.3)",
  "emboss-shadow": "rgba(0, 0, 0, 0.3)",
  "emboss-shadow-strong": "rgba(0, 0, 0, 0.4)",
  "neu-light": "rgba(255, 255, 255, 0.09)",
  "neu-dark": "rgba(0, 0, 0, 0.48)",
  "neu-light-strong": "rgba(255, 255, 255, 0.15)",
  "neu-dark-strong": "rgba(0, 0, 0, 0.58)",
  "neu-inset-light": "rgba(255, 255, 255, 0.06)",
  "neu-inset-dark": "rgba(0, 0, 0, 0.32)",
};

// ─── Preset Definitions ───

export const DEFAULT_APPEARANCE_PRESET: AppearancePresetId = "pure-light";

export const APPEARANCE_PRESETS: AppearancePreset[] = [
  {
    id: "pure-light",
    name: "Light",
    description: "Clean neutral neumorphic palette — warm white and soft grays.",
    swatches: ["#e8eaed", "#d1d5db", "#6b7280", "#9ca3af"],
    seeds: {
      bg: [0.965, 0.002, 250],
      fg: [0.22, 0.008, 250],
      primary: [0.42, 0.012, 250],
      accent: [0.92, 0.004, 250],
      bgRgb: [238, 240, 243],
      glowRgb: [255, 255, 255],
      shadowRgb: [170, 180, 195],
    },
  },
  {
    id: "neumorphic-light",
    name: "Purple Blue",
    description: "Soft blue-gray palette with purple and coral accents.",
    swatches: ["#e0e5ec", "#a3b1c6", "#7c6bc4", "#f0a08c"],
    seeds: {
      bg: [0.935, 0.008, 260],
      fg: [0.28, 0.025, 260],
      primary: [0.54, 0.14, 280],
      accent: [0.76, 0.10, 35],
      bgRgb: [224, 229, 236],
      glowRgb: [255, 255, 255],
      shadowRgb: [163, 177, 198],
    },
  },
  {
    id: "verdant-solar",
    name: "Verdant Solar",
    description: "深海军蓝底，薰衣草蓝与暖桃橙的现代配色。",
    swatches: ["#161E31", "#676f9d", "#424669", "#f8b179"],
    isDark: true,
    seeds: {
      bg: [0.237, 0.039, 266],
      fg: [0.95, 0.005, 270],
      primary: [0.816, 0.110, 59],
      accent: [0.554, 0.072, 276],
      bgRgb: [22, 30, 49],
      glowRgb: [248, 177, 121],
      shadowRgb: [103, 111, 157],
    },
  },
  {
    id: "sunlit-canopy",
    name: "Sunlit Canopy",
    description: "Sage, avocado, pollen yellow, and airy ivory.",
    swatches: ["#f9f5e9", "#bdd4a6", "#52734d", "#ffd66b"],
    seeds: {
      bg: [0.975, 0.023, 108],
      fg: [0.34, 0.050, 145],
      primary: [0.56, 0.10, 135],
      accent: [0.86, 0.13, 95],
      bgRgb: [244, 250, 232],
      glowRgb: [255, 255, 255],
      shadowRgb: [120, 150, 85],
    },
  },
  {
    id: "midnight-indigo",
    name: "铜墨",
    description: "美式复古深色 — 暖米、钢蓝与亮橙的高级感搭配。",
    swatches: ["#1a1a1a", "#e8d8c9", "#4b607f", "#f3701e"],
    isDark: true,
    seeds: {
      bg: [0.22, 0.005, 55],
      fg: [0.95, 0.008, 55],
      primary: [0.692, 0.182, 47],
      accent: [0.485, 0.056, 258],
      bgRgb: [30, 28, 26],
      glowRgb: [243, 112, 30],
      shadowRgb: [75, 96, 127],
    },
  },
  {
    id: "vanilla-cream",
    name: "Vanilla Cream",
    description: "Soft editorial neutrals with cocoa text and pale gold.",
    swatches: ["#fbf4ea", "#eadbca", "#62493d", "#d7ae6b"],
    seeds: {
      bg: [0.98, 0.010, 90],
      fg: [0.38, 0.030, 40],
      primary: [0.58, 0.050, 50],
      accent: [0.83, 0.080, 80],
      bgRgb: [251, 244, 234],
      glowRgb: [255, 255, 255],
      shadowRgb: [160, 135, 110],
    },
  },
  {
    id: "terracotta-sand",
    name: "陶砂",
    description: "深绿与暖棕底色，奶油与焦糖金的热带咖啡风情。",
    swatches: ["#1e3a2f", "#f0e4cc", "#b05c28", "#d4a843"],
    isDark: true,
    seeds: {
      bg: [0.29, 0.035, 160],
      fg: [0.92, 0.020, 85],
      primary: [0.58, 0.120, 45],
      accent: [0.72, 0.100, 80],
      bgRgb: [30, 58, 47],
      glowRgb: [176, 92, 40],
      shadowRgb: [212, 168, 67],
    },
  },
  {
    id: "stone-olive",
    name: "灰蓝",
    description: "粉蓝与深青搭配，现代家居风格的清爽调色板。",
    swatches: ["#c8dde8", "#1a3a4a", "#6a8a8a", "#f5f8fa"],
    seeds: {
      bg: [0.885, 0.027, 231],
      fg: [0.332, 0.047, 232],
      primary: [0.332, 0.047, 232],
      accent: [0.609, 0.036, 196],
      bgRgb: [200, 221, 232],
      glowRgb: [245, 248, 250],
      shadowRgb: [80, 120, 140],
    },
  },

  {
    id: "cactus-green",
    name: "墨绿",
    description: "沙漠仙人掌色系 — 从深墨绿到嫩绿，金色点缀。",
    swatches: ["#164A41", "#4D774E", "#9DC88D", "#F1B24A"],
    isDark: true,
    seeds: {
      bg: [0.338, 0.048, 168],
      fg: [0.95, 0.010, 100],
      primary: [0.76, 0.100, 90],
      accent: [0.78, 0.080, 140],
      bgRgb: [22, 74, 65],
      glowRgb: [241, 178, 74],
      shadowRgb: [157, 200, 141],
    },
  },
  {
    id: "fresh-pink",
    name: "萌粉",
    description: "柔和3D UI风 — 粉杏、天蓝、奶油白的治愈萌系。",
    swatches: ["#faf3ec", "#e8a89c", "#8fb4d0", "#d49080"],
    seeds: {
      bg: [0.97, 0.010, 60],
      fg: [0.35, 0.040, 25],
      primary: [0.76, 0.070, 18],
      accent: [0.74, 0.050, 240],
      bgRgb: [250, 243, 236],
      glowRgb: [143, 180, 208],
      shadowRgb: [212, 144, 128],
    },
  },
  {
    id: "earth-ink",
    name: "土墨",
    description: "产品级灰阶设计 — 青灰主色调搭配暖赭石焦点。",
    swatches: ["#e8e4df", "#3e6b6a", "#8b6358", "#c4c0bb"],
    seeds: {
      bg: [0.94, 0.005, 70],
      fg: [0.30, 0.030, 190],
      primary: [0.48, 0.060, 185],
      accent: [0.52, 0.050, 40],
      bgRgb: [232, 228, 223],
      glowRgb: [139, 99, 88],
      shadowRgb: [62, 107, 106],
    },
  },
];

export function isAppearancePresetId(value: string | null | undefined): value is AppearancePresetId {
  return APPEARANCE_PRESETS.some((preset) => preset.id === value);
}