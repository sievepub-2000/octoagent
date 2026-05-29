"use client";

import { DownloadIcon, FolderKanbanIcon } from "lucide-react";
import { useEffect, useState, type ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { AgentAvatar } from "@/components/brand/octo-mark";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getBackendBaseURL } from "@/core/config";
import { useI18n } from "@/core/i18n/hooks";
import type {
  AgentHandle,
  TaskArtifactFile,
  TaskCard,
  TaskWorkspace,
} from "@/core/task-workspaces";

type TaskCardDetailsCopy = {
  cardDetailsTitle: string;
  cardDetailsDescription: string;
  noCardDescription: string;
  boundAgentLabel: string;
  permissionLabel: string;
  agentRoleLabel: string;
  modelLabel: string;
  documentRoleLabel: string;
  canvasPositionLabel: string;
  branchTaskLabel: string;
  promptPreviewLabel: string;
  archiveDocumentsLabel: string;
  selectCardHint: string;
};

type MarkdownCodeProps = ComponentPropsWithoutRef<"code"> & {
  inline?: boolean;
};

function statusTone(status: string) {
  if (status === "running" || status === "completed") return "default";
  if (status === "paused" || status === "waiting_review") return "secondary";
  if (status === "failed" || status === "terminated") return "destructive";
  return "outline";
}

