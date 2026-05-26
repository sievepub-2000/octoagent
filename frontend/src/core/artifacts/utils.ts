import { getBackendBaseURL } from "../config";
import type { AgentThread } from "../threads";

export function urlOfArtifact({
  filepath,
  threadId,
  download = false,
  isMock = false,
}: {
  filepath: string;
  threadId: string;
  download?: boolean;
  isMock?: boolean;
}) {
  if (isMock) {
    return `${getBackendBaseURL()}/mock/api/threads/${threadId}/artifacts${filepath}${download ? "?download=true" : ""}`;
  }
  return `${getBackendBaseURL()}/api/threads/${threadId}/artifacts${filepath}${download ? "?download=true" : ""}`;
}

export function extractArtifactsFromThread(thread: AgentThread) {
  return thread.values.artifacts ?? [];
}

export function resolveArtifactURL(absolutePath: string, threadId: string) {
  return `${getBackendBaseURL()}/api/threads/${threadId}/artifacts${absolutePath}`;
}

export async function deleteArtifact({
  filepath,
  threadId,
}: {
  filepath: string;
  threadId: string;
}): Promise<void> {
  const url = `${getBackendBaseURL()}/api/threads/${threadId}/artifacts${filepath}`;
  const response = await fetch(url, { method: "DELETE" });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(detail || `Failed to delete artifact: ${response.status}`);
  }
}

