import type { BaseStream } from "@langchain/langgraph-sdk";
import { useEffect } from "react";

import { useI18n } from "@/core/i18n/hooks";
import type { AgentThreadState } from "@/core/threads";
import { sanitizePlainText } from "@/core/threads/utils";

import { FlipDisplay } from "./flip-display";

export function ThreadTitle({
  isNewThread,
  threadId,
  thread,
}: {
  className?: string;
  isNewThread: boolean;
  threadId: string;
  thread: BaseStream<AgentThreadState>;
}) {
  const { t } = useI18n();
  useEffect(() => {
    let _title = t.pages.untitled;

    if (thread.values?.title) {
      _title = sanitizePlainText(thread.values.title) ?? t.pages.untitled;
    } else if (isNewThread) {
      _title = t.pages.newChat;
    }
    if (thread.isThreadLoading) {
      document.title = `Loading... - ${t.pages.appName}`;
    } else {
      document.title = `${_title} - ${t.pages.appName}`;
    }
  }, [
    isNewThread,
    t.pages.newChat,
    t.pages.untitled,
    t.pages.appName,
    thread.isThreadLoading,
    thread.values,
  ]);

  if (!thread.values?.title) {
    return null;
  }
  const safeTitle = sanitizePlainText(thread.values.title) ?? "Untitled";
  return (
    <FlipDisplay uniqueKey={threadId}>
      {safeTitle}
    </FlipDisplay>
  );
}
