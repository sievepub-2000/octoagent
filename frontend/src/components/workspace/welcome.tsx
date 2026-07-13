"use client";

import { useCallback, useEffect, useState } from "react";

import { BrandMark } from "@/components/brand/octo-mark";
import { useI18n } from "@/core/i18n/hooks";
import { useLocalSettings } from "@/core/settings";
import { useSetupStatus } from "@/core/setup";
import { cn } from "@/lib/utils";

import { SetupWizard } from "./setup-wizard";

export interface ContinuationInfo {
  sourceTitle?: string | null;
  messageCount?: number;
  recentMessages?: Array<{ role: string; content: string }>;
}

export function Welcome({ className, continuation }: { className?: string; mode?: "ultra" | "pro" | "thinking" | "flash"; continuation?: ContinuationInfo }) {
  const { t } = useI18n();
  const [settings, setSettings] = useLocalSettings();
  const { status } = useSetupStatus();
  const [showWizard, setShowWizard] = useState(() => !settings.setup.completed);

  useEffect(() => {
    const ready = Boolean(status?.workspace_ready && status.configured_default_model?.trim() && (status.models_configured ?? 0) > 0);
    if (!ready || !status) return;
    setShowWizard(false);
    if (!settings.setup.completed) setSettings("setup", { completed: true, workspace_path: status.workspace_path ?? settings.setup.workspace_path, default_model: status.configured_default_model ?? settings.setup.default_model, sandbox_mode: status.configured_sandbox_mode ?? settings.setup.sandbox_mode });
  }, [setSettings, settings.setup, status]);

  const complete = useCallback(() => setShowWizard(false), []);
  if (showWizard) return <SetupWizard onComplete={complete} />;

  return <div className={cn("mx-auto flex w-full max-w-3xl flex-col items-center justify-center px-6 text-center", className)}><BrandMark className="mb-4 size-9" priority size={36} /><h1 className="text-2xl font-semibold tracking-tight">{continuation ? `Continue ${continuation.sourceTitle || "task"}` : t.welcome.greeting}</h1><p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">{continuation ? `${continuation.messageCount ?? 0} messages from the previous task are ready as context.` : t.welcome.description}</p></div>;
}
