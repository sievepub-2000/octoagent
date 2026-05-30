"use client";

import { FilesIcon, PanelRightCloseIcon, RouteIcon } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";

import { ConversationEmptyState } from "@/components/ai-elements/conversation";
import { BrandMark } from "@/components/brand/octo-mark";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useArtifacts } from "@/components/workspace/artifacts";
import { Tooltip } from "@/components/workspace/tooltip";
import { useI18n } from "@/core/i18n/hooks";
import {
  buildRuntimeSummaryItems,
  buildRuntimeTelemetryEvents,
  mergeRunEvents,
  normalizeRunEvents,
  normalizeWorkflowRunEvents,
  type RunEvent,
  type RuntimeCapabilities,
} from "@/core/runtime";
import { useRuntimeCapabilities } from "@/core/runtime";
import type { AgentThreadState } from "@/core/threads";
import { useWorkflows } from "@/core/workflows";
import { cn } from "@/lib/utils";

import { ArtifactFileList } from "../artifacts/artifact-file-list";
import { RunTimelinePanel } from "../run-timeline-panel";

import { ExecutionConsole } from "./execution-console";
import { TaskWorkspaceRuntime } from "./task-workspace-runtime";
import { WorkBusFlow } from "./work-bus-flow";

export function WorkflowInspector({
  className,
  currentModelName,
  isStreaming,
  mode,
  onCollapsePanel,
  runEvents = [],
  runtimeCapabilities,
  threadId,
  threadState,
}: {
  className?: string;
  currentModelName?: string;
  isStreaming: boolean;
  mode: "flash" | "thinking" | "pro" | "ultra" | undefined;
  onCollapsePanel?: () => void;
  runEvents?: RunEvent[];
  runtimeCapabilities?: RuntimeCapabilities;
  threadId: string;
  threadState: AgentThreadState;
}) {
  const { t } = useI18n();
  const copy = t.workspace.inspector;
  const { selectedArtifact, artifacts } = useArtifacts();
  const { topTab, setTopTab, consoleOpen, setConsoleOpen, appendEvent, events } =
    useWorkflows();
  const { runtime: fetchedRuntime } = useRuntimeCapabilities({
    enabled: runtimeCapabilities == null,
  });
  const runtime = runtimeCapabilities ?? fetchedRuntime;
  const telemetryEventKeysRef = useRef<Set<string>>(new Set());

  const runtimeSummaryItems = useMemo(
    () => buildRuntimeSummaryItems(threadState, runtime, copy, currentModelName),
    [copy, currentModelName, runtime, threadState],
  );

  const telemetryEvents = useMemo(
    () => buildRuntimeTelemetryEvents(threadState, runtime, copy),
    [copy, runtime, threadState],
  );
  const timelineEvents = useMemo(
    () =>
      mergeRunEvents(
        runEvents,
        [
          ...normalizeRunEvents(threadState.runtime?.run_events),
          ...normalizeWorkflowRunEvents(threadState.workflow_events),
        ],
        120,
      ),
    [runEvents, threadState.runtime?.run_events, threadState.workflow_events],
  );
  useEffect(() => {
    if (topTab === "graph") {
      setTopTab("plan");
      return;
    }
    if (selectedArtifact || artifacts.length > 0) {
      setTopTab("artifacts");
    }
  }, [artifacts.length, selectedArtifact, setTopTab, topTab]);

  useEffect(() => {
    if (mode !== "flash" || isStreaming) {
      setConsoleOpen(true);
    }
  }, [isStreaming, mode, setConsoleOpen]);

  useEffect(() => {
    telemetryEventKeysRef.current.clear();
  }, [threadId]);

  useEffect(() => {
    for (const event of telemetryEvents) {
      const key = `${event.kind}:${event.title}:${event.detail ?? ""}`;
      const alreadyPresent = events.some(
        (existing) =>
          existing.kind === event.kind &&
          existing.title === event.title &&
          (existing.detail ?? "") === (event.detail ?? ""),
      );
      if (alreadyPresent || telemetryEventKeysRef.current.has(key)) {
        continue;
      }
      telemetryEventKeysRef.current.add(key);
      appendEvent(event);
    }
  }, [appendEvent, events, telemetryEvents]);

  return (
    <ResizablePanelGroup
      id="workflow-inspector-layout"
      className={cn("h-full min-h-0", className)}
      orientation="vertical"
    >
      <ResizablePanel defaultSize={consoleOpen ? 62 : 100} minSize={45}>
        <div className="octo-panel flex h-full min-h-0 flex-col overflow-hidden rounded-[1.75rem]">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              {onCollapsePanel ? (
                <div className="flex shrink-0 items-center gap-1">
                  <Tooltip content="Collapse right sidebar">
                    <Button
                      aria-label="Collapse right sidebar"
                      className="size-6 rounded-[0.7rem] p-0"
                      onClick={onCollapsePanel}
                      size="icon-sm"
                      type="button"
                      variant="ghost"
                    >
                      <PanelRightCloseIcon className="size-3.5" />
                    </Button>
                  </Tooltip>
                  <BrandMark priority size={38} />
                </div>
              ) : (
                <BrandMark priority size={38} />
              )}
              {copy.title}
            </div>
            <Button size="sm" variant="ghost" onClick={() => setTopTab("plan")}>
              {copy.resetView}
            </Button>
          </div>
          <Tabs
            className="flex min-h-0 flex-1 flex-col"
            onValueChange={(value) => setTopTab(value as typeof topTab)}
            value={topTab}
          >
            <div className="grid grid-cols-2 gap-2 border-b px-3 py-3">
              {runtimeSummaryItems.map((item) => (
                <div
                  className="rounded-lg border bg-muted/25 px-3 py-2"
                  key={item.id}
                >
                  <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    {item.label}
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium">
                      {item.value}
                    </span>
                    <Badge
                      variant={
                        item.tone === "warning"
                          ? "destructive"
                          : item.tone === "success"
                            ? "default"
                            : "secondary"
                      }
                    >
                      {item.tone === "warning"
                        ? copy.attention
                        : item.tone === "success"
                          ? copy.active
                          : copy.info}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
            <TabsList
              className="w-full justify-start rounded-none border-b bg-transparent px-3 py-2"
              variant="line"
            >
              <TabsTrigger value="plan">{copy.board}</TabsTrigger>
              <TabsTrigger value="artifacts">{t.common.artifacts}</TabsTrigger>
            </TabsList>
            <TabsContent className="min-h-0 flex-1 overflow-auto p-4" value="plan">
              <RunTimelinePanel
                className="mb-4"
                events={timelineEvents}
                isLoading={isStreaming}
                workplans={threadState.runtime?.workplans ?? []}
              />
              <WorkBusFlow threadId={threadId} />
              <TaskWorkspaceRuntime
                focus="plan"
                threadId={threadId}
                threadState={threadState}
              />
            </TabsContent>
            <TabsContent className="min-h-0 flex-1 p-4" value="artifacts">
              {threadState.artifacts?.length ? (
                <ArtifactFileList
                  downloadOnly
                  files={threadState.artifacts}
                  threadId={threadId}
                />
              ) : (
                <ConversationEmptyState
                  icon={<FilesIcon />}
                  title={copy.noArtifactsYet}
                  description={copy.noArtifactsDescription}
                />
              )}
            </TabsContent>
          </Tabs>
        </div>
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel
        className={cn(!consoleOpen && "opacity-70")}
        defaultSize={38}
        minSize={20}
      >
        <div className="octo-panel flex h-full min-h-0 flex-col overflow-hidden rounded-[1.75rem]">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <RouteIcon className="size-4" />
              {copy.executionConsole}
            </div>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setConsoleOpen(!consoleOpen)}
            >
              {consoleOpen ? copy.collapse : copy.expand}
            </Button>
          </div>
          <div className="min-h-0 flex-1 p-4">
            <ExecutionConsole isStreaming={isStreaming} mode={mode} />
          </div>
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
