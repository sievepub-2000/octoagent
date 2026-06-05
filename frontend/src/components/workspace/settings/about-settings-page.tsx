"use client";

import { Streamdown } from "streamdown";

import { Card, CardContent } from "@/components/ui/card";
import { useI18n } from "@/core/i18n/hooks";

import { getAboutMarkdown } from "./about-content";

export function AboutSettingsPage() {
  const { locale } = useI18n();
  const aboutMarkdown = getAboutMarkdown(locale);
  const hasAboutContent = aboutMarkdown.trim().length > 0;

  return (
    <Card variant="compact">
      <CardContent className="pt-4">
        {hasAboutContent ? <Streamdown>{aboutMarkdown}</Streamdown> : null}
      </CardContent>
    </Card>
  );
}
