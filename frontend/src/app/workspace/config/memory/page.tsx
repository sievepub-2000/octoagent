"use client";

import { BrainIcon } from "lucide-react";

import { MemorySchemaStatusCard } from "@/components/workspace/settings/memory-schema-status-card";
import { MemorySettingsPage } from "@/components/workspace/settings/memory-settings-page";
import { useI18n } from "@/core/i18n/hooks";

export default function MemoryConfigPage() {
  const { t } = useI18n();
  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6">
        <div className="flex items-center gap-2">
          <BrainIcon aria-hidden="true" className="size-5 text-primary" />
          <h1 className="text-lg font-semibold text-foreground">
            {t.settings.memory.title}
          </h1>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {t.settings.memory.description}
        </p>
      </header>
      <MemorySchemaStatusCard />
      <MemorySettingsPage />
    </div>
  );
}
