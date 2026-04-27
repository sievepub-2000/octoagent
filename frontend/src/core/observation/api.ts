import { getJSON } from "../api/http";

import type { TaskObservationTimelineResponse } from "./types";

export async function loadTaskObservationTimeline(taskId: string) {
  return getJSON<TaskObservationTimelineResponse>(`/api/observation/tasks/${taskId}/timeline`);
}