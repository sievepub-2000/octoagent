import "@/styles/globals.css";
import "katex/dist/katex.min.css";

import { type Metadata } from "next";
import localFont from "next/font/local";

import { ThemePresetController } from "@/components/theme-preset-controller";
import { ThemeProvider } from "@/components/theme-provider";
import { I18nProvider } from "@/core/i18n/context";
import { detectLocaleServer } from "@/core/i18n/server";

export const metadata: Metadata = {
  title: "OctoAgent",
  description: "A LangChain-based framework for building super agents.",
  icons: {
    icon: "/images/octobot-user-transparent.png",
    shortcut: "/images/octobot-user-transparent.png",
    apple: "/images/octobot-user-transparent.png",
  },
};

const geist = localFont({
  src: "../../public/fonts/geist-latin.woff2",
  variable: "--font-geist-sans",
  display: "swap",
});

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = await detectLocaleServer();
  return (
    <html
      lang={locale}
      className={geist.variable}
      suppressContentEditableWarning
      suppressHydrationWarning
    >
      <body suppressHydrationWarning>
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange>
          <I18nProvider initialLocale={locale}>
            <ThemePresetController />
            {children}
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
