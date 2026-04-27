export type OrchestrationCapability = {
  enabled: boolean;
  supports_task_graph_compilation: boolean;
  supports_subagent_handoff: boolean;
  supports_budget_policies: boolean;
  supports_runtime_cards: boolean;
  note: string;
};

export type PromptModuleProfile = {
  module_id: string;
  stage:
    | "identity"
    | "workflow"
    | "context"
    | "reminder"
    | "compaction"
    | "summarization"
    | "routing"
    | "policy";
  title: string;
  purpose: string;
  dynamic_inputs: string[];
  instruction_template: string;
};

export type PromptStackProfile = {
  profile_id: string;
  title: string;
  modules: PromptModuleProfile[];
  source_alignment: string[];
  notes: string[];
};

export type BudgetPolicy = {
  token_budget: number;
  tool_call_budget: number;
  browser_step_budget: number;
  research_trial_budget: number;
  approval_mode: "none" | "soft" | "strict";
};

export type RuntimeBinding = {
  binding_id: string;
  kind: "agent" | "tooling" | "browser" | "research" | "system" | "review";
  target: string;
  state: "planned" | "ready" | "blocked";
  notes: string[];
};

export type RuntimeHandoff = {
  handoff_id: string;
  task_id?: string | null;
  source: "brain" | "task_workspace" | "agent_chat";
  destination: "agent_runtime" | "browser_runtime" | "research_runtime" | "review_queue";
  summary: string;
  status: "planned" | "ready" | "blocked";
};

export type OrchestrationCard = {
  card_id: string;
  title: string;
  kind: "agent" | "tooling" | "browser" | "research" | "checkpoint" | "review";
  dependencies: string[];
  runtime_binding?: RuntimeBinding | null;
};

export type CompiledTaskGraph = {
  graph_id: string;
  source_plan_summary: string;
  cards: OrchestrationCard[];
  handoffs: RuntimeHandoff[];
  budget_policy: BudgetPolicy;
};
