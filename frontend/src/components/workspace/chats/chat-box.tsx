import { useEffect, useRef, useState } from "react";
import type { GroupImperativeHandle } from "react-resizable-panels";

import { ConversationEmptyState } from "@/components/ai-elements/conversation";
import { AgentAvatar } from "@/components/brand/octo-mark";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { getAPIClient } from "@/core/api";
import {
  buildThreadRuntimeTelemetry,
  useRuntimeCapabilities,
} from "@/core/runtime";
import { createWorkflowEvent, useWorkflows } from "@/core/workflows";
import { env } from "@/env";
import { cn } from "@/lib/utils";

import {
  ArtifactFileDetail,
  ArtifactFileList,
  useArtifacts,
} from "../artifacts";
import { useThread } from "../messages/context";
import { WorkflowInspector } from "../orchestrator";

const CLOSE_MODE = { chat: 100, artifacts: 0 };
const OPEN_MODE = { chat: 62, artifacts: 38 };

const ChatBox: React.FC<{
  children: React.ReactNode;
  isNewThread: boolean;
  mode: "flash" | "thinking" | "pro" | "ultra" | undefined;
  threadId: string;
}> = ({
  children,
  isNewThread,
  mode,
  threadId,
}) => {
  const { thread } = useThread();
  const threadIdRef = useRef(threadId);
  const layoutRef = useRef<GroupImperativeHandle>(null);
  const hydratedThreadRef = useRef<string | null>(null);
  const persistTimeoutRef = useRef<number | null>(null);
  const workflowSnapshotRef = useRef<string>("[]");
  const { appendEvent, events, hydrate, workflows } = useWorkflows();
  const { runtime } = useRuntimeCapabilities({ enabled: threadId !== "new" });

  const {
    setArtifacts,
    select: selectArtifact,
    deselect,
    selectedArtifact,
  } = useArtifacts();

  const [autoSelectFirstArtifact, setAutoSelectFirstArtifact] = useState(true);
  useEffect(() => {
    if (threadIdRef.current !== threadId) {
      threadIdRef.current = threadId;
      deselect();
    }

    // Update artifacts from the current thread
    setArtifacts(thread.values.artifacts ?? []);

    // DO NOT automatically deselect the artifact when switching threads, because the artifacts auto discovering is not work now.
    // if (
    //   selectedArtifact &&
    //   !thread.values.artifacts?.includes(selectedArtifact)
    // ) {
    //   deselect();
    // }

    if (
      env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" &&
      autoSelectFirstArtifact
    ) {
      if (thread?.values?.artifacts?.length > 0) {
        setAutoSelectFirstArtifact(false);
        selectArtifact(thread.values.artifacts[0]!);
      }
    }
  }, [
    threadId,
    autoSelectFirstArtifact,
    deselect,
    selectArtifact,
    selectedArtifact,
    setArtifacts,
    thread.values.artifacts,
  ]);

  useEffect(() => {
    if (hydratedThreadRef.current === threadId) {
      return;
    }
    if (
      !thread.values.workflows &&
      !thread.values.workflow_events &&
      workflows.length > 0
    ) {
      hydratedThreadRef.current = threadId;
      workflowSnapshotRef.current = JSON.stringify(workflows);
      return;
    }
    hydrate(thread.values.workflows ?? [], thread.values.workflow_events ?? []);
    hydratedThreadRef.current = threadId;
    workflowSnapshotRef.current = JSON.stringify(thread.values.workflows ?? []);
  }, [hydrate, thread.values.workflow_events, thread.values.workflows, threadId, workflows]);

  useEffect(() => {
    if (!threadId || threadId === "new" || isNewThread || thread.isLoading) {
      return;
    }

    const hasLocalWorkflowState = workflows.length > 0 || events.length > 0;
    const hasRemoteWorkflowState =
      (thread.values.workflows?.length ?? 0) > 0
      || (thread.values.workflow_events?.length ?? 0) > 0;

    // Fresh chats should not write a runtime-only snapshot before the thread
    // has any persisted workflow state. That early update produces LangGraph
    // conflicts while the first user run is still being prepared.
    if (!hasLocalWorkflowState && !hasRemoteWorkflowState && thread.values.runtime == null) {
      return;
    }

    const remoteWorkflows = JSON.stringify(thread.values.workflows ?? []);
    const localWorkflows = JSON.stringify(workflows);
    const remoteEvents = JSON.stringify(thread.values.workflow_events ?? []);
    const localEvents = JSON.stringify(events);
    const nextRuntimeTelemetry = buildThreadRuntimeTelemetry(thread.values, runtime);
    const remoteRuntime = JSON.stringify(thread.values.runtime ?? null);
    const localRuntime = JSON.stringify(nextRuntimeTelemetry);

    if (
      remoteWorkflows === localWorkflows &&
      remoteEvents === localEvents &&
      remoteRuntime === localRuntime
    ) {
      return;
    }

    if (persistTimeoutRef.current) {
      window.clearTimeout(persistTimeoutRef.current);
    }

    persistTimeoutRef.current = window.setTimeout(() => {
      getAPIClient()
        .threads.updateState(threadId, {
          values: {
            workflows,
            workflow_events: events,
            runtime: nextRuntimeTelemetry,
          },
        })
        .catch(() => {
          // Thread may have been deleted (server restart, etc.).
          // Silently ignore — the page-level guard will redirect.
        });
    }, 250);

    return () => {
      if (persistTimeoutRef.current) {
        window.clearTimeout(persistTimeoutRef.current);
      }
    };
  }, [
    events,
    runtime,
    thread.values,
    thread.values.runtime,
    thread.values.workflow_events,
    thread.values.workflows,
    thread.isLoading,
    isNewThread,
    threadId,
    workflows,
  ]);

  useEffect(() => {
    const snapshot = JSON.stringify(workflows);
    if (snapshot !== workflowSnapshotRef.current && workflows.length > 0) {
      workflowSnapshotRef.current = snapshot;
      appendEvent(
        createWorkflowEvent(
          "workflow_saved",
          "Workflow configuration updated",
          "Thread state synchronized with the current orchestration cards.",
          "info",
        ),
      );
    }
  }, [appendEvent, workflows]);

  const artifactPanelOpen = true;

  useEffect(() => {
    if (layoutRef.current) {
      if (artifactPanelOpen) {
        layoutRef.current.setLayout(OPEN_MODE);
      } else {
        layoutRef.current.setLayout(CLOSE_MODE);
      }
    }
  }, [artifactPanelOpen]);

  return (
    <ResizablePanelGroup
      id="workspace-chat-layout"
      orientation="horizontal"
      defaultLayout={{ chat: 100, artifacts: 0 }}
      groupRef={layoutRef}
    >
      <ResizablePanel className="relative" defaultSize={100} id="chat">
        {children}
      </ResizablePanel>
      <ResizableHandle
        withHandle
        className={cn(
          "mx-1 rounded-full opacity-70 transition-opacity hover:opacity-100",
          !artifactPanelOpen && "pointer-events-none opacity-0",
        )}
      />
      <ResizablePanel
        className={cn(
          "transition-all duration-300 ease-in-out",
          !artifactPanelOpen && "opacity-0",
        )}
        defaultSize={38}
        minSize={24}
        id="artifacts"
      >
        <div
          className={cn(
            "h-full p-4 transition-transform duration-300 ease-in-out",
            artifactPanelOpen ? "translate-x-0" : "translate-x-full",
          )}
        >
          {artifactPanelOpen ? (
            <WorkflowInspector
              isStreaming={thread.isLoading}
              mode={mode}
              threadId={threadId}
              threadState={thread.values}
            />
          ) : (
            <div className="relative flex size-full justify-center">
              {selectedArtifact ? (
                <ArtifactFileDetail
                  className="size-full"
                  filepath={selectedArtifact}
                  threadId={threadId}
                />
              ) : thread.values.artifacts?.length === 0 ? (
                <ConversationEmptyState
                  icon={<AgentAvatar size={28} />}
                  title="Inspector unavailable"
                  description="The orchestration panel could not be rendered."
                />
              ) : (
                <div className="flex size-full max-w-(--container-width-sm) flex-col justify-center p-4 pt-8">
                  <header className="shrink-0">
                    <h2 className="text-lg font-medium">Artifacts</h2>
                  </header>
                  <main className="min-h-0 grow">
                    <ArtifactFileList
                      className="max-w-(--container-width-sm) p-4 pt-12"
                      files={thread.values.artifacts ?? []}
                      threadId={threadId}
                    />
                  </main>
                </div>
              )}
            </div>
          )}
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  );
};

export { ChatBox };
