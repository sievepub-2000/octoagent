"use client";

import type { Message } from "@langchain/langgraph-sdk";
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  CircleDotIcon,
  CopyIcon,
  DownloadIcon,
  FileTextIcon,
  Loader2Icon,
  PauseIcon,
  XCircleIcon,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getBackendBaseURL } from "@/core/config";
import { useI18n } from "@/core/i18n/hooks";
import { useTaskArtifacts, useTaskResult, useTaskStudioRuntime } from "@/core/task-workspaces/hooks";
import type { TaskArtifactFile, TaskCard, TaskWorkspace, TaskWorkspaceStatus } from "@/core/task-workspaces/types";
import { useThreadState } from "@/core/threads/hooks";
import { textOfMessage } from "@/core/threads/utils";
import { cn } from "@/lib/utils";

interface WorkflowResultCardProps {
  taskId: string;
  status: TaskWorkspaceStatus;
  selectedCard?: TaskCard | null;
  taskWorkspace?: TaskWorkspace | null;
  artifactsOverride?: TaskArtifactFile[];
  className?: string;
  defaultExpanded?: boolean;
  resultViewportClassName?: string;
}

const TERMINAL_STATUSES: TaskWorkspaceStatus[] = ["completed", "failed", "terminated"];
const PREPARATION_STATUSES: TaskWorkspaceStatus[] = ["created", "planned"];
const RUNTIME_VISIBLE_STATUSES: TaskWorkspaceStatus[] = ["running", "paused", "waiting_review", ...TERMINAL_STATUSES];

function buildLiveThreadResult(messages: Message[] | undefined) {
  if (!messages || messages.length === 0) {
    return null;
  }

  const parts: string[] = [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!message || message.type === "human") {
      continue;
    }

    const text = textOfMessage(message);
    if (!text) {
      continue;
    }

    parts.unshift(text);
    if (parts.length >= 3) {
      break;
    }
  }

  return parts.length > 0 ? parts.join("---") : null;
}

