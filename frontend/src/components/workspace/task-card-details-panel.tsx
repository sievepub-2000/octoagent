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
  const [selectedCardDocumentText, setSelectedCardDocumentText] =
    useState<string | null>(null);
  const [selectedCardDocumentError, setSelectedCardDocumentError] =
    useState<string | null>(null);
  const [selectedCardDocumentLoading, setSelectedCardDocumentLoading] = useState(false);
  const [resultDocumentText, setResultDocumentText] = useState<string | null>(null);
  const [resultDocumentError, setResultDocumentError] = useState<string | null>(null);
  const [resultDocumentLoading, setResultDocumentLoading] = useState(false);

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
  const resultArtifact = artifacts.find((artifact) => artifact.path === resultDocumentPath) ?? null;
  const selectedCardArtifact =
    artifacts.find((artifact) => artifact.path === selectedDocumentPath) ?? null;
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
  const resultPanelTitle = taskWorkspace.status === "failed" ? "失败分析" : "结果文档";

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
            loadError instanceof Error ? loadError.message : "加载卡片文档失败",
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
  }, [selectedDocumentPath, taskWorkspace.task_id]);

  useEffect(() => {
    if (!showResultDocument || !resultDocumentPath) {
      setResultDocumentText(null);
      setResultDocumentError(null);
      setResultDocumentLoading(false);
      return;
    }

    let cancelled = false;
    setResultDocumentLoading(true);
    setResultDocumentError(null);

    void loadTaskWorkspaceDocumentText(taskWorkspace.task_id, resultDocumentPath)
      .then((text) => {
        if (!cancelled) {
          setResultDocumentText(text);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setResultDocumentText(null);
          setResultDocumentError(
            loadError instanceof Error ? loadError.message : "加载结果文档失败",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setResultDocumentLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [resultDocumentPath, showResultDocument, taskWorkspace.task_id]);

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
                  <div className="font-medium">卡片文档预览</div>
                  {selectedDocumentPath ? (
                    <a
                      href={taskWorkspaceFileUrl(taskWorkspace.task_id, selectedDocumentPath)}
                      rel="noreferrer"
                      target="_blank"
                    >
                      <Button size="sm" type="button" variant="outline">
                        <DownloadIcon className="size-4" />
                        {selectedCardArtifact?.name ?? "打开文档"}
                      </Button>
                    </a>
                  ) : null}
                </div>
                {selectedDocumentPath ? (
                  <div className="mt-2 text-xs text-muted-foreground">{selectedDocumentPath}</div>
                ) : null}
                <div className="mt-3">
                  {selectedDocumentPath == null ? (
                    <div className="text-sm text-muted-foreground">当前卡片没有绑定独立文档。</div>
                  ) : selectedCardDocumentLoading ? (
                    <div className="text-sm text-muted-foreground">正在加载卡片文档…</div>
                  ) : selectedCardDocumentError ? (
                    <div className="text-sm text-destructive">{selectedCardDocumentError}</div>
                  ) : selectedCardDocumentText ? (
                    <MarkdownDocumentPreview content={selectedCardDocumentText} />
                  ) : (
                    <div className="text-sm text-muted-foreground">卡片文档为空。</div>
                  )}
                </div>
              </div>
              {showResultDocument ? (
                <div className="rounded-lg border p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium">{resultPanelTitle}</div>
                    {resultDocumentPath ? (
                      <a
                        href={taskWorkspaceFileUrl(taskWorkspace.task_id, resultDocumentPath)}
                        rel="noreferrer"
                        target="_blank"
                      >
                        <Button size="sm" type="button" variant="outline">
                          <DownloadIcon className="size-4" />
                          {resultArtifact?.name ?? "打开结果文档"}
                        </Button>
                      </a>
                    ) : null}
                  </div>
                  {resultDocumentPath ? (
                    <div className="mt-2 text-xs text-muted-foreground">{resultDocumentPath}</div>
                  ) : null}
                  <div className="mt-3">
                    {resultDocumentPath == null ? (
                      <div className="text-sm text-muted-foreground">当前工作流还没有结果文档。</div>
                    ) : resultDocumentLoading ? (
                      <div className="text-sm text-muted-foreground">正在加载结果文档…</div>
                    ) : resultDocumentError ? (
                      <div className="text-sm text-destructive">{resultDocumentError}</div>
                    ) : resultDocumentText ? (
                      <MarkdownDocumentPreview content={resultDocumentText} />
                    ) : (
                      <div className="text-sm text-muted-foreground">结果文档为空。</div>
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