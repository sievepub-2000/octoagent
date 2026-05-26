const STORAGE_KEY = "octoagent:chunk-load-recovery";
const MAX_RETRY_AGE_MS = 60_000;
const WORKSPACE_LAYOUT_CHUNK = "/_next/static/chunks/app/workspace/layout.js";

type StoredRecovery = {
  url: string;
  at: number;
};

function messageFromUnknown(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (value instanceof Error) return `${value.message}\n${value.stack ?? ""}`;
  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint" ||
    typeof value === "symbol"
  ) {
    return String(value);
  }
  try {
    return JSON.stringify(value) ?? "";
  } catch {
    return "";
  }
}

export function isChunkLoadFailure(value: unknown): boolean {
  const message = messageFromUnknown(value);
  return /ChunkLoadError|Loading chunk [^\n]+ failed|Loading CSS chunk [^\n]+ failed|Failed to fetch dynamically imported module/i.test(message);
}

function isNextStaticAsset(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tagName = target.tagName.toUpperCase();
  const url: string | undefined =
    tagName === "SCRIPT"
      ? (target as HTMLScriptElement).src
      : tagName === "LINK"
        ? (target as HTMLLinkElement).href
        : undefined;
  return Boolean(url?.includes("/_next/static/"));
}

function currentUrl(): string {
  return `${window.location.pathname}${window.location.search}`;
}

function readPreviousRecovery(): StoredRecovery | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredRecovery>;
    if (typeof parsed.url !== "string" || typeof parsed.at !== "number") {
      return null;
    }
    return { url: parsed.url, at: parsed.at };
  } catch {
    return null;
  }
}

function markRecoveryAttempt(): boolean {
  const url = currentUrl();
  const previous = readPreviousRecovery();
  if (previous?.url === url && Date.now() - previous.at < MAX_RETRY_AGE_MS) {
    return false;
  }
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ url, at: Date.now() }));
  } catch {
    // Session storage can be unavailable in privacy modes; still allow one reload.
  }
  return true;
}

export function recoverFromChunkLoadFailure(reason: unknown): boolean {
  if (!isChunkLoadFailure(reason)) return false;
  if (!markRecoveryAttempt()) return false;
  window.location.reload();
  return true;
}

function hasFailedWorkspaceLayoutResource(): boolean {
  return performance
    .getEntriesByType("resource")
    .some((entry) => {
      const resource = entry as PerformanceResourceTiming;
      return resource.name.includes(WORKSPACE_LAYOUT_CHUNK) && resource.transferSize === 0 && resource.decodedBodySize === 0;
    });
}

function recoverStuckWorkspaceShell(): void {
  if (!window.location.pathname.startsWith("/workspace/")) return;

  const bodyText = document.body?.innerText ?? "";
  const hasInput = Boolean(document.querySelector("textarea"));
  const hasInspector = Boolean(document.querySelector('[data-testid="workflow-inspector-layout"]'));
  const hasCompleteChatShell = hasInput || hasInspector;
  const hasChunkFailureText = /ChunkLoadError|Loading chunk app\/workspace\/layout failed|This page couldn.t load|Something went wrong/i.test(bodyText);
  const hasStuckChatFallback = /正在准备对话工作区|Loading runtime inspector/i.test(bodyText) && !hasCompleteChatShell;

  if (hasChunkFailureText || (hasStuckChatFallback && hasFailedWorkspaceLayoutResource())) {
    recoverFromChunkLoadFailure("ChunkLoadError: workspace layout shell did not finish loading");
  }
}

export function clearSettledChunkRecovery(): void {
  const previous = readPreviousRecovery();
  if (!previous) return;
  if (previous.url === currentUrl() && Date.now() - previous.at > 5_000) {
    try {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } catch {}
  }
}

export function installChunkLoadRecovery(): () => void {
  const watchdogTimers = [6_000, 12_000, 20_000].map((delay) =>
    window.setTimeout(recoverStuckWorkspaceShell, delay),
  );

  const handleError = (event: ErrorEvent | Event) => {
    const errorEvent = event as ErrorEvent;
    if (isNextStaticAsset(event.target)) {
      recoverFromChunkLoadFailure("ChunkLoadError: Next static asset failed");
      return;
    }
    recoverFromChunkLoadFailure(errorEvent.message);
    recoverFromChunkLoadFailure(errorEvent.error instanceof Error ? errorEvent.error.message : errorEvent.error);
  };

  const handleRejection = (event: PromiseRejectionEvent) => {
    recoverFromChunkLoadFailure(event.reason);
  };

  const handleLoad = () => {
    window.setTimeout(clearSettledChunkRecovery, 8_000);
  };

  window.addEventListener("error", handleError, true);
  window.addEventListener("unhandledrejection", handleRejection);
  window.addEventListener("load", handleLoad);

  return () => {
    for (const timer of watchdogTimers) {
      window.clearTimeout(timer);
    }
    window.removeEventListener("error", handleError, true);
    window.removeEventListener("unhandledrejection", handleRejection);
    window.removeEventListener("load", handleLoad);
  };
}
