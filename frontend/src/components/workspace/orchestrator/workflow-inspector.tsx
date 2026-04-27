"use client";

import { FilesIcon, RouteIcon } from "lucide-react";
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
import { useI18n } from "@/core/i18n/hooks";
import {
  buildRuntimeSummaryItems,
  buildRuntimeTelemetryEvents,
} from "@/core/runtime";
import { useRuntimeCapabilities } from "@/core/runtime";
import type { AgentThreadState } from "@/core/threads";
import { useWorkflows } from "@/core/workflows";
import { cn } from "@/lib/utils";

import { ArtifactFileDetail } from "../artifacts/artifact-file-detail";
import { ArtifactFileList } from "../artifacts/artifact-file-list";

import { ExecutionConsole } from "./execution-console";
import { TaskWorkspaceRuntime } from "./task-workspace-runtime";

export function WorkflowInspector({
  className,
  isStreaming,
  mode,
  threadId,
  threadState,
}: {
  className?: string;
  isStreaming: boolean;
  mode: "flash" | "thinking" | "pro" | "ultra" | undefined;
  threadId: string;
  threadState: AgentThreadState;
}) {
  const { t } = useI18n();
  const copy = t.workspace.inspector;
  const { selectedArtifact, artifacts } = useArtifacts();
  const { topTab, setTopTab, consoleOpen, setConsoleOpen, appendEvent, events } =
    useWorkflows();
  const { runtime } = useRuntimeCapabilities();
  const telemetryEventKeysRef = useRef<Set<string>>(new Set());

  const runtimeSummaryItems = useMemo(
    () => buildRuntimeSummaryItems(threadState, runtime, copy),
    [copy, runtime, threadState],
  );

  const telemetryEvents = useMemo(
    () => buildRuntimeTelemetryEvents(threadState, runtime, copy),
    [copy, runtime, threadState],
  );

  useEffect(() => {
    if (selectedArtifact || artifacts.length > 0) {
      setTopTab("artifacts");
    }
  }, [artifacts.length, selectedArtifact, setTopTab]);

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
              <BrandMark size={24} />
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
              <TabsTrigger value="graph">{copy.canvas}</TabsTrigger>
              <TabsTrigger value="artifacts">{t.common.artifacts}</TabsTrigger>
            </TabsList>
            <TabsContent className="min-h-0 flex-1 p-4" value="plan">
              <TaskWorkspaceRuntime
                focus="plan"
                threadId={threadId}
                threadState={threadState}
              />
            </TabsContent>
            <TabsContent className="min-h-0 flex-1 p-4" value="graph">
              <TaskWorkspaceRuntime
                focus="graph"
                threadId={threadId}
                threadState={threadState}
              />
            </TabsContent>
            <TabsContent className="min-h-0 flex-1 p-4" value="artifacts">
              {selectedArtifact ? (
                <ArtifactFileDetail
                  className="size-full"
                  filepath={selectedArtifact}
                  threadId={threadId}
                />
              ) : threadState.artifacts?.length ? (
                <ArtifactFileList
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
