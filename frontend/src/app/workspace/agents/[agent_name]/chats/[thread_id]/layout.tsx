"use client";

import { PromptInputProvider } from "@/components/ai-elements/prompt-input";
import { ArtifactsProvider } from "@/components/workspace/artifacts";
import { SubtasksProvider } from "@/core/tasks/context";
import { WorkflowsProvider } from "@/core/workflows";

export default function AgentChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SubtasksProvider>
      <WorkflowsProvider>
        <ArtifactsProvider>
          <PromptInputProvider>{children}</PromptInputProvider>
        </ArtifactsProvider>
      </WorkflowsProvider>
    </SubtasksProvider>
  );
}
