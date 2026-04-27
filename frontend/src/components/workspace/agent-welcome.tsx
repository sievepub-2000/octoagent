"use client";

import { AgentAvatar } from "@/components/brand/octo-mark";
import { type Agent } from "@/core/agents";
import { agentAvatarUrl } from "@/core/agents/api";
import { useI18n } from "@/core/i18n/hooks";
import { getWorkspaceLocaleCopy } from "@/core/i18n/workspace-copy";
import { cn } from "@/lib/utils";

function buildSoulPreview(soul: string | null | undefined) {
  if (!soul) {
    return null;
  }
  const normalized = soul.replace(/\s+/g, " ").trim();
  if (normalized.length === 0) {
    return null;
  }
  return normalized.length > 220 ? `${normalized.slice(0, 220)}...` : normalized;
}

export function AgentWelcome({
  className,
  agent,
  agentName,
}: {
  className?: string;
  agent: Agent | null | undefined;
  agentName: string;
}) {
  const { locale } = useI18n();
  const copy = getWorkspaceLocaleCopy(locale);
  const displayName = agent?.name ?? agentName;
  const description = agent?.description;
  const soulPreview = buildSoulPreview(agent?.soul);
  const avatarUrl = agent?.avatar ? agentAvatarUrl(displayName) : null;

  return (
    <div
      className={cn(
        "octo-panel mx-auto flex w-full max-w-xl flex-col items-center justify-center gap-3 rounded-[1.5rem] px-6 py-5 text-center",
        className,
      )}
    >
      <AgentAvatar avatarUrl={avatarUrl} priority size={46} />
      <div className="text-xl font-semibold tracking-[-0.04em]">{displayName}</div>
      {description && (
        <p className="text-muted-foreground max-w-md break-words text-sm leading-5">{description}</p>
      )}
      {soulPreview && (
        <div className="w-full max-w-lg rounded-xl border border-border/60 bg-background/50 px-4 py-3 text-left">
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {copy.agentWelcome.identityPrompt}
          </div>
          <div className="mt-2 text-sm leading-6 text-foreground/90">{soulPreview}</div>
        </div>
      )}
    </div>
  );
}
