"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { BrandMark, WelcomeArtwork } from "@/components/brand/octo-mark";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/core/i18n/hooks";
import { getWorkspaceLocaleCopy } from "@/core/i18n/workspace-copy";
import { useLocalSettings } from "@/core/settings";
import { useSetupStatus } from "@/core/setup";
import { SYSTEM_SESSION_CONTINUE_PROMPT } from "@/core/threads/system-prompts";
import { cn } from "@/lib/utils";

import { AuroraText } from "../ui/aurora-text";

import { SetupWizard } from "./setup-wizard";

export interface ContinuationInfo {
  sourceTitle?: string | null;
  messageCount?: number;
  recentMessages?: Array<{ role: string; content: string }>;
}

function normalizeWelcomeParagraph(value: string) {
  return value.replace(/\s*\n\s*/g, " ").replace(/\s{2,}/g, " ").trim();
}

export function Welcome({
  className,
  mode: _mode,
  continuation,
}: {
  className?: string;
  mode?: "ultra" | "pro" | "thinking" | "flash";
  continuation?: ContinuationInfo;
}) {
  const { locale, t } = useI18n();
  const copy = getWorkspaceLocaleCopy(locale);
  const [localSettings, setLocalSettings] = useLocalSettings();
  const { status: setupStatus } = useSetupStatus();
  const [showWizard, setShowWizard] = useState(
    () => !localSettings.setup.completed,
  );
  const [hasWaved, setHasWaved] = useState(false);
  const searchParams = useSearchParams();
  const colors = useMemo(() => {
    return ["var(--primary)", "var(--accent)", "var(--primary)"];
  }, []);

  useEffect(() => {
    setHasWaved(true);
  }, []);

  useEffect(() => {
    const serverSetupReady = Boolean(
      setupStatus?.workspace_ready &&
      setupStatus.configured_default_model?.trim() &&
      (setupStatus.models_configured ?? 0) > 0,
    );

    if (serverSetupReady && setupStatus) {
      setShowWizard(false);
      const nextSetup = {
        completed: true,
        workspace_path: setupStatus.workspace_path ?? localSettings.setup.workspace_path,
        default_model: setupStatus.configured_default_model ?? localSettings.setup.default_model,
        sandbox_mode: setupStatus.configured_sandbox_mode ?? localSettings.setup.sandbox_mode,
      };
      if (
        !localSettings.setup.completed ||
        localSettings.setup.workspace_path !== nextSetup.workspace_path ||
        localSettings.setup.default_model !== nextSetup.default_model ||
        localSettings.setup.sandbox_mode !== nextSetup.sandbox_mode
      ) {
        setLocalSettings("setup", nextSetup);
      }
      return;
    }

    setShowWizard(!localSettings.setup.completed);
  }, [
    localSettings.setup.completed,
    localSettings.setup.default_model,
    localSettings.setup.sandbox_mode,
    localSettings.setup.workspace_path,
    setLocalSettings,
    setupStatus,
  ]);

  const handleWizardComplete = useCallback(() => {
    setShowWizard(false);
  }, []);

  // Build a short summary from the last few messages of the prior conversation.
  // Must be above the early return to satisfy the Rules of Hooks.
  const continuationSummary = useMemo(() => {
    if (!continuation) return null;
    const msgs = (continuation.recentMessages ?? []).slice(-4);
    if (msgs.length === 0) return null;
    return msgs
      .map((message) => {
        const marker = message.role === "human" ? "👤" : "🤖";
        const text = message.content.length > 120
          ? `${message.content.slice(0, 120)}…`
          : message.content;
        return `${marker}  ${text}`;
      })
      .join("\n");
  }, [continuation]);

  if (showWizard) {
    return <SetupWizard onComplete={handleWizardComplete} />;
  }

  const isSkillMode = searchParams.get("mode") === "skill";
  const isContinuation = Boolean(continuation);
  const description = normalizeWelcomeParagraph(
    isSkillMode
      ? t.welcome.createYourOwnSkillDescription
      : t.welcome.description,
  );

  return (
    <div
      className={cn(
        "mx-auto flex w-full max-w-5xl flex-col items-center justify-center gap-2 px-4 py-2 text-center md:px-6",
        className,
      )}
    >
      <div className="octo-panel relative w-full overflow-hidden rounded-[1.75rem] px-5 py-3 md:px-7 md:py-4">
        <div className="octo-grid pointer-events-none absolute inset-0 opacity-70" />
        <div className="relative flex flex-col items-center gap-3 text-center">
          {isContinuation ? (
            /* ───── Continuation summary ───── */
            <>
              <div className="flex items-center gap-2">
                <BrandMark className="size-6" priority size={24} />
                <Badge className="rounded-full border-0 bg-primary/12 px-2.5 py-1 text-[10px] font-medium text-primary shadow-none">
                  {t.common.continueTask ?? "Continue"}
                </Badge>
              </div>
              <p className="text-muted-foreground text-xs md:text-sm">
                {continuation?.sourceTitle
                  ? copy.welcome.continuationFromSource(
                    continuation.sourceTitle,
                    continuation?.messageCount ?? 0,
                  )
                  : copy.welcome.continuationFromPrior}
              </p>
              <code className="rounded-sm border bg-background px-2 py-1 font-mono text-[11px] text-foreground">
                {SYSTEM_SESSION_CONTINUE_PROMPT}
              </code>
              {continuationSummary && (
                <pre className="text-muted-foreground/80 w-full max-w-xl overflow-hidden text-left font-sans text-[11px] leading-5 whitespace-pre-wrap">
                  {continuationSummary}
                </pre>
              )}
            </>
          ) : (
            /* ───── Normal welcome ───── */
            <>
              <div className="flex flex-col items-center gap-3">
                <WelcomeArtwork priority />
                <div className="flex items-center gap-2">
                  <BrandMark className="size-8" priority size={32} />
                  <Badge className="rounded-full border-0 bg-primary/12 px-2.5 py-1 text-[10px] font-medium text-primary shadow-none">
                    {copy.welcome.workspaceBadge}
                  </Badge>
                </div>
              </div>
              <div className="min-w-0 space-y-2">
                <div className="text-xl font-semibold tracking-normal md:text-[1.8rem]">
                  {isSkillMode ? (
                    <span className="golden-text">{t.welcome.createYourOwnSkill}</span>
                  ) : (
                    <div className="flex flex-wrap items-center justify-center gap-2">
                      <span className={cn("inline-flex text-base", !hasWaved ? "animate-wave" : "")}>👋</span>
                      <AuroraText colors={colors}>{t.welcome.greeting}</AuroraText>
                    </div>
                  )}
                </div>
                <div className="text-muted-foreground mx-auto max-w-xl text-xs leading-5 md:text-sm">
                  <p className="text-left indent-8">{description}</p>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
