export interface ObservationTimelineEvent {
  timestamp: string;
  title: string;
  details: string[];
}

export interface TaskObservationTimelineResponse {
  task_id: string;
  events: ObservationTimelineEvent[];
}