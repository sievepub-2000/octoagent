"use client";

import {
  GitBranchPlusIcon,
  GitForkIcon,
  ListTodoIcon,
  SparklesIcon,
  ShieldAlertIcon,
  Trash2Icon,
  UsersRoundIcon,
} from "lucide-react";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  useBrainPlan,
  type BrainBuilderAction,
  type BrainBuilderActionModel,
  type BrainExecutionContract,
} from "@/core/brain";
import { useRuntimeCapabilities } from "@/core/runtime";
import { useWorkflows } from "@/core/workflows";
import {
  buildBrainPlanPayload,
  countWorkflowSteps,
  type Workflow,
} from "@/core/workflows";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<Workflow["status"], string> = {
  draft: "Draft",
  queued: "Queued",
  running: "Running",
  waiting_retry: "Retrying",
  waiting_user: "Need user",
  blocked: "Blocked",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

const MODE_ICON = {
  task: GitBranchPlusIcon,
  branch: GitForkIcon,
  group: UsersRoundIcon,
};

export function WorkflowBuilder() {
  const { workflows, selectedWorkflow, selectedWorkflowId, create, remove, select, update } =
    useWorkflows();
  const { runtime } = useRuntimeCapabilities();
  const maxWorkflowAgents =
    runtime?.agent_limits.max_total_subagents_per_thread ?? 8;
  const maxBranches =
    runtime?.agent_limits.max_active_subagents_per_thread ?? 6;

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <RuntimeGuide />
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => create("task")}>
          <GitBranchPlusIcon />
          Task
        </Button>
        <Button size="sm" variant="outline" onClick={() => create("branch")}>
          <GitForkIcon />
          Branch
        </Button>
        <Button size="sm" variant="outline" onClick={() => create("group")}>
          <UsersRoundIcon />
          Group
        </Button>
      </div>

      <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
        <ScrollArea className="min-h-0 rounded-xl border">
          <div className="space-y-3 p-3">
            {workflows.length === 0 ? (
              <Card className="gap-3 border-dashed py-4 shadow-none">
                <CardHeader className="px-4">
                  <CardTitle className="text-sm">No workflow cards yet</CardTitle>
                  <CardDescription>
                    Start with `task` for most jobs. Use `branch` for parallel work,
                    and `group` only when discussion really matters.
                  </CardDescription>
                </CardHeader>
              </Card>
            ) : (
              workflows.map((workflow) => {
                const Icon = MODE_ICON[workflow.mode];
                const selected = workflow.id === selectedWorkflowId;
                return (
                  <button
                    className={cn("w-full text-left")}
                    key={workflow.id}
                    onClick={() => select(workflow.id)}
                    type="button"
                  >
                    <Card
                      className={cn(
                        "gap-3 py-4 transition-colors",
                        selected
                          ? "border-foreground/30 bg-accent/35"
                          : "hover:bg-accent/20 shadow-none",
                      )}
                    >
                      <CardHeader className="px-4">
                        <div className="flex items-start justify-between gap-2">
                          <div className="space-y-1">
                            <CardTitle className="flex items-center gap-2 text-sm">
                              <Icon className="size-4" />
                              {workflow.title}
                            </CardTitle>
                            <CardDescription className="line-clamp-2">
                              {workflow.goal || "Describe the goal in one sentence"}
                            </CardDescription>
                          </div>
                          <Badge variant="secondary">{workflow.mode}</Badge>
                        </div>
                      </CardHeader>
                      <CardContent className="flex items-center justify-between px-4 text-xs text-muted-foreground">
                        <span>{STATUS_LABEL[workflow.status]}</span>
                        <span>{countWorkflowSteps(workflow)} steps</span>
                      </CardContent>
                    </Card>
                  </button>
                );
              })
            )}
          </div>
        </ScrollArea>

        <div className="min-h-0">
          {selectedWorkflow ? (
            <WorkflowEditor
              workflow={selectedWorkflow}
              maxBranches={maxBranches}
              maxWorkflowAgents={maxWorkflowAgents}
              onDelete={() => remove(selectedWorkflow.id)}
              onUpdate={(patch) => update(selectedWorkflow.id, patch)}
            />
          ) : (
            <Card className="h-full min-h-[320px] justify-center border-dashed shadow-none">
              <CardHeader>
                <CardTitle>Select a workflow card</CardTitle>
                <CardDescription>
                  Configure the goal and expected output, then let the main agent
                  orchestrate the rest inside a constrained loop.
                </CardDescription>
              </CardHeader>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function WorkflowEditor({
  workflow,
  maxBranches,
  maxWorkflowAgents,
  onDelete,
  onUpdate,
}: {
  workflow: Workflow;
  maxBranches: number;
  maxWorkflowAgents: number;
  onDelete: () => void;
  onUpdate: (patch: Partial<Workflow>) => void;
}) {
  const { brainPlan, isLoading: brainLoading } = useBrainPlan(
    workflow.goal.trim().length > 0
      ? buildBrainPlanPayload(workflow)
      : null,
  );
  const missingInputs = new Set(brainPlan?.execution_contract.missing_inputs ?? []);
  const evidenceBlocked = missingInputs.has("evidence");
  const factorCandidatesBlocked = missingInputs.has("factor_candidates");
  const riskLimitsBlocked = missingInputs.has("risk_limits");
  const presetSuggestion = brainPlan
    ? deriveWorkflowPreset(workflow, brainPlan.execution_contract.template)
    : null;
  const builderActionModel = useMemo(
    () => brainPlan?.builder_action_model ?? null,
    [brainPlan],
  );
  const presetAlignment =
    presetSuggestion ? evaluatePresetAlignment(workflow, presetSuggestion.patch) : null;
  const applyBuilderAction = (action: BrainBuilderAction) => {
    const patch = normalizeWorkflowPatch(workflow, action.patch);
    if (Object.keys(patch).length === 0) {
      return;
    }
    onUpdate(patch);
  };
  const applyAllBuilderActions = () => {
    if (!builderActionModel) {
      return;
    }
    const patch = normalizeWorkflowPatch(workflow, builderActionModel.apply_all_patch);
    if (Object.keys(patch).length === 0) {
      return;
    }
    onUpdate(patch);
  };
  const focusMissingInput = (input: string) => {
    const targetId = missingInputFieldId(input);
    if (!targetId) {
      return;
    }
    const element = document.getElementById(targetId);
    if (!element) {
      return;
    }
    element.scrollIntoView({ behavior: "smooth", block: "center" });
    if (
      element instanceof HTMLInputElement ||
      element instanceof HTMLTextAreaElement
    ) {
      element.focus();
    }
  };

  return (
    <ScrollArea className="h-full rounded-xl border">
      <div className="space-y-5 p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-semibold">{workflow.title}</h3>
              <Badge variant="secondary">{workflow.mode}</Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Keep the config minimal: goal, result, participating agents, and
              failure policy. The main agent should own decomposition.
            </p>
          </div>
          <Button size="sm" variant="ghost" onClick={onDelete}>
            <Trash2Icon />
            Delete
          </Button>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <LabeledField label="Title">
            <Input
              value={workflow.title}
              onChange={(event) => onUpdate({ title: event.target.value })}
            />
          </LabeledField>
          <LabeledField label="Status">
            <Select
              value={workflow.status}
              onValueChange={(value) =>
                onUpdate({ status: value as Workflow["status"] })
              }
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(STATUS_LABEL).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </LabeledField>
        </div>

        <LabeledField label="Goal">
          <Textarea
            value={workflow.goal}
            onChange={(event) => onUpdate({ goal: event.target.value })}
            placeholder="What should the main agent achieve?"
          />
        </LabeledField>

        <LabeledField
          fieldId="workflow-expected-output"
          label="Expected Output"
          remediationHint={
            evidenceBlocked
              ? "Brain is blocked on evidence. Add the expected deliverable, sample output, or validation target here."
              : undefined
          }
          tone={evidenceBlocked ? "blocked" : "default"}
        >
          <Textarea
            id="workflow-expected-output"
            value={workflow.expectedOutput}
            onChange={(event) => onUpdate({ expectedOutput: event.target.value })}
            placeholder="What should the final result look like?"
          />
        </LabeledField>

        <div className="grid gap-4 md:grid-cols-2">
          <LabeledField label="Brain Mode">
            <Select
              value={workflow.brainConfig.preferredMode}
              onValueChange={(value) =>
                onUpdate({
                  brainConfig: {
                    ...workflow.brainConfig,
                    preferredMode:
                      value as Workflow["brainConfig"]["preferredMode"],
                  },
                })
              }
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="plan">Plan</SelectItem>
                <SelectItem value="research">Research</SelectItem>
                <SelectItem value="quant">Quant</SelectItem>
                <SelectItem value="policy">Policy</SelectItem>
              </SelectContent>
            </Select>
          </LabeledField>
          <LabeledField
            fieldId="workflow-risk-limits"
            label="Risk Limits"
            remediationHint={
              riskLimitsBlocked
                ? "Brain quant execution is blocked until explicit risk guardrails are declared."
                : undefined
            }
            tone={riskLimitsBlocked ? "blocked" : "default"}
          >
            <Input
              id="workflow-risk-limits"
              value={workflow.brainConfig.riskLimits.join(", ")}
              onChange={(event) =>
                onUpdate({
                  brainConfig: {
                    ...workflow.brainConfig,
                    riskLimits: splitCommaSeparated(event.target.value),
                  },
                })
              }
              placeholder="max drawdown 8%, no leverage, sector cap 20%"
            />
          </LabeledField>
        </div>

        <LabeledField
          fieldId="workflow-factor-candidates"
          label="Factor Candidates"
          remediationHint={
            factorCandidatesBlocked
              ? "Brain quant execution is blocked until factor candidates are listed."
              : undefined
          }
          tone={factorCandidatesBlocked ? "blocked" : "default"}
        >
          <Input
            id="workflow-factor-candidates"
            value={workflow.brainConfig.factorCandidates.join(", ")}
            onChange={(event) =>
              onUpdate({
                brainConfig: {
                  ...workflow.brainConfig,
                  factorCandidates: splitCommaSeparated(event.target.value),
                },
              })
            }
            placeholder="momentum_20d, quality_rank, volatility_regime"
          />
        </LabeledField>

        <LabeledField label="Memory Hints">
          <Textarea
            value={workflow.brainConfig.memoryHints.join("\n")}
            onChange={(event) =>
              onUpdate({
                brainConfig: {
                  ...workflow.brainConfig,
                  memoryHints: event.target.value
                    .split("\n")
                    .map((line) => line.trim())
                    .filter(Boolean),
                },
              })
            }
            placeholder="Previous factor drift in small caps&#10;Avoid overnight leverage spikes"
          />
        </LabeledField>

        <BrainPlanPreview
          builderActionModel={builderActionModel}
          brainLoading={brainLoading}
          brainPlan={brainPlan}
          onApplyAction={applyBuilderAction}
          onApplyAllActions={applyAllBuilderActions}
          onResolveMissingInput={focusMissingInput}
          onApplyPreset={
            presetSuggestion ? () => onUpdate(presetSuggestion.patch) : undefined
          }
          presetAlignment={presetAlignment}
          presetSummary={presetSuggestion?.summary}
        />

        <LabeledField label="Participating Agents">
          <div className="space-y-2">
            <Input
              value={workflow.agents.join(", ")}
              onChange={(event) =>
                onUpdate({
                  agents: splitCommaSeparated(event.target.value).slice(
                    0,
                    maxWorkflowAgents,
                  ),
                })
              }
              placeholder="lead_agent, researcher, coder, reviewer"
            />
            <p className="text-xs text-muted-foreground">
              Recommended ceiling: {maxWorkflowAgents} agents per workflow on
              this host. Keep `task` and `group` compact unless parallelism is essential.
            </p>
          </div>
        </LabeledField>

        <Separator />

        {workflow.mode === "task" && (
          <LabeledField label="Task Route">
            <Input
              value={workflow.route.join(" -> ")}
              onChange={(event) =>
                onUpdate({
                  route: event.target.value
                    .split("->")
                    .map((part) => part.trim())
                    .filter(Boolean),
                } as Partial<Workflow>)
              }
              placeholder="lead_agent -> executor -> reviewer -> lead_agent"
            />
          </LabeledField>
        )}

        {workflow.mode === "branch" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium">Branches</div>
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  workflow.branches.length < maxBranches &&
                  onUpdate({
                    branches: [
                      ...workflow.branches,
                      {
                        id: `branch-${Date.now()}`,
                        agentName: "analyst",
                        responsibility: "Add another perspective",
                      },
                    ],
                  } as Partial<Workflow>)
                }
              >
                Add branch
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Recommended parallel branch ceiling: {maxBranches}. Extra branches
              increase local-model memory pressure and retry noise.
            </p>
            {workflow.branches.map((branch) => (
              <div
                className="grid gap-2 rounded-lg border p-3 md:grid-cols-[160px_minmax(0,1fr)]"
                key={branch.id}
              >
                <Input
                  value={branch.agentName}
                  onChange={(event) =>
                    onUpdate({
                      branches: workflow.branches.map((item) =>
                        item.id === branch.id
                          ? { ...item, agentName: event.target.value }
                          : item,
                      ),
                    } as Partial<Workflow>)
                  }
                />
                <Input
                  value={branch.responsibility}
                  onChange={(event) =>
                    onUpdate({
                      branches: workflow.branches.map((item) =>
                        item.id === branch.id
                          ? { ...item, responsibility: event.target.value }
                          : item,
                      ),
                    } as Partial<Workflow>)
                  }
                />
              </div>
            ))}
          </div>
        )}

        {workflow.mode === "group" && (
          <LabeledField label="Collaboration Style">
            <Select
              value={workflow.collaborationStyle}
              onValueChange={(value) =>
                onUpdate({
                  collaborationStyle: value as typeof workflow.collaborationStyle,
                } as Partial<Workflow>)
              }
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="fast">Fast convergence</SelectItem>
                <SelectItem value="balanced">Balanced discussion</SelectItem>
                <SelectItem value="deep_review">Deep review</SelectItem>
              </SelectContent>
            </Select>
          </LabeledField>
        )}

        <Separator />

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <LabeledField label="Max Step Attempts">
            <Input
              min={1}
              type="number"
              value={String(workflow.failurePolicy.maxStepAttempts)}
              onChange={(event) =>
                onUpdate({
                  failurePolicy: {
                    ...workflow.failurePolicy,
                    maxStepAttempts: Number(event.target.value) || 1,
                  },
                })
              }
            />
          </LabeledField>
          <LabeledField label="Max No-Progress Rounds">
            <Input
              min={1}
              type="number"
              value={String(workflow.failurePolicy.maxNoProgressRounds)}
              onChange={(event) =>
                onUpdate({
                  failurePolicy: {
                    ...workflow.failurePolicy,
                    maxNoProgressRounds: Number(event.target.value) || 1,
                  },
                })
              }
            />
          </LabeledField>
          <LabeledField label="Max Total Steps">
            <Input
              min={1}
              type="number"
              value={String(workflow.failurePolicy.maxTotalSteps)}
              onChange={(event) =>
                onUpdate({
                  failurePolicy: {
                    ...workflow.failurePolicy,
                    maxTotalSteps: Number(event.target.value) || 1,
                  },
                })
              }
            />
          </LabeledField>
          <LabeledField label="On Final Failure">
            <Select
              value={workflow.failurePolicy.onFinalFailure}
              onValueChange={(value) =>
                onUpdate({
                  failurePolicy: {
                    ...workflow.failurePolicy,
                    onFinalFailure:
                      value as Workflow["failurePolicy"]["onFinalFailure"],
                  },
                })
              }
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="stop">Stop</SelectItem>
                <SelectItem value="fallback">Fallback</SelectItem>
                <SelectItem value="ask_user">Ask user</SelectItem>
              </SelectContent>
            </Select>
          </LabeledField>
        </div>
      </div>
    </ScrollArea>
  );
}

function BrainPlanPreview({
  builderActionModel,
  brainPlan,
  brainLoading,
  onApplyAction,
  onApplyAllActions,
  onResolveMissingInput,
  onApplyPreset,
  presetAlignment,
  presetSummary,
}: {
  builderActionModel?: BrainBuilderActionModel | null;
  brainPlan:
    | ReturnType<typeof useBrainPlan>["brainPlan"]
    | undefined;
  brainLoading: boolean;
  onApplyAction?: (action: BrainBuilderAction) => void;
  onApplyAllActions?: () => void;
  onResolveMissingInput?: (input: string) => void;
  onApplyPreset?: () => void;
  presetAlignment?: {
    aligned: boolean;
    reasons: string[];
  } | null;
  presetSummary?: string;
}) {
  if (brainLoading) {
    return (
      <Card className="gap-3 py-4 shadow-none">
        <CardHeader className="px-4">
          <CardTitle className="text-sm">Brain Fusion Plan</CardTitle>
          <CardDescription>
            Generating strategy graph and arbitration hints.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (!brainPlan) {
    return null;
  }

  const validation = brainPlan.strategy_validation;
  const arbitrations = brainPlan.strategy_graph.arbitrations;
  const executionContract = brainPlan.execution_contract;
  const blockingInputs = executionContract.missing_inputs.join(", ");
  const requiredCheckpointCount = executionContract.checkpoints.filter(
    (checkpoint) => checkpoint.required,
  ).length;
  const readyCheckpointCount = executionContract.checkpoints.filter(
    (checkpoint) => checkpoint.status === "ready",
  ).length;

  return (
    <Card className="gap-3 py-4 shadow-none">
      <CardHeader className="px-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-sm">Brain Fusion Plan</CardTitle>
          <Badge variant={validation.valid ? "secondary" : "destructive"}>
            {validation.valid ? "Validated" : "Needs fixes"}
          </Badge>
        </div>
        <CardDescription>{brainPlan.plan.summary}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 px-4 text-xs">
        <div className="grid gap-3 md:grid-cols-4">
          <div className="rounded-lg border bg-muted/20 p-3">
            <div className="font-medium text-foreground">Execution Order</div>
            <div className="mt-1 text-muted-foreground">
              {validation.execution_order.length > 0
                ? validation.execution_order.join(" -> ")
                : "No validated execution order yet"}
            </div>
          </div>
          <div className="rounded-lg border bg-muted/20 p-3">
            <div className="font-medium text-foreground">Arbitration</div>
            <div className="mt-1 text-muted-foreground">
              {arbitrations.length > 0
                ? arbitrations
                    .map((item) => `${item.output_name}: ${item.mode}`)
                    .join("; ")
                : "No shared-output arbitration required"}
            </div>
          </div>
          <div className="rounded-lg border bg-muted/20 p-3">
            <div className="font-medium text-foreground">Decision</div>
            <div className="mt-1 text-muted-foreground">
              {brainPlan.decision.recommendation}
            </div>
          </div>
          <div className="rounded-lg border bg-muted/20 p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="font-medium text-foreground">Execution Contract</div>
              <Badge
                variant={
                  executionContract.readiness === "blocked"
                    ? "destructive"
                    : executionContract.readiness === "ready"
                      ? "secondary"
                      : "outline"
                }
              >
                {formatExecutionReadiness(executionContract.readiness)}
              </Badge>
            </div>
            <div className="mt-1 text-muted-foreground">
              {formatExecutionTemplate(executionContract.template)}
            </div>
            <div className="mt-1 text-muted-foreground">
              Runtime mode: {executionContract.suggested_runtime_mode}
            </div>
            <div className="mt-1 text-muted-foreground">
              Workflow mode: {formatWorkflowMode(executionContract.suggested_workflow_mode)}
            </div>
          </div>
        </div>

        {presetSummary && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-muted/10 p-3">
            <div className="space-y-1">
              <div className="flex items-center gap-2 font-medium text-foreground">
                <SparklesIcon className="size-4" />
                Workflow Preset
                {presetAlignment && (
                  <Badge variant={presetAlignment.aligned ? "secondary" : "outline"}>
                    {presetAlignment.aligned ? "Aligned" : "Drifted"}
                  </Badge>
                )}
              </div>
              <div className="text-muted-foreground">{presetSummary}</div>
              {presetAlignment && presetAlignment.reasons.length > 0 && (
                <div className="text-muted-foreground">
                  {presetAlignment.reasons.join("; ")}
                </div>
              )}
            </div>
            <Button size="sm" variant="outline" onClick={onApplyPreset} type="button">
              {presetAlignment?.aligned ? "Re-apply preset" : "Apply preset"}
            </Button>
          </div>
        )}

        {builderActionModel && (
          <div className="space-y-3 rounded-lg border bg-muted/10 p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="space-y-1">
                <div className="flex items-center gap-2 font-medium text-foreground">
                  <ListTodoIcon className="size-4" />
                  Builder Action Model
                </div>
                <div className="text-muted-foreground">{builderActionModel.summary}</div>
              </div>
              {builderActionModel.auto_actions.length > 1 ? (
                <Button size="sm" variant="outline" onClick={onApplyAllActions} type="button">
                  Apply all actions
                </Button>
              ) : null}
            </div>

            {builderActionModel.auto_actions.length > 0 ? (
              <div className="grid gap-2 md:grid-cols-2">
                {builderActionModel.auto_actions.map((action) => (
                  <div className="rounded-md border bg-background/80 p-3" key={action.id}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="font-medium text-foreground">{action.title}</div>
                      <Badge variant="secondary">Auto</Badge>
                    </div>
                    <div className="mt-1 text-muted-foreground">{action.description}</div>
                    <div className="mt-3">
                      <Button size="sm" variant="outline" onClick={() => onApplyAction?.(action)} type="button">
                        Apply action
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}

            {builderActionModel.manual_actions.length > 0 ? (
              <div className="space-y-2">
                <div className="font-medium text-foreground">Manual follow-ups</div>
                <div className="grid gap-2 md:grid-cols-2">
                  {builderActionModel.manual_actions.map((action) => (
                    <div className="rounded-md border bg-background/80 p-3" key={action.id}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="font-medium text-foreground">{action.title}</div>
                        <Badge variant="outline">Manual</Badge>
                      </div>
                      <div className="mt-1 text-muted-foreground">{action.description}</div>
                      {action.target_field ? (
                        <div className="mt-3">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => onResolveMissingInput?.(action.target_field!)}
                            type="button"
                          >
                            Open field
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        )}

        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border bg-muted/20 p-3">
            <div className="font-medium text-foreground">Required Inputs</div>
            <div className="mt-1 text-muted-foreground">
              {executionContract.required_inputs.length > 0
                ? executionContract.required_inputs.join(", ")
                : "No special inputs required"}
            </div>
          </div>
          <div className="rounded-lg border bg-muted/20 p-3">
            <div className="font-medium text-foreground">Missing Inputs</div>
            <div className="mt-1 text-muted-foreground">
              {blockingInputs.length > 0 ? blockingInputs : "No blocking inputs"}
            </div>
          </div>
          <div className="rounded-lg border bg-muted/20 p-3">
            <div className="font-medium text-foreground">Approval Checkpoints</div>
            <div className="mt-1 text-muted-foreground">
              {executionContract.checkpoints.length > 0
                ? `${readyCheckpointCount}/${requiredCheckpointCount} required checkpoints ready`
                : "No explicit approval gates yet"}
            </div>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-lg border bg-muted/20 p-3">
            <div className="font-medium text-foreground">Current Phase</div>
            <div className="mt-1 text-muted-foreground">
              {formatContractPhase(executionContract.current_phase)}
            </div>
          </div>
          <div className="rounded-lg border bg-muted/20 p-3">
            <div className="font-medium text-foreground">Next Owner</div>
            <div className="mt-1 text-muted-foreground">
              {formatNextOwner(executionContract.next_owner)}
            </div>
          </div>
        </div>

        {executionContract.quant_backtest && (
          <div className="space-y-2 rounded-lg border bg-muted/10 p-3">
            <div className="font-medium text-foreground">Quant Backtest Contract</div>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-md border bg-background/80 p-3">
                <div className="font-medium text-foreground">Factors</div>
                <div className="mt-1 text-muted-foreground">
                  {executionContract.quant_backtest.factor_count} candidate(s)
                </div>
              </div>
              <div className="rounded-md border bg-background/80 p-3">
                <div className="font-medium text-foreground">Evidence</div>
                <div className="mt-1 text-muted-foreground">
                  {executionContract.quant_backtest.evidence_count} item(s)
                </div>
              </div>
              <div className="rounded-md border bg-background/80 p-3">
                <div className="font-medium text-foreground">Risk Guardrails</div>
                <div className="mt-1 text-muted-foreground">
                  {executionContract.quant_backtest.risk_guardrail_count} declared
                </div>
              </div>
              <div className="rounded-md border bg-background/80 p-3">
                <div className="font-medium text-foreground">Next Action</div>
                <div className="mt-1 text-muted-foreground">
                  {formatQuantNextAction(executionContract.quant_backtest.next_action)}
                </div>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-md border bg-background/80 p-3">
                <div className="font-medium text-foreground">Suggested Universe</div>
                <div className="mt-1 text-muted-foreground">
                  {formatSuggestedUniverse(
                    executionContract.quant_backtest.suggested_universe,
                  )}
                </div>
              </div>
              <div className="rounded-md border bg-background/80 p-3">
                <div className="font-medium text-foreground">Approval Handoff</div>
                <div className="mt-1 text-muted-foreground">
                  {formatApprovalHandoff(
                    executionContract.quant_backtest.approval_handoff,
                  )}
                </div>
              </div>
              <div className="rounded-md border bg-background/80 p-3">
                <div className="font-medium text-foreground">Execution Phase</div>
                <div className="mt-1 text-muted-foreground">
                  {formatExecutionPhase(
                    executionContract.quant_backtest.execution_phase,
                  )}
                </div>
              </div>
              <div className="rounded-md border bg-background/80 p-3 md:col-span-2">
                <div className="font-medium text-foreground">Factor Candidates</div>
                <div className="mt-1 text-muted-foreground">
                  {executionContract.quant_backtest.factor_candidates.length > 0
                    ? executionContract.quant_backtest.factor_candidates.join(", ")
                    : "No factor candidates declared yet"}
                </div>
              </div>
            </div>
            <div className="rounded-md border bg-background/80 p-3">
              <div className="font-medium text-foreground">Risk Guardrails</div>
              <div className="mt-1 text-muted-foreground">
                {executionContract.quant_backtest.risk_guardrails.length > 0
                  ? executionContract.quant_backtest.risk_guardrails.join(", ")
                  : "No explicit risk guardrails declared yet"}
              </div>
            </div>
          </div>
        )}

        {executionContract.missing_inputs.length > 0 && (
          <div className="space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
            <div className="font-medium text-foreground">Remediation</div>
            <div className="space-y-1 text-muted-foreground">
              {executionContract.missing_inputs.map((input) => (
                <button
                  className="block w-full rounded-md border border-transparent px-2 py-2 text-left transition-colors hover:border-amber-500/30 hover:bg-background/60"
                  key={input}
                  onClick={() => onResolveMissingInput?.(input)}
                  type="button"
                >
                  {formatMissingInputGuidance(input)}
                </button>
              ))}
            </div>
          </div>
        )}

        {executionContract.checkpoints.length > 0 && (
          <div className="space-y-2 rounded-lg border bg-muted/10 p-3">
            <div className="font-medium text-foreground">Checkpoint Status</div>
            <div className="grid gap-2 md:grid-cols-3">
              {executionContract.checkpoints.map((checkpoint) => (
                <div className="rounded-md border bg-background/80 p-3" key={checkpoint.id}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-foreground">{checkpoint.title}</div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">
                        {formatCheckpointPhase(checkpoint.phase)}
                      </Badge>
                      <Badge
                        variant={
                          checkpoint.status === "blocked"
                            ? "destructive"
                            : checkpoint.status === "ready"
                              ? "secondary"
                              : "outline"
                        }
                      >
                        {formatCheckpointStatus(checkpoint.status)}
                      </Badge>
                    </div>
                  </div>
                  {checkpoint.reason && (
                    <div className="mt-1 text-muted-foreground">{checkpoint.reason}</div>
                  )}
                  <div className="mt-1 text-muted-foreground">
                    Owner: {formatCheckpointOwner(checkpoint.owner_role)}
                  </div>
                  <div className="mt-1 text-muted-foreground">
                    Handoff: {formatCheckpointHandoff(checkpoint.handoff_kind)}
                  </div>
                  {checkpoint.next_step && (
                    <div className="mt-1 text-muted-foreground">
                      Next: {checkpoint.next_step}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {executionContract.notes.length > 0 && (
          <div className="space-y-2 rounded-lg border bg-muted/10 p-3">
            <div className="font-medium text-foreground">Execution Notes</div>
            <div className="space-y-1 text-muted-foreground">
              {executionContract.notes.map((note) => (
                <div key={note}>{note}</div>
              ))}
            </div>
          </div>
        )}

        {(validation.errors.length > 0 || validation.warnings.length > 0) && (
          <div className="space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
            <div className="flex items-center gap-2 font-medium text-foreground">
              <ShieldAlertIcon className="size-4" />
              Fusion Guardrails
            </div>
            {validation.errors.map((error) => (
              <div className="text-red-300" key={error}>
                {error}
              </div>
            ))}
            {validation.warnings.map((warning) => (
              <div className="text-muted-foreground" key={warning}>
                {warning}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function formatExecutionTemplate(template: string) {
  switch (template) {
    case "quant_backtest":
      return "Quant backtest";
    case "research_review":
      return "Research review";
    case "policy_review":
      return "Policy review";
    default:
      return "Generic analysis";
  }
}

function formatExecutionReadiness(readiness: string) {
  switch (readiness) {
    case "ready":
      return "Ready";
    case "blocked":
      return "Blocked";
    default:
      return "Review required";
  }
}

function formatWorkflowMode(mode: string) {
  switch (mode) {
    case "branch":
      return "Branch";
    case "group":
      return "Group";
    default:
      return "Task";
  }
}

function formatContractPhase(phase: string) {
  switch (phase) {
    case "inputs":
      return "Inputs";
    case "review":
      return "Review";
    case "approval":
      return "Approval";
    case "execution":
      return "Execution";
    default:
      return "Plan";
  }
}

function formatCheckpointStatus(status: string) {
  switch (status) {
    case "ready":
      return "Ready";
    case "blocked":
      return "Blocked";
    default:
      return "Pending";
  }
}

function formatNextOwner(owner: string) {
  switch (owner) {
    case "risk_reviewer":
      return "Risk reviewer";
    case "research_reviewer":
      return "Research reviewer";
    case "policy_reviewer":
      return "Policy reviewer";
    case "system":
      return "System";
    default:
      return "Operator";
  }
}

function formatMissingInputGuidance(input: string) {
  switch (input) {
    case "evidence":
      return "Open `Expected Output` and add a concrete deliverable, sample result, or evidence target.";
    case "factor_candidates":
      return "Open `Factor Candidates` and list the ranking signals or hypotheses to test.";
    case "risk_limits":
      return "Open `Risk Limits` and declare explicit drawdown, leverage, or exposure guardrails.";
    default:
      return `Add the missing input: ${input}.`;
  }
}

function formatQuantNextAction(nextAction: string) {
  switch (nextAction) {
    case "prepare_backtest":
      return "Prepare bounded backtest";
    case "manual_review":
      return "Escalate to manual review";
    default:
      return "Collect missing inputs";
  }
}

function formatSuggestedUniverse(universe: string) {
  switch (universe) {
    case "broad_market":
      return "Broad market";
    case "constrained":
      return "Constrained by declared guardrails";
    default:
      return "Universe not defined yet";
  }
}

function formatApprovalHandoff(handoff: string) {
  switch (handoff) {
    case "operator_review":
      return "Operator review";
    case "risk_signoff":
      return "Risk signoff";
    default:
      return "Not ready for handoff";
  }
}

function formatExecutionPhase(phase: string) {
  switch (phase) {
    case "review_inputs":
      return "Review inputs";
    case "await_approval":
      return "Await approval";
    case "prepare_execution":
      return "Prepare execution";
    default:
      return "Collect inputs";
  }
}

function formatCheckpointPhase(phase: string) {
  switch (phase) {
    case "inputs":
      return "Inputs";
    case "approval":
      return "Approval";
    case "execution":
      return "Execution";
    default:
      return "Review";
  }
}

function formatCheckpointOwner(owner: string) {
  switch (owner) {
    case "risk_reviewer":
      return "Risk reviewer";
    case "research_reviewer":
      return "Research reviewer";
    case "policy_reviewer":
      return "Policy reviewer";
    default:
      return "Operator";
  }
}

function formatCheckpointHandoff(handoff: string) {
  switch (handoff) {
    case "risk_signoff":
      return "Risk signoff";
    case "evidence_review":
      return "Evidence review";
    case "policy_signoff":
      return "Policy signoff";
    default:
      return "Operator review";
  }
}

function normalizeWorkflowPatch(
  workflow: Workflow,
  input: Record<string, unknown>,
): Partial<Workflow> {
  const patch: Partial<Workflow> = {};

  if (input.mode === "task" || input.mode === "branch" || input.mode === "group") {
    patch.mode = input.mode;
  }
  if (Array.isArray(input.agents)) {
    patch.agents = input.agents.filter((item): item is string => typeof item === "string");
  }
  if (Array.isArray(input.route)) {
    (patch as Partial<Workflow> & { route?: string[] }).route = input.route.filter(
      (item): item is string => typeof item === "string",
    );
  }
  if (Array.isArray(input.branches)) {
    (patch as Partial<Workflow> & {
      branches?: Array<{ id: string; agentName: string; responsibility: string }>;
    }).branches = input.branches
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
      .map((item, index) => ({
        id: typeof item.id === "string" ? item.id : `brain-branch-${index + 1}`,
        agentName: typeof item.agentName === "string" ? item.agentName : "researcher",
        responsibility:
          typeof item.responsibility === "string"
            ? item.responsibility
            : "Add another perspective",
      }));
  }
  if (
    input.collaborationStyle === "fast"
    || input.collaborationStyle === "balanced"
    || input.collaborationStyle === "deep_review"
  ) {
    (patch as Partial<Workflow> & {
      collaborationStyle?: "fast" | "balanced" | "deep_review";
    }).collaborationStyle = input.collaborationStyle;
  }

  const brainConfig = input.brainConfig;
  if (brainConfig && typeof brainConfig === "object") {
    const candidate = brainConfig as Record<string, unknown>;
    const preferredMode = candidate.preferredMode;
    if (
      preferredMode === "plan"
      || preferredMode === "research"
      || preferredMode === "quant"
      || preferredMode === "policy"
    ) {
      patch.brainConfig = {
        preferredMode,
        factorCandidates: workflow.brainConfig.factorCandidates,
        riskLimits: workflow.brainConfig.riskLimits,
        memoryHints: workflow.brainConfig.memoryHints,
      };
    }
  }

  const failurePolicy = input.failurePolicy;
  if (failurePolicy && typeof failurePolicy === "object") {
    const candidate = failurePolicy as Record<string, unknown>;
    const onFinalFailure = candidate.onFinalFailure;
    if (
      (typeof candidate.maxStepAttempts === "number" || typeof candidate.maxNoProgressRounds === "number" || typeof candidate.maxTotalSteps === "number")
      && (onFinalFailure === "stop" || onFinalFailure === "fallback" || onFinalFailure === "ask_user")
    ) {
      patch.failurePolicy = {
        maxStepAttempts:
          typeof candidate.maxStepAttempts === "number"
            ? candidate.maxStepAttempts
            : workflow.failurePolicy.maxStepAttempts,
        maxNoProgressRounds:
          typeof candidate.maxNoProgressRounds === "number"
            ? candidate.maxNoProgressRounds
            : workflow.failurePolicy.maxNoProgressRounds,
        maxTotalSteps:
          typeof candidate.maxTotalSteps === "number"
            ? candidate.maxTotalSteps
            : workflow.failurePolicy.maxTotalSteps,
        onFinalFailure,
      };
    }
  }

  return patch;
}

function missingInputFieldId(input: string) {
  switch (input) {
    case "evidence":
      return "workflow-expected-output";
    case "factor_candidates":
      return "workflow-factor-candidates";
    case "risk_limits":
      return "workflow-risk-limits";
    default:
      return null;
  }
}

function deriveWorkflowPreset(
  workflow: Workflow,
  template: BrainExecutionContract["template"],
) {
  switch (template) {
    case "quant_backtest":
      return {
        summary:
          "Switch to a task workflow tuned for bounded quant exploration with explicit review return.",
        patch: {
          mode: "task" as const,
          title: workflow.title.startsWith("Quant:")
            ? workflow.title
            : `Quant: ${workflow.title}`,
          agents: ["lead_agent", "quant_researcher", "risk_reviewer", "lead_agent"],
          route: [
            "lead_agent",
            "quant_researcher",
            "risk_reviewer",
            "lead_agent",
          ],
          brainConfig: {
            ...workflow.brainConfig,
            preferredMode: "quant" as const,
          },
        } satisfies Partial<Workflow>,
      };
    case "research_review":
      return {
        summary:
          "Switch to a branch workflow for parallel research and implementation review before synthesis.",
        patch: {
          mode: "branch" as const,
          title: workflow.title.startsWith("Research:")
            ? workflow.title
            : `Research: ${workflow.title}`,
          agents: ["lead_agent", "researcher", "coder", "reviewer"],
          branches: [
            {
              id: `branch-research`,
              agentName: "researcher",
              responsibility: "Validate evidence and expand the problem space",
            },
            {
              id: `branch-implementation`,
              agentName: "coder",
              responsibility: "Draft a candidate implementation or response",
            },
          ],
          brainConfig: {
            ...workflow.brainConfig,
            preferredMode: "research" as const,
          },
        } satisfies Partial<Workflow>,
      };
    case "policy_review":
      return {
        summary:
          "Switch to a group workflow for policy discussion, constraint review, and supervised consensus.",
        patch: {
          mode: "group" as const,
          title: workflow.title.startsWith("Policy:")
            ? workflow.title
            : `Policy: ${workflow.title}`,
          agents: ["lead_agent", "policy_reviewer", "domain_owner", "reviewer"],
          collaborationStyle: "deep_review" as const,
          brainConfig: {
            ...workflow.brainConfig,
            preferredMode: "policy" as const,
          },
        } satisfies Partial<Workflow>,
      };
    default:
      return {
        summary:
          "Keep a task workflow for linear analysis with an explicit handoff back to the lead agent.",
        patch: {
          mode: "task" as const,
          route: ["lead_agent", "executor", "reviewer", "lead_agent"],
          brainConfig: {
            ...workflow.brainConfig,
            preferredMode: "plan" as const,
          },
        } satisfies Partial<Workflow>,
      };
  }
}

function evaluatePresetAlignment(workflow: Workflow, patch: Partial<Workflow>) {
  const reasons: string[] = [];

  if (patch.mode && workflow.mode !== patch.mode) {
    reasons.push(`mode is ${workflow.mode}, preset expects ${patch.mode}`);
  }

  if (patch.brainConfig?.preferredMode) {
    if (workflow.brainConfig.preferredMode !== patch.brainConfig.preferredMode) {
      reasons.push(
        `brain mode is ${workflow.brainConfig.preferredMode}, preset expects ${patch.brainConfig.preferredMode}`,
      );
    }
  }

  if ("route" in patch && patch.route && workflow.mode === "task") {
    if (workflow.route.join(" -> ") !== patch.route.join(" -> ")) {
      reasons.push("task route no longer matches the preset");
    }
  }

  if ("branches" in patch && patch.branches && workflow.mode === "branch") {
    const currentBranches = workflow.branches.map(
      (branch) => `${branch.agentName}:${branch.responsibility}`,
    );
    const presetBranches = patch.branches.map(
      (branch) => `${branch.agentName}:${branch.responsibility}`,
    );
    if (currentBranches.join("|") !== presetBranches.join("|")) {
      reasons.push("branch layout no longer matches the preset");
    }
  }

  if ("collaborationStyle" in patch && patch.collaborationStyle && workflow.mode === "group") {
    if (workflow.collaborationStyle !== patch.collaborationStyle) {
      reasons.push(
        `collaboration style is ${workflow.collaborationStyle}, preset expects ${patch.collaborationStyle}`,
      );
    }
  }

  if (patch.agents) {
    if (workflow.agents.join("|") !== patch.agents.join("|")) {
      reasons.push("participating agents no longer match the preset");
    }
  }

  return {
    aligned: reasons.length === 0,
    reasons:
      reasons.length > 0 ? reasons : ["Current workflow still matches Brain guidance."],
  };
}

function RuntimeGuide() {
  const { runtime, isLoading } = useRuntimeCapabilities();

  if (isLoading || !runtime) {
    return null;
  }

  const defaultModel =
    runtime.models.find((model) => model.name === runtime.default_model) ??
    runtime.models[0];

  return (
    <Card className="gap-3 py-4 shadow-none">
      <CardHeader className="px-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-sm">Runtime Guardrails</CardTitle>
          <Badge
            variant={
              runtime.runtime_status.memory_guard_state === "tight"
                ? "destructive"
                : "secondary"
            }
          >
            Memory {runtime.runtime_status.memory_guard_state}
          </Badge>
        </div>
        <CardDescription>
          The planner is constrained by actual host limits, not free-form canvas rules.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 px-4 text-xs text-muted-foreground md:grid-cols-3">
        <div className="rounded-lg border bg-muted/20 p-3">
          <div className="font-medium text-foreground">Agent budget</div>
          <div className="mt-1">
            {runtime.agent_limits.max_active_subagents_per_thread} active per thread,
            {" "}
            {runtime.agent_limits.max_total_subagents_per_thread} total delegated tasks,
            {" "}
            {runtime.agent_limits.max_concurrent_subagents} global concurrent.
          </div>
        </div>
        <div className="rounded-lg border bg-muted/20 p-3">
          <div className="font-medium text-foreground">Memory guard</div>
          <div className="mt-1">
            {runtime.runtime_status.available_memory_gb != null
              ? `${runtime.runtime_status.available_memory_gb.toFixed(1)} GiB available now`
              : "Host memory unavailable"}
          </div>
          <div className="mt-1">
            Reserve floor {runtime.agent_limits.min_available_memory_gb} GiB, estimate
            {" "}
            {runtime.agent_limits.estimated_memory_per_subagent_gb} GiB per delegated worker.
          </div>
        </div>
        <div className="rounded-lg border bg-muted/20 p-3">
          <div className="font-medium text-foreground">Model failover</div>
          <div className="mt-1">
            {defaultModel
              ? `${defaultModel.display_name ?? defaultModel.name} ${
                  defaultModel.fallback_models.length > 0
                    ? `-> ${defaultModel.fallback_models.join(" -> ")}`
                    : "(no fallback chain configured)"
                }`
              : "No model metadata available"}
          </div>
          <div className="mt-1">
            Token overflow, timeout, 429, and network failures will trigger ordered backup models.
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function LabeledField({
  fieldId,
  label,
  children,
  remediationHint,
  tone = "default",
}: {
  fieldId?: string;
  label: string;
  children: React.ReactNode;
  remediationHint?: string;
  tone?: "default" | "blocked";
}) {
  return (
    <label className="space-y-2" htmlFor={fieldId}>
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-sm font-medium">{label}</div>
        {tone === "blocked" && <Badge variant="destructive">Required by Brain</Badge>}
      </div>
      {remediationHint && (
        <div
          className={cn(
            "text-xs",
            tone === "blocked" ? "text-amber-200" : "text-muted-foreground",
          )}
        >
          {remediationHint}
        </div>
      )}
      {children}
    </label>
  );
}

function splitCommaSeparated(value: string) {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}
