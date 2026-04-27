export const SUPPORTED_LOCALES = ["en-US", "ja", "ko", "zh-CN", "zh-TW"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en-US";

export function isLocale(value: string): value is Locale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

export function normalizeLocale(locale: string | null | undefined): Locale {
  if (!locale) {
    return DEFAULT_LOCALE;
  }

  if (isLocale(locale)) {
    return locale;
  }

  const lower = locale.toLowerCase();

  if (lower.startsWith("ja")) {
    return "ja";
  }

  if (lower.startsWith("ko")) {
    return "ko";
  }

  if (lower === "zh-tw" || lower === "zh-hant" || lower.startsWith("zh-hant")) {
    return "zh-TW";
  }

  if (lower.startsWith("zh")) {
    return "zh-CN";
  }

  return DEFAULT_LOCALE;
}

// Helper function to detect browser locale
export function detectLocale(): Locale {
  if (typeof window === "undefined") {
    return DEFAULT_LOCALE;
  }

  const browserLang =
    navigator.language ||
    (navigator as unknown as { userLanguage: string }).userLanguage;

  return normalizeLocale(browserLang);
}
