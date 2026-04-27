"use client";

import {
  Handle,
  MarkerType,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { AlertCircleIcon, MoveRightIcon } from "lucide-react";
import { useMemo } from "react";

import { Canvas } from "@/components/ai-elements/canvas";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useBrainPlan } from "@/core/brain";
import { useWorkflows } from "@/core/workflows";
import { buildBrainPlanPayload, type Workflow } from "@/core/workflows";
import { cn } from "@/lib/utils";

type WorkflowCanvasNodeData = {
  title: string;
  subtitle?: string;
  meta?: string;
  tone?: "primary" | "branch" | "group" | "brain" | "gate";
};

type WorkflowCanvasNode = Node<WorkflowCanvasNodeData, "workflow-card">;

const workflowNodeTypes = {
  "workflow-card": WorkflowCardNode,
};

export function WorkflowGraph() {
  const { selectedWorkflow } = useWorkflows();
  const { brainPlan } = useBrainPlan(
    selectedWorkflow && selectedWorkflow.goal.trim().length > 0
      ? buildBrainPlanPayload(selectedWorkflow)
      : null,
  );

  const { nodes, edges } = useMemo(() => {
    if (!selectedWorkflow) {
      return { nodes: [] as Node[], edges: [] as Edge[] };
    }
    if (brainPlan?.strategy_validation.valid) {
      return buildBrainGraph(brainPlan);
    }
    return buildGraph(selectedWorkflow);
  }, [brainPlan, selectedWorkflow]);

  if (!selectedWorkflow) {
    return (
      <Card className="h-full justify-center border-dashed shadow-none">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertCircleIcon className="size-4" />
            No workflow selected
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Create a `task`, `branch`, or `group` card first. The graph stays
          constrained on purpose: the main agent always owns review and closure.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">{selectedWorkflow.title}</h3>
          <p className="text-xs text-muted-foreground">
            {selectedWorkflow.mode === "task"
              ? "Single-chain orchestration with explicit return to the main agent."
              : selectedWorkflow.mode === "branch"
                ? "Parallel branches report back to the main agent for synthesis."
                : "Group discussion remains supervised by a manager loop."}
          </p>
        </div>
        <Badge variant="secondary">{selectedWorkflow.mode}</Badge>
      </div>
      <div className="octo-panel octo-grid min-h-0 flex-1 overflow-hidden rounded-[1.75rem]">
        <Canvas
          edges={edges}
          fitView
          nodes={nodes}
          nodeTypes={workflowNodeTypes}
          proOptions={{ hideAttribution: true }}
        />
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <MoveRightIcon className="size-3" />
        {brainPlan?.strategy_validation.valid
          ? "Solid edges are same-turn dependencies. Dashed amber edges are lagged feedback loops."
          : "Big arrows are represented as thick directed edges during design. Runtime stays checkpoint-based to prevent infinite loops."}
      </div>
    </div>
  );
}

function buildBrainGraph(
  brainPlan: NonNullable<ReturnType<typeof useBrainPlan>["brainPlan"]>,
) {
  const stageY = {
    observe: 40,
    infer: 150,
    score: 280,
    decide: 420,
    execute: 560,
    review: 700,
  } as const;

  const stageCounts = new Map<string, number>();
  const nodes: WorkflowCanvasNode[] = brainPlan.strategy_graph.nodes.map((node) => {
    const currentCount = stageCounts.get(node.stage) ?? 0;
    stageCounts.set(node.stage, currentCount + 1);
    return createWorkflowNode(node.id, { x: 60 + currentCount * 220, y: stageY[node.stage] }, {
      title: node.title,
      subtitle: node.stage,
      tone: node.stage === "decide" || node.stage === "execute" ? "primary" : "brain",
    });
  });

  const arbitrationNodes: WorkflowCanvasNode[] = brainPlan.strategy_graph.arbitrations.map(
    (arbitration, index) =>
      createWorkflowNode(
        `arbitration-${arbitration.output_name}`,
        { x: 760, y: 120 + index * 180 },
        {
        title: arbitration.output_name,
        subtitle: arbitration.mode,
        tone:
          arbitration.mode === "veto" || arbitration.mode === "policy_gate"
            ? "gate"
            : "branch",
        },
      ),
  );

  const edges: Edge[] = brainPlan.strategy_graph.edges.map((edge, index) => ({
    id: `brain-edge-${index}-${edge.source}-${edge.target}`,
    source: edge.source,
    target: edge.target,
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
    style: {
      strokeWidth: edge.kind === "feedback_lagged" ? 2 : 3,
      stroke:
        edge.kind === "causal"
          ? "var(--foreground)"
          : edge.kind === "feedback_lagged"
            ? "oklch(0.72 0.16 85)"
            : "var(--muted-foreground)",
      strokeDasharray: edge.kind === "feedback_lagged" ? "7 5" : undefined,
    },
    animated: edge.kind !== "precedence",
    label: edge.kind === "feedback_lagged" ? `lag ${edge.lag}` : edge.kind,
  }));

  const arbitrationEdges: Edge[] = brainPlan.strategy_graph.arbitrations.flatMap(
    (arbitration, index) =>
      arbitration.owners.map((owner, ownerIndex) => ({
        id: `arbitration-edge-${index}-${ownerIndex}-${owner}`,
        source: owner,
        target: `arbitration-${arbitration.output_name}`,
        markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
        style: {
          strokeWidth: 2,
          stroke:
            arbitration.mode === "veto"
              ? "oklch(0.72 0.16 30)"
              : "oklch(0.68 0.15 220)",
          strokeDasharray: "6 4",
        },
        animated: true,
        label: arbitration.mode,
      })),
  );

  return { nodes: [...nodes, ...arbitrationNodes], edges: [...edges, ...arbitrationEdges] };
}

function buildGraph(workflow: Workflow) {
  if (workflow.mode === "task") {
    return buildTaskGraph(workflow);
  }
  if (workflow.mode === "branch") {
    return buildBranchGraph(workflow);
  }
  return buildGroupGraph(workflow);
}

function buildTaskGraph(workflow: Extract<Workflow, { mode: "task" }>) {
  const nodes: WorkflowCanvasNode[] = workflow.route.map((agent, index) =>
    createWorkflowNode(`${workflow.id}-${index}`, { x: 80 + index * 180, y: 130 }, {
      title: labelForNode(agent, index === 0 || index === workflow.route.length - 1),
      subtitle: index === 0 || index === workflow.route.length - 1 ? "orchestrator" : "specialist",
      tone: index === 0 || index === workflow.route.length - 1 ? "primary" : "branch",
    }),
  );

  const edges: Edge[] = workflow.route.slice(1).map((_, index) => ({
    id: `${workflow.id}-edge-${index}`,
    source: `${workflow.id}-${index}`,
    target: `${workflow.id}-${index + 1}`,
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
    style: { strokeWidth: 3 },
    animated: index < workflow.route.length - 2,
  }));

  return { nodes, edges };
}

function buildBranchGraph(workflow: Extract<Workflow, { mode: "branch" }>) {
  const mainId = `${workflow.id}-main`;
  const nodes: WorkflowCanvasNode[] = [
    createWorkflowNode(mainId, { x: 300, y: 30 }, {
      title: "Main Agent",
      subtitle: "dispatch",
      tone: "primary",
    }),
    ...workflow.branches.map((branch, index) =>
      createWorkflowNode(branch.id, { x: 80 + index * 220, y: 180 }, {
        title: branch.agentName,
        subtitle: branch.responsibility,
        tone: "branch",
      }),
    ),
    createWorkflowNode(`${workflow.id}-merge`, { x: 300, y: 330 }, {
      title: "Main Agent",
      subtitle: "synthesize",
      tone: "primary",
    }),
  ];

  const edges: Edge[] = workflow.branches.flatMap((branch) => [
    {
      id: `${mainId}-${branch.id}`,
      source: mainId,
      target: branch.id,
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      style: { strokeWidth: 3 },
    },
    {
      id: `${branch.id}-merge`,
      source: branch.id,
      target: `${workflow.id}-merge`,
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      style: { strokeWidth: 3 },
      animated: true,
    },
  ]);

  return { nodes, edges };
}

function buildGroupGraph(workflow: Extract<Workflow, { mode: "group" }>) {
  const nodes: WorkflowCanvasNode[] = [
    createWorkflowNode(`${workflow.id}-main`, { x: 300, y: 20 }, {
      title: "Main Agent",
      subtitle: "owner",
      tone: "primary",
    }),
    createWorkflowNode(`${workflow.id}-manager`, { x: 300, y: 150 }, {
      title: "Group Manager",
      subtitle: "moderate",
      tone: "group",
    }),
    ...workflow.agents.map((agent, index) =>
      createWorkflowNode(`${workflow.id}-agent-${index}`, { x: 40 + index * 160, y: 300 }, {
        title: agent,
        subtitle: "participant",
        tone: "branch",
      }),
    ),
  ];

  const edges: Edge[] = [
    {
      id: `${workflow.id}-main-manager`,
      source: `${workflow.id}-main`,
      target: `${workflow.id}-manager`,
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      style: { strokeWidth: 3 },
    },
    ...workflow.agents.flatMap((agent, index) => [
      {
        id: `${workflow.id}-manager-${index}`,
        source: `${workflow.id}-manager`,
        target: `${workflow.id}-agent-${index}`,
        markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
        style: { strokeWidth: 2.5 },
      },
      {
        id: `${workflow.id}-agent-manager-${index}`,
        source: `${workflow.id}-agent-${index}`,
        target: `${workflow.id}-manager`,
        markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
        style: { strokeWidth: 2.5 },
        animated: true,
      },
    ]),
  ];

  return { nodes, edges };
}

function labelForNode(agent: string, isPrimary: boolean) {
  return isPrimary ? "Main Agent" : agent;
}

function createWorkflowNode(
  id: string,
  position: { x: number; y: number },
  data: WorkflowCanvasNodeData,
): WorkflowCanvasNode {
  return {
    id,
    type: "workflow-card",
    position,
    data,
  };
}

function WorkflowCardNode({ data }: NodeProps<WorkflowCanvasNode>) {
  const toneClassName =
    data.tone === "primary"
      ? "border-primary/30 bg-[linear-gradient(180deg,var(--panel-start),var(--panel-end))]"
      : data.tone === "gate"
        ? "border-amber-400/35 bg-[linear-gradient(180deg,var(--panel-start),var(--panel-end))]"
        : data.tone === "group"
          ? "border-chart-3/30 bg-[linear-gradient(180deg,var(--panel-start),var(--panel-end))]"
          : data.tone === "brain"
            ? "border-chart-4/30 bg-[linear-gradient(180deg,var(--panel-start),var(--panel-end))]"
            : "border-border/70 bg-[linear-gradient(180deg,var(--panel-start),var(--panel-end))]";

  return (
    <>
      <Handle className="!size-3 !border-2 !border-white !bg-primary" position={Position.Left} type="target" />
      <div
        className={cn(
          "min-w-[190px] max-w-[240px] rounded-[1.35rem] border p-3 shadow-[3px_3px_8px_var(--neu-dark),_-3px_-3px_8px_var(--neu-light)] backdrop-blur-md",
          toneClassName,
        )}
      >
        <div className="space-y-1">
          {data.subtitle ? (
            <div className="text-[10px] font-medium uppercase tracking-[0.22em] text-muted-foreground">
              {data.subtitle}
            </div>
          ) : null}
          <div className="text-sm font-semibold tracking-[-0.04em] text-foreground">
            {data.title}
          </div>
          {data.meta ? (
            <div className="text-xs leading-5 text-muted-foreground">{data.meta}</div>
          ) : null}
        </div>
      </div>
      <Handle className="!size-3 !border-2 !border-white !bg-primary" position={Position.Right} type="source" />
    </>
  );
}
