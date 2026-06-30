import { PanelRightOpenIcon } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GroupImperativeHandle } from "react-resizable-panels";

import { Button } from "@/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Tooltip } from "@/components/workspace/tooltip";
import { getAPIClient } from "@/core/api";
import {
  buildThreadRuntimeTelemetry,
  type RunEvent,
  useRuntimeCapabilities,
} from "@/core/runtime";
import type { AgentThreadState } from "@/core/threads";
import { createWorkflowEvent, useWorkflows } from "@/core/workflows";
import { env } from "@/env";
import { useIsMobile } from "@/hooks/use-mobile";
import { cn } from "@/lib/utils";

import {
  useArtifacts,
} from "../artifacts";
import { useThread } from "../messages/context";

const WorkflowInspector = dynamic(
  () => import("../orchestrator/workflow-inspector").then((module) => module.WorkflowInspector),
  {
    ssr: false,
    loading: () => <InspectorFallback />,
  },
);

const CLOSE_MODE = { chat: 100, artifacts: 0 };
const OPEN_MODE = { chat: 62, artifacts: 38 };
const OPEN_MODE_MOBILE = { chat: 54, artifacts: 46 };

function InspectorFallback() {
  return (
    <div className="octo-panel flex size-full min-h-[16rem] items-center justify-center rounded-[1.75rem] px-4 text-center text-sm text-muted-foreground" aria-busy="true" aria-live="polite">
      Loading runtime inspector...
    </div>
  );
}

