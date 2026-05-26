export interface ObservationTimelineEvent {
  timestamp: string;
  title: string;
  details: string[];
}

export interface TaskObservationTimelineResponse {
  task_id: string;
  events: ObservationTimelineEvent[];
}

export interface ToolTraceEntry {
  ts?: string | null;
  event: string;
  tool?: string | null;
  payload: Record<string, unknown>;
}

export interface ToolTraceResponse {
  path: string;
  entries: ToolTraceEntry[];
  count: number;
  limit: number;
  truncated: boolean;
}