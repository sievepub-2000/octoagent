import { redirect } from "next/navigation";

import { buildNewChatPath, type NewChatSearchParams } from "@/core/threads/new-chat-route";

export default async function NewChatPage({
  searchParams,
}: {
  searchParams?: Promise<NewChatSearchParams>;
}) {
  return redirect(buildNewChatPath(await searchParams));
}