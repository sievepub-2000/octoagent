export type BrainPlanStep = {
  id: string;
  title: string;
  description: string;
  status: "pending" | "ready" | "blocked";
};

export type BrainPlan = {
  summary: string;
  steps: BrainPlanStep[];
};

export type BrainAnalysis = {
  findings: string[];
  risks: string[];
  confidence: number;
};

export type BrainDecision = {
  recommendation: string;
  rationale: string[];
  risk_level: "low" | "medium" | "high";
};

export type BrainApprovalCheckpoint = {
  id: string;
  title: string;
  required: boolean;
  status: "pending" | "ready" | "blocked";
  phase: "inputs" | "review" | "approval" | "execution";
  reason?: string | null;
  handoff_kind:
    | "operator_review"
    | "risk_signoff"
    | "evidence_review"
    | "policy_signoff";
  owner_role:
    | "operator"
    | "risk_reviewer"
    | "research_reviewer"
    | "policy_reviewer";
  next_step?: string | null;
};

export type BrainExecutionContract = {
  template:
    | "generic_analysis"
    | "quant_backtest"
    | "research_review"
    | "policy_review";
  readiness: "ready" | "review_required" | "blocked";
  current_phase: "inputs" | "review" | "approval" | "execution" | "plan";
  next_owner:
    | "operator"
    | "risk_reviewer"
    | "research_reviewer"
    | "policy_reviewer"
    | "system";
  memory_context_strength: "none" | "light" | "strong";
  review_intensity: "standard" | "heightened";
  suggested_workflow_mode: "task" | "branch" | "group";
  required_inputs: string[];
  missing_inputs: string[];
  checkpoints: BrainApprovalCheckpoint[];
  suggested_runtime_mode: "plan" | "task" | "workflow";
  notes: string[];
  quant_backtest?: BrainQuantBacktestContract | null;
};

export type BrainBuilderAction = {
  id: string;
  kind: string;
  title: string;
  description: string;
  auto_apply: boolean;
  status: "ready" | "manual" | "already_aligned";
  target_field?: string | null;
  patch: Record<string, unknown>;
};

export type BrainBuilderActionModel = {
  summary: string;
  auto_actions: BrainBuilderAction[];
  manual_actions: BrainBuilderAction[];
  apply_all_patch: Record<string, unknown>;
};

export type BrainQuantBacktestContract = {
  factor_count: number;
  evidence_count: number;
  risk_guardrail_count: number;
  factor_candidates: string[];
  risk_guardrails: string[];
  suggested_universe: "broad_market" | "constrained" | "undefined";
  execution_phase:
    | "collect_inputs"
    | "review_inputs"
    | "await_approval"
    | "prepare_execution";
  next_action: "collect_inputs" | "prepare_backtest" | "manual_review";
  approval_handoff: "operator_review" | "risk_signoff" | "not_ready";
};

export type BrainStrategyNode = {
  id: string;
  title: string;
  stage: "observe" | "infer" | "score" | "decide" | "execute" | "review";
  produces: string[];
  consumes: string[];
};

export type BrainStrategyEdge = {
  source: string;
  target: string;
  kind: "precedence" | "causal" | "feedback_lagged";
  lag: number;
};

export type BrainOutputArbitration = {
  output_name: string;
  mode:
    | "single_owner"
    | "weighted_vote"
    | "stacked_meta"
    | "policy_gate"
    | "veto";
  owners: string[];
};

export type BrainStrategyGraph = {
  nodes: BrainStrategyNode[];
  edges: BrainStrategyEdge[];
  arbitrations: BrainOutputArbitration[];
};

export type BrainStrategyValidation = {
  valid: boolean;
  execution_order: string[];
  errors: string[];
  warnings: string[];
};

export type BrainResponse = {
  plan: BrainPlan;
  analysis: BrainAnalysis;
  decision: BrainDecision;
  execution_contract: BrainExecutionContract;
  builder_action_model: BrainBuilderActionModel;
  strategy_graph: BrainStrategyGraph;
  strategy_validation: BrainStrategyValidation;
};

export type BrainPlanRequest = {
  thread_id?: string | null;
  user_goal: string;
  constraints?: string[];
  evidence?: string[];
  preferred_mode?: "plan" | "research" | "quant" | "policy";
  factor_candidates?: string[];
  risk_limits?: string[];
  memory_hints?: string[];
};
