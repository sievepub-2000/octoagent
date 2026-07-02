import type { Message } from "@langchain/langgraph-sdk";

import type { AgentThreadState } from "@/core/threads";
import { textOfMessage } from "@/core/threads/utils";

export const CONTEXT_AUTO_COMPACT_THRESHOLD = 0.9;

export type ContextTokenUsage = {
  usedTokens: number;
  rawUsedTokens: number;
  cycleBaseTokens: number;
  maxTokens: number | null;
  thresholdTokens: number | null;
  ratio: number;
  percent: number;
  thresholdRatio: number;
  hasContextWindow: boolean;
  shouldAutoCompact: boolean;
};

function estimateTextTokens(text: string): number {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return 0;
  }

  const cjkChars = normalized.match(/[\u3400-\u9fff\uf900-\ufaff]/g)?.length ?? 0;
  const nonCjkText = normalized.replace(/[\u3400-\u9fff\uf900-\ufaff]/g, " ");
  const latinTokens = Math.ceil(nonCjkText.length / 4);
  return Math.max(1, cjkChars + latinTokens);
}

function estimateMessageTokens(message: Message): number {
  const text = textOfMessage(message);
  if (!text) {
    return 8;
  }
  return 8 + estimateTextTokens(text);
}

export function estimateContextTokens(state: AgentThreadState | undefined, draftText: string): number {
  const messages = state?.messages ?? [];
  const messageTokens = messages.reduce((total, message) => total + estimateMessageTokens(message), 0);
  const todoTokens = estimateTextTokens((state?.todos ?? []).map((todo) => `${todo.content ?? ""} ${todo.status}`).join(""));
  const workflowTokens = estimateTextTokens((state?.workflows ?? []).map((workflow) => `${workflow.title ?? ""} ${workflow.goal ?? ""}`).join(""));
  const draftTokens = estimateTextTokens(draftText);
  return messageTokens + todoTokens + workflowTokens + draftTokens;
}

export function computeContextTokenUsage({
  state,
  draftText,
  maxTokens,
  cycleBaseTokens = 0,
  thresholdRatio = CONTEXT_AUTO_COMPACT_THRESHOLD,
}: {
  state?: AgentThreadState;
  draftText: string;
  maxTokens?: number | null;
  cycleBaseTokens?: number;
  thresholdRatio?: number;
}): ContextTokenUsage {
  const resolvedMaxTokens = typeof maxTokens === "number" && Number.isFinite(maxTokens) && maxTokens > 0
    ? Math.floor(maxTokens)
    : null;
  const thresholdTokens = resolvedMaxTokens === null ? null : Math.floor(resolvedMaxTokens * thresholdRatio);
  const rawUsedTokens = estimateContextTokens(state, draftText);
  const resolvedCycleBaseTokens = Math.max(0, Math.min(cycleBaseTokens, rawUsedTokens));
  const usedTokens = Math.max(0, rawUsedTokens - resolvedCycleBaseTokens);
  const ratio = resolvedMaxTokens === null ? 0 : Math.min(1, usedTokens / resolvedMaxTokens);
  return {
    usedTokens,
    rawUsedTokens,
    cycleBaseTokens: resolvedCycleBaseTokens,
    maxTokens: resolvedMaxTokens,
    thresholdTokens,
    ratio,
    percent: Math.round(ratio * 100),
    thresholdRatio,
    hasContextWindow: resolvedMaxTokens !== null,
    shouldAutoCompact: resolvedMaxTokens !== null && ratio >= thresholdRatio,
  };
}