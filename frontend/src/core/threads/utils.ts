import type { Message } from "@langchain/langgraph-sdk";

import type { AgentThread } from "./types";

const HTML_ENTITY_MAP: Record<string, string> = {
  "&nbsp;": " ",
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#39;": "'",
};

export function sanitizePlainText(value: string) {
  return value
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&(nbsp|amp|lt|gt|quot|#39);/g, (entity) => HTML_ENTITY_MAP[entity] ?? " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function pathOfThread(threadId: string) {
  return `/workspace/chats/${threadId}`;
}

export function pathToContinueThread(threadId: string) {
  return `/workspace/chats/new?continue_from=${encodeURIComponent(threadId)}`;
}

export function textOfMessage(message: Message) {
  if (typeof message.content === "string") {
    const text = sanitizePlainText(message.content);
    return text || null;
  } else if (Array.isArray(message.content)) {
    const textParts: string[] = [];
    for (const part of message.content) {
      if (part.type === "text" && typeof part.text === "string") {
        const text = sanitizePlainText(part.text);
        if (text) {
          textParts.push(text);
        }
      }
    }
    return textParts.length > 0 ? textParts.join("") : null;
  }
  return null;
}

export function titleOfThread(thread: AgentThread) {
  const persistedTitle = thread.values?.title
    ? sanitizePlainText(thread.values.title)
    : "";
  if (persistedTitle) {
    return persistedTitle;
  }
  const firstHuman = (thread.values?.messages ?? []).find((message) => message.type === "human");
  const fallback = firstHuman ? textOfMessage(firstHuman) : null;
  if (fallback?.trim()) {
    return fallback.trim().replace(/\s+/g, " ").slice(0, 48);
  }
  return "Untitled";
}
