"use client";

import {
  ActivityIcon,
  Clock3Icon,
  FileTextIcon,
  TerminalIcon,
  XIcon,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { ConversationEmptyState } from "@/components/ai-elements/conversation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/core/i18n/hooks";
import {
  useSystemExecutionSession,
  useSystemExecutionSessions,
} from "@/core/system-execution/hooks";
import { cn } from "@/lib/utils";

import {
  ArtifactFileDetail,
  ArtifactFileList,
  useArtifacts,
} from "../artifacts";
import { useThread } from "../messages/context";

const ChatBox = ({
  children,
  threadId,
}: {
  children: ReactNode;
  threadId: string;
}) => {
  const { t } = useI18n();
  const { thread } = useThread();
  const {
    artifacts,
    deselect,
    open,
    select,
    selectedArtifact,
    setArtifacts,
    setOpen,
  } = useArtifacts();
  const [activePanel, setActivePanel] = useState<"terminal" | "documents">(
    "terminal",
  );
  const previousThreadIdRef = useRef(threadId);

  useEffect(() => {
    if (previousThreadIdRef.current !== threadId) {
      previousThreadIdRef.current = threadId;
      deselect();
    }
    setArtifacts(thread.values.artifacts ?? []);
  }, [deselect, setArtifacts, thread.values.artifacts, threadId]);

  useEffect(() => {
    if (open || selectedArtifact) {
      setActivePanel("documents");
    }
  }, [open, selectedArtifact]);

  return (
    <div className="relative flex size-full min-h-0 overflow-hidden">
      <div className="min-w-0 flex-1">{children}</div>
      <aside
        data-testid="chat-side-panel"
        className={cn(
          "absolute inset-y-0 right-0 z-40 flex w-[min(92vw,430px)] translate-x-full flex-col border-l bg-background/96 opacity-0 shadow-[-18px_0_40px_var(--emboss-shadow)] backdrop-blur-xl transition duration-200",
          "xl:relative xl:z-auto xl:w-[410px] xl:translate-x-0 xl:opacity-100 2xl:w-[450px]",
          open && "translate-x-0 opacity-100",
        )}
        aria-label={t.common.artifacts}
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b px-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <ActivityIcon className="size-4" />
              {t.workspace.inspector.executionConsole}
            </div>
            <div className="text-muted-foreground truncate text-xs">
              {t.workspace.inspector.terminalDescription}
            </div>
          </div>
          <Button
            aria-label={t.common.close}
            className="xl:hidden"
            data-testid="chat-side-panel-close"
            size="icon"
            variant="ghost"
            onClick={() => setOpen(false)}
          >
            <XIcon className="size-4" />
          </Button>
        </div>

        <Tabs
          className="flex min-h-0 flex-1 flex-col"
          value={activePanel}
          onValueChange={(value) =>
            setActivePanel(value as "terminal" | "documents")
          }
        >
          <TabsList
            className="w-full justify-start rounded-none border-b bg-transparent px-3 py-2"
            variant="line"
          >
            <TabsTrigger data-testid="chat-side-panel-terminal-tab" value="terminal">
              <TerminalIcon className="size-4" />
              {t.workspace.inspector.terminalTab}
            </TabsTrigger>
            <TabsTrigger data-testid="chat-side-panel-documents-tab" value="documents">
              <FileTextIcon className="size-4" />
              {t.common.artifacts}
              {artifacts.length > 0 ? (
                <Badge className="ml-1" variant="secondary">
                  {artifacts.length}
                </Badge>
              ) : null}
            </TabsTrigger>
          </TabsList>
          <TabsContent
            className="min-h-0 flex-1 p-0"
            data-testid="chat-side-panel-terminal"
            value="terminal"
          >
            <TerminalActivityPanel />
          </TabsContent>
          <TabsContent
            className="min-h-0 flex-1 p-0"
            data-testid="chat-side-panel-documents"
            value="documents"
          >
            <ArtifactDocumentsPanel
              artifacts={artifacts}
              selectedArtifact={selectedArtifact}
              threadId={threadId}
              onSelect={select}
            />
          </TabsContent>
        </Tabs>
      </aside>
    </div>
  );
};

function TerminalActivityPanel() {
  const { t } = useI18n();
  const copy = t.workspace.inspector;
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    null,
  );
  const { sessions } = useSystemExecutionSessions(
    { limit: 5 },
    { enabled: true, refetchInterval: 3000 },
  );
  const activeSessionId = selectedSessionId ?? sessions[0]?.session_id ?? null;
  const { session } = useSystemExecutionSession(activeSessionId, {
    enabled: activeSessionId != null,
    refetchInterval: activeSessionId != null ? 2000 : false,
  });
  const visibleSession =
    session ?? sessions.find((item) => item.session_id === activeSessionId) ?? null;
  const latestOutput = visibleSession?.last_output?.trim();
  const latestCommand =
    visibleSession?.last_command ??
    visibleSession?.requested_commands?.[0] ??
    null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-medium">
              <TerminalIcon className="size-4" />
              {copy.latestOutput}
            </div>
            <p className="text-muted-foreground mt-1 truncate text-xs">
              {visibleSession?.session_id ?? copy.noTerminalOutputYet}
            </p>
          </div>
          {visibleSession ? (
            <Badge variant="secondary">{visibleSession.status}</Badge>
          ) : null}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {visibleSession ? (
          <div className="space-y-4">
            <div className="rounded-xl border bg-card/50 p-3">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge variant="outline">{visibleSession.target}</Badge>
                {visibleSession.last_exit_code != null ? (
                  <Badge variant="secondary">
                    {copy.exitCode}: {visibleSession.last_exit_code}
                  </Badge>
                ) : null}
                {visibleSession.updated_at ? (
                  <span className="text-muted-foreground flex items-center gap-1 text-xs">
                    <Clock3Icon className="size-3.5" />
                    {formatTimestamp(visibleSession.updated_at)}
                  </span>
                ) : null}
              </div>
              {latestCommand ? (
                <div className="mb-2 truncate font-mono text-xs">
                  $ {latestCommand}
                </div>
              ) : null}
              <div className="rounded-lg border bg-slate-950 px-3 py-3 font-mono text-xs leading-6 text-slate-100">
                {latestOutput ? (
                  <pre className="whitespace-pre-wrap break-words">
                    {latestOutput}
                  </pre>
                ) : (
                  <span className="text-slate-400">
                    {copy.noTerminalOutputYet}
                  </span>
                )}
              </div>
            </div>

            {sessions.length > 0 ? (
              <div className="space-y-2">
                <div className="text-muted-foreground text-xs font-medium">
                  {copy.recentSessions}
                </div>
                {sessions.map((item) => {
                  const command =
                    item.last_command ??
                    item.requested_commands?.[0] ??
                    copy.runtimeEvent;
                  return (
                    <button
                      className={cn(
                        "w-full rounded-lg border px-3 py-2 text-left text-xs transition hover:bg-accent/45",
                        item.session_id === activeSessionId && "bg-accent/40",
                      )}
                      key={item.session_id}
                      onClick={() => setSelectedSessionId(item.session_id)}
                      type="button"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-mono">{command}</span>
                        <Badge variant="outline">{item.status}</Badge>
                      </div>
                      <div className="text-muted-foreground mt-1 truncate">
                        {item.session_id}
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>
        ) : (
          <ConversationEmptyState
            description={copy.noTerminalOutputDescription}
            icon={<TerminalIcon />}
            title={copy.noTerminalOutputYet}
          />
        )}
      </div>
    </div>
  );
}

function ArtifactDocumentsPanel({
  artifacts,
  selectedArtifact,
  threadId,
  onSelect,
}: {
  artifacts: string[];
  selectedArtifact: string | null;
  threadId: string;
  onSelect: (artifact: string) => void;
}) {
  const { t } = useI18n();
  const copy = t.workspace.inspector;

  return (
    <div className="min-h-0 flex-1 overflow-auto p-4">
      {selectedArtifact ? (
        <ArtifactFileDetail
          className="h-full min-h-[520px]"
          filepath={selectedArtifact}
          threadId={threadId}
        />
      ) : artifacts.length > 0 ? (
        <ArtifactFileList
          files={artifacts}
          onSelect={onSelect}
          threadId={threadId}
        />
      ) : (
        <ConversationEmptyState
          description={copy.noArtifactsDescription}
          icon={<FileTextIcon />}
          title={copy.noArtifactsYet}
        />
      )}
    </div>
  );
}

function formatTimestamp(value: string) {
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return new Date(parsed).toLocaleString();
}

export { ChatBox };
