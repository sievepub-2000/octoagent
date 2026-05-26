import { getJSON } from "../api/http";

import type { TaskObservationTimelineResponse, ToolTraceResponse } from "./types";

export async function loadTaskObservationTimeline(taskId: string) {
  return getJSON<TaskObservationTimelineResponse>(`/api/observation/tasks/${taskId}/timeline`);
}

export async function loadToolTrace(options: { limit?: number; event?: string | null } = {}) {
  const event = options.event?.trim();

  return getJSON<ToolTraceResponse>("/api/observation/tool-trace", {
    limit: options.limit ?? 80,
    event: event && event.length > 0 ? event : undefined,
  });
}