function metadataString(config: Record<string, unknown>, key: string) {
  const value = config[key];
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function artifactFileUrl(taskId: string, relativePath: string) {
  const encodedPath = relativePath
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  return `${getBackendBaseURL()}/api/task-workspaces/${encodeURIComponent(taskId)}/artifacts/${encodedPath}`;
}

function selectedCardCandidates(selectedCard: TaskCard | null | undefined, taskWorkspace: TaskWorkspace | null | undefined) {
  if (!selectedCard) {
    return [] as Array<{ path: string; label: string }>;
  }

  const candidates: Array<{ path: string; label: string }> = [];
  const resultPath = metadataString(selectedCard.config, "result_document_path");
  const documentPath = metadataString(selectedCard.config, "document_path");
  const workflowResultPath = metadataString(taskWorkspace?.metadata ?? {}, "result_doc_path");

  if (resultPath) {
    candidates.push({ path: resultPath, label: `Selected card result: ${resultPath}` });
  }
  if (documentPath && documentPath !== resultPath) {
    candidates.push({ path: documentPath, label: `Selected card document: ${documentPath}` });
  }
  if (workflowResultPath && workflowResultPath !== resultPath && workflowResultPath !== documentPath) {
    candidates.push({ path: workflowResultPath, label: `Workflow result: ${workflowResultPath}` });
  }
  return candidates;
}

function createHeadingId(value: string) {
  const id = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5\u3040-\u30ff\uac00-\ud7af\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
  return id || "section";
}

function uniqueHeadingId(baseId: string, counts: Map<string, number>) {
  const seen = counts.get(baseId) ?? 0;
  counts.set(baseId, seen + 1);
  return seen === 0 ? baseId : `${baseId}-${seen + 1}`;
}

function markdownChildrenText(children: ReactNode): string {
  if (typeof children === "string" || typeof children === "number") {
    return String(children);
  }
  if (Array.isArray(children)) {
    return children.map(markdownChildrenText).join(" ");
  }
  return "";
}

function extractMarkdownSections(markdown: string) {
  const headingCounts = new Map<string, number>();
  return [...markdown.matchAll(/^(#{1,3})\s+(.+)$/gm)].flatMap((match) => {
    const title = match[2]?.trim() ?? "";
    if (!title) {
      return [];
    }
    const baseId = createHeadingId(title);
    return [
      {
        depth: match[1]?.length ?? 1,
        title,
        id: uniqueHeadingId(baseId, headingCounts),
      },
    ];
  });
}

function fileNameFromPath(value: string | null | undefined, fallback: string) {
  if (!value) {
    return fallback;
  }
  const normalized = value.split("?")[0] ?? value;
  const segments = normalized.split("/").filter(Boolean);
  return segments.at(-1) ?? fallback;
}

export function WorkflowResultCard({
  taskId,
  status,
  selectedCard,
  taskWorkspace,
  artifactsOverride,
  className,
  defaultExpanded: _defaultExpanded = true,
  resultViewportClassName,
}: WorkflowResultCardProps) {
  const { t } = useI18n();
  const isRunning = status === "running";
  const shouldShow = PREPARATION_STATUSES.includes(status) || RUNTIME_VISIBLE_STATUSES.includes(status);
  const shouldLoadRuntime = RUNTIME_VISIBLE_STATUSES.includes(status);

  const { resultContent, hasResult, sourceLabel, sourcePath, isLoading: resultLoading } = useTaskResult(taskId, {
    enabled: shouldShow,
    refetchInterval: isRunning ? 5000 : false,
  });
  const { artifacts, isLoading: artifactsLoading } = useTaskArtifacts(taskId, {
    enabled: shouldShow,
    refetchInterval: isRunning ? 5000 : false,
  });
  const { studioRuntime, isLoading: runtimeLoading } = useTaskStudioRuntime(taskId, {
    enabled: shouldLoadRuntime,
    refetchInterval: isRunning ? 5000 : false,
  });

  const runtimeSessionId = studioRuntime?.runtime_summary.latest_runtime_session_id ?? null;
  const runtimeProvider = (studioRuntime?.runtime_summary.last_runtime_provider ?? taskWorkspace?.agent_runtime_provider ?? "").toLowerCase();
  const canLoadThreadState = runtimeSessionId != null && (runtimeSessionId.startsWith("thread") || runtimeProvider.includes("langgraph"));
  const { data: threadState, isVerifying: threadLoading } = useThreadState(
    runtimeSessionId,
    shouldLoadRuntime && canLoadThreadState && !resultLoading && (!hasResult || isRunning),
  );

  const [selectedCardContent, setSelectedCardContent] = useState<string | null>(null);
  const [selectedCardSource, setSelectedCardSource] = useState<string | null>(null);
  const [selectedCardSourcePath, setSelectedCardSourcePath] = useState<string | null>(null);
  const [selectedCardLoading, setSelectedCardLoading] = useState(false);
  const [generatedDownloadHref, setGeneratedDownloadHref] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const candidates = selectedCardCandidates(selectedCard, taskWorkspace);
    if (candidates.length === 0) {
      setSelectedCardContent(null);
      setSelectedCardSource(null);
      setSelectedCardSourcePath(null);
      setSelectedCardLoading(false);
      return undefined;
    }

    setSelectedCardLoading(true);
    setSelectedCardContent(null);
    setSelectedCardSource(null);
    setSelectedCardSourcePath(null);

    async function loadSelectedCardContent() {
      for (const candidate of candidates) {
        try {
          const response = await fetch(artifactFileUrl(taskId, candidate.path));
          if (!response.ok) {
            continue;
          }
          const text = await response.text();
          if (!text.trim()) {
            continue;
          }
          if (!cancelled) {
            setSelectedCardContent(text);
            setSelectedCardSource(candidate.label);
            setSelectedCardSourcePath(candidate.path);
            setSelectedCardLoading(false);
          }
          return;
        } catch {
          continue;
        }
      }

      if (!cancelled) {
        setSelectedCardContent(null);
        setSelectedCardSource(null);
        setSelectedCardSourcePath(null);
        setSelectedCardLoading(false);
      }
    }

    void loadSelectedCardContent();
    return () => {
      cancelled = true;
    };
  }, [selectedCard, taskId, taskWorkspace]);

  const liveThreadResult = useMemo(() => buildLiveThreadResult(threadState?.messages), [threadState?.messages]);
  const runtimeSummaryResult = useMemo(() => {
    const summary = studioRuntime?.runtime_summary.last_agent_result_summary;
    return typeof summary === "string" && summary.trim().length > 0 ? summary.trim() : null;
  }, [studioRuntime?.runtime_summary.last_agent_result_summary]);

  const effectiveResultContent = selectedCardContent
    ?? (hasResult && resultContent.trim().length > 0 ? resultContent : null)
    ?? liveThreadResult
    ?? runtimeSummaryResult
    ?? "";
  const effectiveHasResult = effectiveResultContent.trim().length > 0;
  const resultSource = selectedCardSource
    ?? (hasResult && resultContent.trim().length > 0 ? (sourceLabel ?? sourcePath ?? "03_RESULT.md") : null)
    ?? (liveThreadResult ? "LangGraph" : null)
    ?? (runtimeSummaryResult ? "runtime-summary" : null);
  const resultSections = useMemo(() => extractMarkdownSections(effectiveResultContent), [effectiveResultContent]);
  const visibleArtifacts = useMemo(() => artifactsOverride ?? artifacts, [artifacts, artifactsOverride]);
  const serverDownloadHref = useMemo(() => {
    const artifactPath = selectedCardSourcePath ?? sourcePath ?? null;
    return artifactPath ? artifactFileUrl(taskId, artifactPath) : null;
  }, [selectedCardSourcePath, sourcePath, taskId]);
  const downloadFileName = useMemo(
    () => fileNameFromPath(selectedCardSourcePath ?? sourcePath, `${taskId}-result.md`),
    [selectedCardSourcePath, sourcePath, taskId],
  );
  const isLoading = resultLoading || artifactsLoading || runtimeLoading || threadLoading;

  useEffect(() => {
    if (!effectiveHasResult || serverDownloadHref) {
      setGeneratedDownloadHref((current) => {
        if (current) {
          URL.revokeObjectURL(current);
        }
        return null;
      });
      return undefined;
    }

    const href = URL.createObjectURL(new Blob([effectiveResultContent], { type: "text/markdown;charset=utf-8" }));
    setGeneratedDownloadHref((current) => {
      if (current) {
        URL.revokeObjectURL(current);
      }
      return href;
    });

    return () => {
      URL.revokeObjectURL(href);
    };
  }, [effectiveHasResult, effectiveResultContent, serverDownloadHref]);

  const failureInfo = useMemo(() => {
    if (status !== "failed" || !effectiveResultContent) {
      return null;
    }
    const lines = effectiveResultContent.split("");
    let failureReason = "";
    let output = "";
    let inOutput = false;
    for (const line of lines) {
      if (line.startsWith("- Failure reason:")) {
        failureReason = line.replace("- Failure reason:", "").trim();
        continue;
      }
      if (line === "## Output") {
        inOutput = true;
        continue;
      }
      if (line.startsWith("## ") && line !== "## Output") {
        inOutput = false;
        continue;
      }
      if (inOutput) {
        output += `${line}`;
      }
    }
    return { reason: failureReason, output: output.trim() };
  }, [effectiveResultContent, status]);

  if (!shouldShow) {
    return null;
  }

  const statusConfig = {
    created: {
      icon: <CircleDotIcon className="size-5" />,
      label: t.workflows.statusCreated,
      borderClass: "border-muted-foreground/20",
      bgClass: "bg-muted/20",
      textClass: "text-muted-foreground",
      badgeClass: "bg-muted text-muted-foreground",
    },
    planned: {
      icon: <CircleDotIcon className="size-5" />,
      label: t.workflows.statusCreated,
      borderClass: "border-muted-foreground/20",
      bgClass: "bg-muted/20",
      textClass: "text-muted-foreground",
      badgeClass: "bg-muted text-muted-foreground",
    },
    completed: {
      icon: <CheckCircle2Icon className="size-5" />,
      label: t.workflows.statusCompleted,
      borderClass: "border-green-500/30",
      bgClass: "bg-green-500/5",
      textClass: "text-green-600 dark:text-green-400",
      badgeClass: "bg-green-500/15 text-green-600 dark:text-green-400",
    },
    failed: {
      icon: <XCircleIcon className="size-5" />,
      label: t.workflows.statusFailed,
      borderClass: "border-destructive/30",
      bgClass: "bg-destructive/5",
      textClass: "text-destructive",
      badgeClass: "bg-destructive/15 text-destructive",
    },
    terminated: {
      icon: <AlertTriangleIcon className="size-5" />,
      label: t.workflows.statusTerminated,
      borderClass: "border-amber-500/30",
      bgClass: "bg-amber-500/5",
      textClass: "text-amber-600 dark:text-amber-400",
      badgeClass: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
    },
    paused: {
      icon: <PauseIcon className="size-5" />,
      label: t.workflows.statusPaused,
      borderClass: "border-amber-500/30",
      bgClass: "bg-amber-500/5",
      textClass: "text-amber-600 dark:text-amber-400",
      badgeClass: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
    },
    waiting_review: {
      icon: <PauseIcon className="size-5" />,
      label: t.workflows.statusWaitingReview,
      borderClass: "border-amber-500/30",
      bgClass: "bg-amber-500/5",
      textClass: "text-amber-600 dark:text-amber-400",
      badgeClass: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
    },
    running: {
      icon: <Loader2Icon className="size-5 animate-spin" />,
      label: t.workflows.statusRunning,
      borderClass: "border-blue-500/30",
      bgClass: "bg-blue-500/5",
      textClass: "text-blue-600 dark:text-blue-400",
      badgeClass: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
    },
  };

  const config = statusConfig[status as keyof typeof statusConfig] ?? statusConfig.completed;

  const handleCopyResult = async () => {
    if (!effectiveHasResult) {
      return;
    }
    await navigator.clipboard.writeText(effectiveResultContent);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <section
      data-testid="workflow-result-card"
      className={cn("rounded-[28px] border px-5 py-5", config.borderClass, config.bgClass, className)}
    >
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border/70 pb-4">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className={config.textClass}>{config.icon}</span>
            <h3 className="text-base font-semibold text-foreground">{t.workflows.resultTitle}</h3>
            <Badge variant="outline" className={cn("text-[10px]", config.badgeClass)}>
              {config.label}
            </Badge>
            {selectedCard ? (
              <Badge variant="secondary" className="text-[10px]">
                {selectedCard.title || selectedCard.kind}
              </Badge>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
            {resultSource ? <span>{t.workflows.resultDocumentSource}: {resultSource}</span> : null}
            {visibleArtifacts.length > 0 ? <span>{t.workflows.generatedFiles}: {visibleArtifacts.length}</span> : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => void handleCopyResult()} disabled={!effectiveHasResult} data-testid="workflow-result-copy">
            <CopyIcon className="size-4" />
            {copied ? t.clipboard.copiedToClipboard : t.workflows.copyResult}
          </Button>
          {(serverDownloadHref || generatedDownloadHref) ? (
            <Button asChild variant="outline" size="sm">
              <a data-testid="workflow-result-download" href={serverDownloadHref ?? generatedDownloadHref ?? undefined} download={downloadFileName}>
                <DownloadIcon className="size-4" />
                {t.workflows.downloadResult}
              </a>
            </Button>
          ) : null}
        </div>
      </div>

      {isLoading || selectedCardLoading ? (
        <div className="flex items-center justify-center py-8 text-muted-foreground">
          <Loader2Icon className="mr-2 size-4 animate-spin" />
          <span className="text-sm">{t.common.loading}</span>
        </div>
      ) : (
        <div className="pt-5">
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,220px)]">
            <aside className="space-y-4 xl:order-2">
              <div className="rounded-2xl border border-border/70 bg-background/72 p-4">
                <div className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground/80">
                  {t.workflows.resultSections}
                </div>
                {resultSections.length > 0 ? (
                  <div className="mt-3 space-y-2">
                    {resultSections.map((section) => (
                      <div
                        key={section.id}
                        className={cn(
                          "rounded-xl border border-border/60 bg-muted/10 px-3 py-2 text-sm text-foreground",
                          section.depth === 1 ? "font-semibold" : section.depth === 2 ? "pl-4" : "pl-5 text-muted-foreground",
                        )}
                      >
                        {section.title}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3 text-sm text-muted-foreground">{t.workflows.noResultSections}</div>
                )}
              </div>

              {status === "failed" && failureInfo ? (
                <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-4" data-testid="workflow-result-failure">
                  <h4 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-destructive">
                    <XCircleIcon className="size-4" />
                    {t.workflows.failureAnalysis}
                  </h4>
                  {failureInfo.reason ? (
                    <div className="mb-3">
                      <p className="mb-1 text-xs font-medium text-muted-foreground">{t.workflows.failureReason}</p>
                      <p className="text-sm text-foreground">{failureInfo.reason}</p>
                    </div>
                  ) : null}
                  {failureInfo.output && failureInfo.output !== "_No output recorded._" ? (
                    <div className="mb-3">
                      <p className="mb-1 text-xs font-medium text-muted-foreground">{t.workflows.failureOutput}</p>
                      <div className="max-h-60 overflow-y-auto rounded-md border bg-card p-3 text-sm">
                        <ReactMarkdown
                          components={{
                            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                            code: ({ children }) => <code className="rounded bg-muted px-1 py-0.5 text-xs">{children}</code>,
                            pre: ({ children }) => <pre className="mb-2 overflow-x-auto rounded bg-muted p-2 text-xs last:mb-0">{children}</pre>,
                          }}
                        >
                          {failureInfo.output}
                        </ReactMarkdown>
                      </div>
                    </div>
                  ) : null}
                  <div>
                    <p className="mb-1 text-xs font-medium text-muted-foreground">{t.workflows.possibleSolutions}</p>
                    <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                      <li>{t.workflows.solutionCheckLog}</li>
                      <li>{t.workflows.solutionCheckConfig}</li>
                      <li>{t.workflows.solutionRetry}</li>
                    </ul>
                  </div>
                </div>
              ) : null}
            </aside>

            <div className="min-w-0 xl:order-1">
              <div className="rounded-2xl border border-border/70 bg-background/78 p-4">
                <h4 className="mb-3 flex items-center gap-1.5 text-sm font-semibold">
                  <FileTextIcon className="size-4" />
                  {t.workflows.resultContent}
                  {resultSource ? (
                    <Badge variant="outline" className="ml-2 text-[10px]">
                      {resultSource}
                    </Badge>
                  ) : null}
                </h4>

                {effectiveHasResult ? (
                  <article className={cn("overflow-y-auto rounded-2xl border border-border/70 bg-card p-4", resultViewportClassName)} data-testid="workflow-result-document">
                    <div className="prose prose-sm max-w-none dark:prose-invert">
                      <ReactMarkdown
                        components={{
                          h1: ({ children }) => <h1 className="mb-3 text-lg font-bold" id={createHeadingId(markdownChildrenText(children))}>{children}</h1>,
                          h2: ({ children }) => <h2 className="mb-2 mt-4 text-base font-semibold" id={createHeadingId(markdownChildrenText(children))}>{children}</h2>,
                          h3: ({ children }) => <h3 className="mb-1.5 mt-3 text-sm font-semibold" id={createHeadingId(markdownChildrenText(children))}>{children}</h3>,
                          p: ({ children }) => <p className="mb-2 text-sm leading-relaxed last:mb-0">{children}</p>,
                          ul: ({ children }) => <ul className="mb-2 list-inside list-disc space-y-1 text-sm">{children}</ul>,
                          ol: ({ children }) => <ol className="mb-2 list-inside list-decimal space-y-1 text-sm">{children}</ol>,
                          code: ({ children }) => <code className="rounded bg-muted px-1 py-0.5 text-xs">{children}</code>,
                          pre: ({ children }) => <pre className="mb-3 overflow-x-auto rounded-md bg-muted p-3 text-xs last:mb-0">{children}</pre>,
                          a: ({ href, children }) => (
                            <a href={href} className="text-primary underline hover:text-primary/80" target="_blank" rel="noopener noreferrer">
                              {children}
                            </a>
                          ),
                        }}
                      >
                        {effectiveResultContent}
                      </ReactMarkdown>
                    </div>
                  </article>
                ) : (
                  <div className="rounded-2xl border border-dashed bg-card p-4 text-sm text-muted-foreground">
                    {t.workflows.noResultYet}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
