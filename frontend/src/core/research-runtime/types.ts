export type ResearchRuntimeCapability = {
  enabled: boolean;
  supports_experiment_loops: boolean;
  supports_code_mutation: boolean;
  supports_metric_comparison: boolean;
  supports_artifact_persistence: boolean;
  supports_program_instructions: boolean;
  supports_workspace_binding: boolean;
  supports_trial_execution: boolean;
  supports_workspace_status_projection: boolean;
  supports_runtime_snapshots: boolean;
  default_loop_template: "bounded_autoresearch" | "manual";
  note: string;
};

export type ResearchInstructionProgram = {
  instruction_id: string;
  title: string;
  summary: string;
  objective: string;
  guardrails: string[];
  iteration_budget: number;
  time_budget_minutes: number;
  allowed_mutation_roots: string[];
  allowed_tool_classes: string[];
};

export type ResearchExperimentSpec = {
  spec_id: string;
  title: string;
  objective: string;
  candidate_files: string[];
  success_metric: string;
  max_trials: number;
  evaluation_window_minutes: number;
  instruction_program_id?: string | null;
  stop_on_promote: boolean;
};

export type ResearchArtifactRef = {
  artifact_id: string;
  kind: "report" | "diff" | "metric_log" | "checkpoint";
  label: string;
  path: string;
};

export type ResearchTrialVerdict = {
  outcome: "promote" | "discard" | "review";
  rationale: string[];
  metric_delta: Record<string, number>;
  confidence: number;
};

export type ResearchExecutionBudget = {
  requested_trials: number;
  granted_trials: number;
  remaining_trials_after_run: number;
  time_budget_minutes: number;
};

export type ResearchRuntimeSnapshot = {
  total_experiments: number;
  active_experiments: number;
  completed_experiments: number;
  failed_experiments: number;
  total_trials: number;
  active_trials: number;
  experiment_status_counts: Record<string, number>;
  trial_status_counts: Record<string, number>;
  task_bound_experiments: number;
  recent_activity: Array<Record<string, string>>;
};

export type ResearchExperiment = {
  experiment_id: string;
  task_id?: string | null;
  goal: string;
  status: "planned" | "queued" | "running" | "completed" | "failed" | "cancelled";
  hypothesis?: string | null;
  success_metric?: string | null;
  instruction_program_id?: string | null;
  source: "task_workspace" | "brain" | "manual";
  spec?: ResearchExperimentSpec | null;
  trial_count: number;
  latest_trial_id?: string | null;
  promoted_trial_id?: string | null;
  last_error?: string | null;
  candidate_files: string[];
  guardrails: string[];
  progress_score: number;
  created_at: string;
  updated_at: string;
};

export type ResearchTrial = {
  trial_id: string;
  experiment_id: string;
  title: string;
  status: "planned" | "queued" | "running" | "completed" | "failed" | "discarded";
  summary: string;
  metrics: Record<string, number>;
  modified_files: string[];
  artifacts: ResearchArtifactRef[];
  verdict?: ResearchTrialVerdict | null;
  iteration_index: number;
  budget?: ResearchExecutionBudget | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ResearchExperimentListResponse = {
  experiments: ResearchExperiment[];
};

export type ResearchProgramListResponse = {
  programs: ResearchInstructionProgram[];
};

export type CreateResearchExperimentRequest = {
  goal: string;
  task_id?: string | null;
  hypothesis?: string | null;
  success_metric?: string;
  candidate_files?: string[];
  max_trials?: number;
  evaluation_window_minutes?: number;
  instruction_program_id?: string;
  source?: "task_workspace" | "brain" | "manual";
};

export type RunResearchExperimentRequest = {
  requested_trials?: number;
  stop_on_promote?: boolean;
};

export type ResearchExperimentRunResponse = {
  experiment: ResearchExperiment;
  new_trials: ResearchTrial[];
  runtime_snapshot?: ResearchRuntimeSnapshot | null;
};

export type ResearchRuntimeStatusResponse = {
  snapshot: ResearchRuntimeSnapshot;
};
