import { uuid } from "@/core/utils/uuid";

export type NewChatSearchParams = Record<string, string | string[] | undefined>;

export function buildNewChatPath(searchParams: NewChatSearchParams = {}) {
  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(searchParams)) {
    if (typeof value === "string") {
      params.append(key, value);
      continue;
    }

    for (const item of value ?? []) {
      params.append(key, item);
    }
  }

  params.set("fresh", "1");
  if (!params.has("draft")) {
    params.set("draft", String(Date.now()));
  }

  return `/workspace/chats/${uuid()}?${params.toString()}`;
}