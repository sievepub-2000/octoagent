import { redirect } from "next/navigation";

import { buildNewChatPath } from "@/core/threads/new-chat-route";

export default function WorkspacePage() {
  return redirect(buildNewChatPath());
}
