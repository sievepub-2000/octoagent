import { redirect } from "next/navigation";

import { buildNewChatPath } from "@/core/threads/new-chat-route";

export default function LandingPage() {
  return redirect(buildNewChatPath());
}