const ChatBox: React.FC<{
  children: React.ReactNode;
  isNewThread: boolean;
  mode: "flash" | "thinking" | "pro" | "ultra" | undefined;
  runEvents?: RunEvent[];
  threadId: string;
  contextModelName?: string;
}> = ({
  children,
  contextModelName,
  isNewThread,
  mode,
  runEvents = [],
  threadId,
}) => {
  const { thread } = useThread();
  const threadValues = thread.values;
  const threadIdRef = useRef(threadId);
  const layoutRef = useRef<GroupImperativeHandle>(null);
  const hydratedThreadRef = useRef<string | null>(null);
  const persistTimeoutRef = useRef<number | null>(null);
  const workflowSnapshotRef = useRef<string>("[]");
  const { appendEvent, events, hydrate, workflows } = useWorkflows();
  const [artifactPanelOpen, setArtifactPanelOpen] = useState(false);
  const [inspectorReady, setInspectorReady] = useState(false);
  const { runtime } = useRuntimeCapabilities({
    enabled: threadId !== "new" && artifactPanelOpen && inspectorReady,
  });
  const isMobile = useIsMobile();

  const {
    setArtifacts,
    select: selectArtifact,
    deselect,
    selectedArtifact,
  } = useArtifacts();

  const [autoSelectFirstArtifact, setAutoSelectFirstArtifact] = useState(true);
  const threadArtifacts = useMemo(
    () => threadValues.artifacts ?? [],
    [threadValues.artifacts],
  );
  const inspectorMessages = useMemo(
    () => (threadValues.messages ?? []).slice(-40),
    [threadValues.messages],
  );
  const inspectorThreadState = useMemo<AgentThreadState>(
    () => ({
      title: threadValues.title ?? "",
      messages: inspectorMessages,
      artifacts: threadArtifacts,
      continuation: threadValues.continuation,
      runtime: threadValues.runtime,
      todos: threadValues.todos,
      workflows: threadValues.workflows,
      workflow_events: threadValues.workflow_events,
      task_workspace_ids: threadValues.task_workspace_ids,
      active_task_workspace_id: threadValues.active_task_workspace_id,
    }),
    [
      inspectorMessages,
      threadArtifacts,
      threadValues.active_task_workspace_id,
      threadValues.continuation,
      threadValues.runtime,
      threadValues.task_workspace_ids,
      threadValues.title,
      threadValues.todos,
      threadValues.workflow_events,
      threadValues.workflows,
    ],
  );

  useEffect(() => {
    if (threadIdRef.current !== threadId) {
      threadIdRef.current = threadId;
      deselect();
    }

    // Update artifacts from the current thread
    setArtifacts(threadArtifacts);

    // Fallback: scan messages for present_files tool calls if artifacts are missing
    if (threadArtifacts.length === 0 && threadValues.messages?.length > 0) {
      const messageArtifacts: string[] = [];
      for (const msg of threadValues.messages) {
        if (msg.type === "ai" && msg.tool_calls) {
          for (const tc of msg.tool_calls) {
            if (tc.name === "present_files" && tc.args?.files) {
              const files = Array.isArray(tc.args.files) ? tc.args.files : [tc.args.files];
              messageArtifacts.push(...files.filter(Boolean));
            }
          }
        }
      }
      if (messageArtifacts.length > 0) {
        setArtifacts(messageArtifacts);
      }
    }

    // Auto-deselect artifact when switching to a thread without it
    if (selectedArtifact && !threadArtifacts.includes(selectedArtifact)) {
      deselect();
    }
    // Also close artifact panel entirely if new thread has no artifacts
    if (threadArtifacts.length === 0 && selectedArtifact) {
      deselect();
    }

    if (
      env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" &&
      autoSelectFirstArtifact
    ) {
      if (threadArtifacts.length > 0) {
        setAutoSelectFirstArtifact(false);
        selectArtifact(threadArtifacts[0]!);
      }
    }
  }, [
    threadId,
    autoSelectFirstArtifact,
    deselect,
    selectArtifact,
    selectedArtifact,
    setArtifacts,
    threadArtifacts,
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
      (threadValues.workflows?.length ?? 0) > 0
      || (threadValues.workflow_events?.length ?? 0) > 0;

    // Fresh chats should not write a runtime-only snapshot before the thread
    // has any persisted workflow state. That early update produces LangGraph
    // conflicts while the first user run is still being prepared.
    if (!hasLocalWorkflowState && !hasRemoteWorkflowState && threadValues.runtime == null) {
      return;
    }

    const remoteWorkflows = JSON.stringify(threadValues.workflows ?? []);
    const localWorkflows = JSON.stringify(workflows);
    const remoteEvents = JSON.stringify(threadValues.workflow_events ?? []);
    const localEvents = JSON.stringify(events);
    const nextRuntimeTelemetry = buildThreadRuntimeTelemetry(threadValues, runtime, undefined, contextModelName);
    const remoteRuntime = JSON.stringify(threadValues.runtime ?? null);
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
    contextModelName,
    runtime,
    threadValues,
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

  const toggleArtifactPanel = useCallback(() => {
    setArtifactPanelOpen((open) => !open);
  }, []);

  useEffect(() => {
    if (threadArtifacts.length > 0 || workflows.length > 0 || events.length > 0) {
      setArtifactPanelOpen(true);
    }
  }, [events.length, threadArtifacts.length, workflows.length]);

  useEffect(() => {
    if (layoutRef.current) {
      if (artifactPanelOpen) {
        layoutRef.current.setLayout(isMobile ? OPEN_MODE_MOBILE : OPEN_MODE);
      } else {
        layoutRef.current.setLayout(CLOSE_MODE);
      }
    }
  }, [artifactPanelOpen, isMobile]);

  useEffect(() => {
    setInspectorReady(false);
    const scheduleIdle = window.requestIdleCallback
      ?? ((callback: IdleRequestCallback) => window.setTimeout(
        () => callback({ didTimeout: false, timeRemaining: () => 0 }),
        1,
      ));
    const cancelIdle = window.cancelIdleCallback ?? window.clearTimeout;
    let idleId: number | null = null;
    if (!artifactPanelOpen) {
      return undefined;
    }
    const delayId = window.setTimeout(() => {
      idleId = scheduleIdle(() => setInspectorReady(true), { timeout: 1_800 });
    }, 900);
    return () => {
      window.clearTimeout(delayId);
      if (idleId != null) {
        cancelIdle(idleId);
      }
    };
  }, [artifactPanelOpen, threadId]);

  return (
    <div className="relative size-full min-h-0">
      {!artifactPanelOpen && (
        <Tooltip content="Expand right sidebar">
          <Button
            aria-label="Expand right sidebar"
            className="absolute right-3 top-3 z-50 hidden shadow-[0_12px_28px_rgba(0,0,0,0.12)] lg:inline-flex"
            onClick={toggleArtifactPanel}
            size="icon-sm"
            type="button"
            variant="ghost"
          >
            <PanelRightOpenIcon className="size-4" />
          </Button>
        </Tooltip>
      )}
      <ResizablePanelGroup
        id="workspace-chat-layout"
        orientation={isMobile ? "vertical" : "horizontal"}
        defaultLayout={{ chat: 100, artifacts: 0 }}
        groupRef={layoutRef}
      >
        <ResizablePanel className="relative" defaultSize={100} id="chat" minSize={isMobile ? 0 : undefined}>
          {children}
        </ResizablePanel>
        <ResizableHandle
          withHandle
          className={cn(
            "rounded-full opacity-70 transition-opacity hover:opacity-100",
            isMobile ? "my-1" : "mx-1",
            !artifactPanelOpen && "pointer-events-none opacity-0",
          )}
        />
        <ResizablePanel
          className={cn(
            "transition-all duration-300 ease-in-out",
            !artifactPanelOpen && "pointer-events-none opacity-0",
          )}
          collapsible
          collapsedSize={0}
          defaultSize={isMobile ? 72 : 38}
          minSize={artifactPanelOpen ? (isMobile ? 60 : 24) : 0}
          id="artifacts"
        >
          <div
            className={cn(
              "h-full transition-transform duration-300 ease-in-out",
              isMobile ? "px-3 pb-3 pt-1" : "p-4",
              artifactPanelOpen ? "translate-x-0 translate-y-0" : isMobile ? "translate-y-full" : "translate-x-full",
            )}
          >
            {artifactPanelOpen && inspectorReady ? (
              <WorkflowInspector
                currentModelName={contextModelName}
                isStreaming={thread.isLoading}
                mode={mode}
                onCollapsePanel={toggleArtifactPanel}
                runEvents={runEvents}
                runtimeCapabilities={runtime}
                threadId={threadId}
                threadState={inspectorThreadState}
              />
            ) : <InspectorFallback />}
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
};

export { ChatBox };
