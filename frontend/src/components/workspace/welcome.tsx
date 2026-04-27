"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { BrandMark, WelcomeArtwork } from "@/components/brand/octo-mark";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/core/i18n/hooks";
import { getWorkspaceLocaleCopy } from "@/core/i18n/workspace-copy";
import { useLocalSettings } from "@/core/settings";
import { cn } from "@/lib/utils";

import { AuroraText } from "../ui/aurora-text";

import { SetupWizard } from "./setup-wizard";

export interface ContinuationInfo {
  sourceTitle?: string | null;
  messageCount?: number;
  recentMessages?: Array<{ role: string; content: string }>;
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
  const [localSettings] = useLocalSettings();
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
    setShowWizard(!localSettings.setup.completed);
  }, [localSettings.setup.completed]);

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

  return (
    <div
      className={cn(
        "mx-auto flex w-full flex-col items-center justify-center gap-2 px-4 py-2 text-center md:px-6",
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
                <div className="text-xl font-semibold tracking-[-0.05em] md:text-[1.8rem]">
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
                  {isSkillMode ? (
                    t.welcome.createYourOwnSkillDescription.includes("\n") ? (
                      <pre className="font-sans whitespace-pre-wrap">
                        {t.welcome.createYourOwnSkillDescription}
                      </pre>
                    ) : (
                      <p>{t.welcome.createYourOwnSkillDescription}</p>
                    )
                  ) : t.welcome.description.includes("\n") ? (
                    <pre className="font-sans whitespace-pre-wrap">{t.welcome.description}</pre>
                  ) : (
                    <p>{t.welcome.description}</p>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