function metadataString(metadata: Record<string, unknown>, key: string) {
  const value = metadata[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function cardPositionSummary(config: Record<string, unknown>) {
  const position = config.position;
  if (typeof position === "object" && position != null) {
    const candidate = position as { x?: unknown; y?: unknown };
    if (typeof candidate.x === "number" && typeof candidate.y === "number") {
      return `${Math.round(candidate.x)}, ${Math.round(candidate.y)}`;
    }
  }
  return null;
}

function taskWorkspaceFileUrl(taskId: string, relativePath: string) {
  const encodedPath = relativePath
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  return `${getBackendBaseURL()}/api/task-workspaces/${taskId}/artifacts/${encodedPath}?download=true`;
}

function MarkdownDocumentPreview({ content }: { content: string }) {
  return (
    <div className="octo-markdown max-h-[320px] overflow-auto rounded-md border bg-muted/10 p-3 text-sm text-foreground">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, ...props }) => (
            <a
              {...props}
              className="font-medium text-primary underline underline-offset-4"
              rel="noreferrer"
              target="_blank"
            />
          ),
          code: ({ inline, className, children, ...props }: MarkdownCodeProps) =>
            inline ? (
              <code
                {...props}
                className="rounded bg-background px-1.5 py-0.5 font-mono text-[0.85em]"
              >
                {children}
              </code>
            ) : (
              <code {...props} className={className}>
                {children}
              </code>
            ),
          pre: ({ node: _node, ...props }) => (
            <pre
              {...props}
              className="overflow-auto rounded-md border bg-background/80 p-3 font-mono text-xs leading-6"
            />
          ),
          table: ({ node: _node, ...props }) => (
            <div className="overflow-x-auto">
              <table {...props} className="w-full border-collapse text-left text-xs" />
            </div>
          ),
          th: ({ node: _node, ...props }) => (
            <th
              {...props}
              className="border border-border bg-background px-2 py-1.5 font-semibold"
            />
          ),
          td: ({ node: _node, ...props }) => (
            <td {...props} className="border border-border px-2 py-1.5 align-top" />
          ),
          blockquote: ({ node: _node, ...props }) => (
            <blockquote
              {...props}
              className="border-l-4 border-primary/40 pl-4 italic text-muted-foreground"
            />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

async function loadTaskWorkspaceDocumentText(taskId: string, relativePath: string) {
  const response = await fetch(taskWorkspaceFileUrl(taskId, relativePath), {
    headers: {
      Accept: "text/plain, text/markdown;q=0.9, */*;q=0.1",
    },
  });
  if (!response.ok) {
    throw new Error(`Failed to load document ${relativePath}`);
  }
  return response.text();
}

function isResultArtifact(path: string, resultDocumentPath: string | null) {
  if (path === resultDocumentPath) return true;
  const normalized = path.toLowerCase();
  return (
    normalized.includes("/result") ||
    normalized.includes("result/") ||
    normalized.includes("/output") ||
    normalized.includes("output/") ||
    normalized.endsWith("result.md") ||
    normalized.endsWith("results.md") ||
    normalized.endsWith("output.md")
  );
}

export function TaskCardDetailsPanel({
  taskWorkspace,
  selectedCard,
  agents,
  artifacts,
  copy,
  showResultDocument = true,
}: {
  taskWorkspace: TaskWorkspace;
  selectedCard: TaskCard | null;
  agents: AgentHandle[];
  artifacts: TaskArtifactFile[];
  copy: TaskCardDetailsCopy;
  showResultDocument?: boolean;
}) {
  const { t } = useI18n();
  const [selectedCardDocumentText, setSelectedCardDocumentText] =
    useState<string | null>(null);
  const [selectedCardDocumentError, setSelectedCardDocumentError] =
    useState<string | null>(null);
  const [selectedCardDocumentLoading, setSelectedCardDocumentLoading] = useState(false);

  const selectedCardConfig = selectedCard?.config ?? {};
  const selectedCardAgent = selectedCard?.linked_agent_id
    ? agents.find((agent) => agent.agent_id === selectedCard.linked_agent_id) ?? null
    : null;
  const selectedPromptPreview = metadataString(selectedCardConfig, "prompt_preview");
  const selectedBranchTask = metadataString(selectedCardConfig, "branch_task");
  const selectedDocumentRole = metadataString(selectedCardConfig, "document_role");
  const selectedDocumentPath = metadataString(selectedCardConfig, "document_path");
  const selectedModelName =
    metadataString(selectedCardConfig, "model_name") ?? selectedCardAgent?.model_name ?? null;
  const selectedAgentRole =
    metadataString(selectedCardConfig, "agent_role") ?? selectedCardAgent?.role ?? null;
  const selectedPosition = cardPositionSummary(selectedCardConfig);
  const projectDocumentPath = metadataString(taskWorkspace.metadata, "project_doc_path");
  const workflowDocumentPath = metadataString(taskWorkspace.metadata, "workflow_doc_path");
  const resultDocumentPath =
    metadataString(selectedCardConfig, "result_document_path")
    ?? metadataString(taskWorkspace.metadata, "result_doc_path");
  const selectedCardArtifact =
    artifacts.find((artifact) => artifact.path === selectedDocumentPath) ?? null;
  const resultArtifacts = [
    ...artifacts.filter((artifact) => isResultArtifact(artifact.path, resultDocumentPath)),
    ...(resultDocumentPath && !artifacts.some((artifact) => artifact.path === resultDocumentPath)
      ? [
          {
            name: resultDocumentPath.split("/").at(-1) ?? resultDocumentPath,
            path: resultDocumentPath,
            download_url: taskWorkspaceFileUrl(taskWorkspace.task_id, resultDocumentPath),
          },
        ]
      : []),
  ]
    .filter(
      (artifact, index, items) =>
        items.findIndex((candidate) => candidate.path === artifact.path) === index,
    )
    .sort((left, right) => left.path.localeCompare(right.path));
  const archiveDocuments = [
    { label: "Project brief", path: projectDocumentPath },
    { label: "Workflow settings", path: workflowDocumentPath ?? selectedDocumentPath },
    { label: "Card document", path: selectedDocumentPath },
    { label: "Result file", path: resultDocumentPath },
  ]
    .filter((item): item is { label: string; path: string } => Boolean(item.path))
    .filter(
      (item, index, items) =>
        items.findIndex((candidate) => candidate.path === item.path) === index,
    );
  const resultPanelTitle = taskWorkspace.status === "failed" ? t.taskCardDetails.failureAnalysis : t.taskCardDetails.resultDocument;

  useEffect(() => {
    if (!selectedDocumentPath) {
      setSelectedCardDocumentText(null);
      setSelectedCardDocumentError(null);
      setSelectedCardDocumentLoading(false);
      return;
    }

    let cancelled = false;
    setSelectedCardDocumentLoading(true);
    setSelectedCardDocumentError(null);

    void loadTaskWorkspaceDocumentText(taskWorkspace.task_id, selectedDocumentPath)
      .then((text) => {
        if (!cancelled) {
          setSelectedCardDocumentText(text);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setSelectedCardDocumentText(null);
          setSelectedCardDocumentError(
            loadError instanceof Error ? loadError.message : t.taskCardDetails.loadCardDocFailed,
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setSelectedCardDocumentLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedDocumentPath, t.taskCardDetails.loadCardDocFailed, taskWorkspace.task_id]);

  return (
    <Card className="shadow-none" data-testid="task-card-details-panel">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">{copy.cardDetailsTitle}</CardTitle>
            <CardDescription>{copy.cardDetailsDescription}</CardDescription>
          </div>
          {selectedCard ? (
            <Badge variant={statusTone(selectedCard.status)}>{selectedCard.status}</Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent>
        {selectedCard ? (
          <ScrollArea className="h-[280px] pr-3">
            <div className="space-y-4">
              <div className="rounded-lg border p-3">
                <div className="flex items-start gap-3">
                  {selectedCardAgent ? (
                    <AgentAvatar
                      avatarUrl={metadataString(selectedCardAgent.metadata, "avatar_url")}
                      size={42}
                    />
                  ) : (
                    <div className="flex size-[42px] items-center justify-center rounded-xl border bg-muted/20">
                      <FolderKanbanIcon className="size-5 text-muted-foreground" />
                    </div>
                  )}
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-medium text-foreground">{selectedCard.title}</div>
                      <Badge variant="outline">{selectedCard.kind}</Badge>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {selectedCard.description ?? copy.noCardDescription}
                    </div>
                  </div>
                </div>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-lg border p-3">
                  <div className="font-medium">{copy.boundAgentLabel}</div>
                  <div className="mt-1 text-muted-foreground">
                    {selectedCardAgent?.name
                      ?? metadataString(selectedCardConfig, "agent_name")
                      ?? "Project card"}
                  </div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="font-medium">{copy.permissionLabel}</div>
                  <div className="mt-1 text-muted-foreground">{selectedCard.permission_mode}</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="font-medium">{copy.agentRoleLabel}</div>
                  <div className="mt-1 text-muted-foreground">{selectedAgentRole ?? "n/a"}</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="font-medium">{copy.modelLabel}</div>
                  <div className="mt-1 text-muted-foreground">{selectedModelName ?? "default"}</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="font-medium">{copy.documentRoleLabel}</div>
                  <div className="mt-1 text-muted-foreground">{selectedDocumentRole ?? "n/a"}</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="font-medium">{copy.canvasPositionLabel}</div>
                  <div className="mt-1 text-muted-foreground">{selectedPosition ?? "Auto layout"}</div>
                </div>
              </div>
              {selectedBranchTask ? (
                <div className="rounded-lg border p-3">
                  <div className="font-medium">{copy.branchTaskLabel}</div>
                  <div className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">
                    {selectedBranchTask}
                  </div>
                </div>
              ) : null}
              {selectedPromptPreview ? (
                <div className="rounded-lg border p-3">
                  <div className="font-medium">{copy.promptPreviewLabel}</div>
                  <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-md border bg-muted/10 p-2 text-xs text-foreground">
                    {selectedPromptPreview}
                  </pre>
                </div>
              ) : null}
              {archiveDocuments.length > 0 ? (
                <div className="rounded-lg border p-3">
                  <div className="font-medium">{copy.archiveDocumentsLabel}</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {archiveDocuments.map((document) => (
                      <a
                        href={taskWorkspaceFileUrl(taskWorkspace.task_id, document.path)}
                        key={document.path}
                        rel="noreferrer"
                        target="_blank"
                      >
                        <Button size="sm" type="button" variant="outline">
                          <DownloadIcon className="size-4" />
                          {document.label}
                        </Button>
                      </a>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="rounded-lg border p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium">{t.taskCardDetails.cardDocumentPreview}</div>
                  {selectedDocumentPath ? (
                    <a
                      href={taskWorkspaceFileUrl(taskWorkspace.task_id, selectedDocumentPath)}
                      rel="noreferrer"
                      target="_blank"
                    >
                      <Button size="sm" type="button" variant="outline">
                        <DownloadIcon className="size-4" />
                        {selectedCardArtifact?.name ?? t.taskCardDetails.openDocument}
                      </Button>
                    </a>
                  ) : null}
                </div>
                {selectedDocumentPath ? (
                  <div className="mt-2 text-xs text-muted-foreground">{selectedDocumentPath}</div>
                ) : null}
                <div className="mt-3">
                  {selectedDocumentPath == null ? (
                    <div className="text-sm text-muted-foreground">{t.taskCardDetails.noBoundDocument}</div>
                  ) : selectedCardDocumentLoading ? (
                    <div className="text-sm text-muted-foreground">{t.taskCardDetails.loadingCardDoc}</div>
                  ) : selectedCardDocumentError ? (
                    <div className="text-sm text-destructive">{selectedCardDocumentError}</div>
                  ) : selectedCardDocumentText ? (
                    <MarkdownDocumentPreview content={selectedCardDocumentText} />
                  ) : (
                    <div className="text-sm text-muted-foreground">{t.taskCardDetails.cardDocEmpty}</div>
                  )}
                </div>
              </div>
              {showResultDocument ? (
                <div className="rounded-lg border p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium">{resultPanelTitle}</div>
                    <Badge variant="outline">{resultArtifacts.length}</Badge>
                  </div>
                  <div className="mt-3 space-y-2">
                    {resultArtifacts.length === 0 ? (
                      <div className="text-sm text-muted-foreground">{t.taskCardDetails.noDownloadableResult}</div>
                    ) : (
                      resultArtifacts.map((artifact, index) => (
                        <a
                          className="flex items-center justify-between gap-3 rounded-md border bg-muted/10 px-3 py-2 text-sm transition hover:bg-muted/20"
                          href={artifact.download_url || taskWorkspaceFileUrl(taskWorkspace.task_id, artifact.path)}
                          key={artifact.path}
                          rel="noreferrer"
                          target="_blank"
                        >
                          <span className="min-w-0">
                            <span className="font-medium">{index + 1}. {artifact.name}</span>
                            <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                              {artifact.path}
                            </span>
                          </span>
                          <DownloadIcon className="size-4 shrink-0 text-muted-foreground" />
                        </a>
                      ))
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </ScrollArea>
        ) : (
          <div className="text-sm text-muted-foreground">{copy.selectCardHint}</div>
        )}
      </CardContent>
    </Card>
  );
}