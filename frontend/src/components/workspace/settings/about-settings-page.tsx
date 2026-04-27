"use client";

import { Streamdown } from "streamdown";

import { Card, CardContent } from "@/components/ui/card";


import { aboutMarkdown } from "./about-content";

export function AboutSettingsPage() {
  const hasAboutContent = aboutMarkdown.trim().length > 0;

  return (
    <Card variant="compact">
      <CardContent className="pt-4">
        {hasAboutContent ? <Streamdown>{aboutMarkdown}</Streamdown> : null}
      </CardContent>
    </Card>
  );
}
