"use client";

import {
  Handle,
  MarkerType,
  Position,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
  type OnNodesChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
} from "@xyflow/react";
import {
  BriefcaseIcon,
  CrownIcon,
  SettingsIcon,
  UserIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AgentAvatar } from "@/components/brand/octo-mark";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import type {
  AgentHandle,
  TaskCard,
  TaskCardEdge,
  TaskAgentRuntimeProvider,
  TaskCardGraph,
  TaskStudioRuntimeResponse,
} from "@/core/task-workspaces";
import { formatTaskRuntimeProvider } from "@/core/task-workspaces/runtime-provider";
import { cn } from "@/lib/utils";

/* ────────────────────────────────────────────
   Types
   ──────────────────────────────────────────── */

type CardNodeData = {
  card: TaskCard;
  role: "project" | "primary" | "sub-agent" | "system";
  compact?: boolean;
  avatarUrl?: string | null;
  agentLabel?: string | null;
  runtimeCardStatus?: TaskCard["status"] | null;
  runtimeStatusLabel?: string | null;
  runtimeDetail?: string | null;
  isSelected?: boolean;
  onDescriptionChange?: (cardId: string, desc: string) => void;
};

type CardNode = Node<CardNodeData, "task-card">;

type AgentDirectoryEntry = {
  avatarUrl?: string | null;
  name?: string | null;
  role?: string | null;
  index: number;
};

type RuntimeTopologyRuntime = Pick<
  TaskStudioRuntimeResponse,
  "status" | "agents" | "handoffs" | "readiness" | "runtime_summary"
>;

type RuntimeCardState = {
  cardStatus: TaskCard["status"];
  statusLabel: string;
  detail?: string | null;
};

const EMPTY_AGENT_HANDLES: AgentHandle[] = [];

function formatRuntimeLabel(value: string | null | undefined) {
  return value?.replace(/_/g, " ") ?? "idle";
}

function normalizeRuntimeCardStatus(status: string | null | undefined): TaskCard["status"] {
  switch (status) {
    case "running":
    case "waiting_handoff":
      return "running";
    case "completed":
      return "completed";
    case "paused":
    case "waiting_review":
      return "paused";
    case "failed":
      return "blocked";
    case "terminated":
      return "terminated";
    case "configured":
      return "configured";
    default:
      return "idle";
  }
}

function runtimeEdgeTone(status: string | null | undefined) {
  if (status === "completed") {
    return "oklch(0.72 0.16 152)";
  }
  if (status === "failed") {
    return "oklch(0.63 0.21 27)";
  }
  if (status === "waiting_review") {
    return "oklch(0.81 0.16 83)";
  }
  if (status === "paused") {
    return "oklch(0.74 0.15 50)";
  }
  return "oklch(0.68 0.15 220)";
}

function runtimePairKey(sourceCardId: string, targetCardId: string) {
  return `${sourceCardId}::${targetCardId}`;
}

function cardStatusTone(status: TaskCard["status"]) {
  if (status === "running") {
    return {
      container: "border-emerald-400/60 shadow-[0_0_0_1px_rgb(16_185_129_/_0.12)]",
      badge: "border-emerald-200 bg-emerald-50 text-emerald-700",
    };
  }
  if (status === "completed") {
    return {
      container: "border-cyan-400/60 shadow-[0_0_0_1px_rgb(34_211_238_/_0.12)]",
      badge: "border-cyan-200 bg-cyan-50 text-cyan-700",
    };
  }
  if (status === "paused") {
    return {
      container: "border-amber-400/60 shadow-[0_0_0_1px_rgb(245_158_11_/_0.12)]",
      badge: "border-amber-200 bg-amber-50 text-amber-700",
    };
  }
  if (status === "blocked" || status === "terminated") {
    return {
      container: "border-rose-400/60 shadow-[0_0_0_1px_rgb(244_63_94_/_0.12)]",
      badge: "border-rose-200 bg-rose-50 text-rose-700",
    };
  }
  return {
    container: "",
    badge: "border-border bg-background text-muted-foreground",
  };
}

/* ────────────────────────────────────────────
   Card classification — works with both old and new card formats
   ──────────────────────────────────────────── */

function isManagementRole(role: string | null | undefined) {
  const normalized = role?.trim().toLowerCase();
  return normalized != null && ["lead", "coordinator", "manager", "orchestrator"].includes(normalized);
}

function roleHintForCard(
  card: TaskCard,
  agentDirectory: Map<string, AgentDirectoryEntry>,
) {
  if (!card.linked_agent_id) {
    return null;
  }
  return (
    agentDirectory.get(card.linked_agent_id)?.role
    ?? metadataString(card.config, "agent_role")
    ?? metadataString(card.config, "role")
  );
}

function projectLikeCard(card: TaskCard) {
  return card.kind === "start"
    || card.tags.includes("project")
    || card.tags.includes("entry")
    || metadataString(card.config, "document_role") === "project"
    || (!card.linked_agent_id && metadataString(card.config, "result_document_path") != null);
}

function inferPrimaryCard(
  cards: TaskCard[],
  edges: TaskCardEdge[],
  agentDirectory: Map<string, AgentDirectoryEntry>,
) {
  const agentCards = cards.filter((card) => card.linked_agent_id != null);
  if (agentCards.length === 0) {
    return null;
  }

  const explicitlyPrimary = agentCards.find((card) => {
    if (card.tags.includes("primary")) {
      return true;
    }
    if (card.config?.is_primary === true) {
      return true;
    }
    return isManagementRole(roleHintForCard(card, agentDirectory));
  });
  if (explicitlyPrimary) {
    return explicitlyPrimary;
  }

  const incomingByCard = new Map<string, number>();
  const outgoingByCard = new Map<string, number>();
  for (const edge of edges) {
    incomingByCard.set(edge.target_card_id, (incomingByCard.get(edge.target_card_id) ?? 0) + 1);
    outgoingByCard.set(edge.source_card_id, (outgoingByCard.get(edge.source_card_id) ?? 0) + 1);
  }

  return [...agentCards].sort((left, right) => {
    const leftIncoming = incomingByCard.get(left.card_id) ?? 0;
    const rightIncoming = incomingByCard.get(right.card_id) ?? 0;
    if (leftIncoming !== rightIncoming) {
      return leftIncoming - rightIncoming;
    }
    const leftOutgoing = outgoingByCard.get(left.card_id) ?? 0;
    const rightOutgoing = outgoingByCard.get(right.card_id) ?? 0;
    if (leftOutgoing !== rightOutgoing) {
      return rightOutgoing - leftOutgoing;
    }
    const leftIndex = left.linked_agent_id ? (agentDirectory.get(left.linked_agent_id)?.index ?? Number.MAX_SAFE_INTEGER) : Number.MAX_SAFE_INTEGER;
    const rightIndex = right.linked_agent_id ? (agentDirectory.get(right.linked_agent_id)?.index ?? Number.MAX_SAFE_INTEGER) : Number.MAX_SAFE_INTEGER;
    return leftIndex - rightIndex;
  })[0] ?? null;
}

function metadataString(metadata: Record<string, unknown>, key: string) {
  const value = metadata[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function readCardPosition(card: TaskCard) {
  const position = card.config?.position;
  if (typeof position === "object" && position != null) {
    const candidate = position as { x?: unknown; y?: unknown };
    if (typeof candidate.x === "number" && typeof candidate.y === "number") {
      return { x: candidate.x, y: candidate.y };
    }
  }
  return null;
}

function writeCardPosition(card: TaskCard, position: { x: number; y: number }): TaskCard {
  return {
    ...card,
    config: {
      ...card.config,
      position: {
        x: Math.round(position.x),
        y: Math.round(position.y),
      },
    },
  };
}

function buildCardsFromNodes(nodes: CardNode[]): TaskCard[] {
  return nodes.map((node) => writeCardPosition(node.data.card, node.position));
}

function buildCardEdges(edges: Edge[]): TaskCardEdge[] {
  const normalizeEdgeLabel = (label: unknown): string | null => {
    if (typeof label === "string") {
      return label;
    }
    if (typeof label === "number" || typeof label === "boolean" || typeof label === "bigint") {
      return String(label);
    }
    return null;
  };

  return edges
    .filter((edge) => edge.source && edge.target)
    .map((edge) => ({
      edge_id: edge.id,
      source_card_id: String(edge.source),
      target_card_id: String(edge.target),
      label: normalizeEdgeLabel(edge.label),
    }));
}

/* ────────────────────────────────────────────
   Layout helpers
   ──────────────────────────────────────────── */

function layoutNodes(
  cards: TaskCard[],
  edges: TaskCardEdge[],
  agentDirectory: Map<string, AgentDirectoryEntry>,
  compact = false,
): CardNode[] {
  if (cards.length === 0) return [];

  // Determine topology from project card config
  const projectCard = cards.find(projectLikeCard) ?? null;
  const primaryCard = inferPrimaryCard(cards, edges, agentDirectory);
  const projectEntry = projectCard ? { card: projectCard, role: "project" as const } : null;
  const topology = (projectEntry?.card.config?.topology as string) ?? "single";
  const primaryEntry = primaryCard ? { card: primaryCard, role: "primary" as const } : null;
  const subEntries = cards
    .filter((card) => card.linked_agent_id != null && card.card_id !== primaryCard?.card_id)
    .map((card) => ({ card, role: "sub-agent" as const }));
  const consumedIds = new Set([
    ...(projectCard ? [projectCard.card_id] : []),
    ...(primaryCard ? [primaryCard.card_id] : []),
    ...subEntries.map((entry) => entry.card.card_id),
  ]);
  const systemEntries = cards
    .filter((card) => !consumedIds.has(card.card_id))
    .map((card) => ({ card, role: "system" as const }));

  if (!projectEntry && !primaryEntry && subEntries.length === 0) {
    return cards.map((card, i) =>
      makeCardNode(
        card,
        readCardPosition(card) ?? { x: 200, y: 40 + i * 140 },
        card.linked_agent_id ? "sub-agent" : "system",
        agentDirectory.get(card.linked_agent_id ?? ""),
        compact,
      ),
    );
  }

  const nodes: CardNode[] = [];
  let xCursor = 40;

  // Project card at far left
  if (projectEntry) {
    nodes.push(makeCardNode(
      projectEntry.card,
      readCardPosition(projectEntry.card) ?? { x: xCursor, y: 200 },
      "project",
      agentDirectory.get(projectEntry.card.linked_agent_id ?? ""),
      compact,
    ));
    xCursor += 280;
  }

  // System cards stacked below project
  systemEntries.forEach((entry, i) => {
    nodes.push(makeCardNode(
      entry.card,
      readCardPosition(entry.card) ?? { x: 40, y: 380 + i * 120 },
      "system",
      agentDirectory.get(entry.card.linked_agent_id ?? ""),
      compact,
    ));
  });

  // Sub-agents: layout depends on topology
  if (topology === "group" && (primaryEntry || subEntries.length > 0)) {
    const circleEntries = [
      ...(primaryEntry ? [primaryEntry] : []),
      ...subEntries,
    ];
    if (circleEntries.length === 1) {
      const entry = circleEntries[0];
      if (!entry) {
        return nodes;
      }
      nodes.push(makeCardNode(
        entry.card,
        readCardPosition(entry.card) ?? { x: xCursor, y: 200 },
        entry.role,
        agentDirectory.get(entry.card.linked_agent_id ?? ""),
        compact,
      ));
    } else {
      const centerX = xCursor + 160;
      const centerY = 220;
      const radius = Math.max(150, circleEntries.length * 38);
      circleEntries.forEach((entry, i) => {
        const angle = -Math.PI / 2 + (i * 2 * Math.PI) / circleEntries.length;
        nodes.push(makeCardNode(
          entry.card,
          readCardPosition(entry.card) ?? {
            x: centerX + radius * Math.cos(angle),
            y: centerY + radius * Math.sin(angle),
          },
          entry.role,
          agentDirectory.get(entry.card.linked_agent_id ?? ""),
          compact,
        ));
      });
    }
  } else {
    if (primaryEntry) {
      nodes.push(makeCardNode(
        primaryEntry.card,
        readCardPosition(primaryEntry.card) ?? { x: xCursor, y: 200 },
        "primary",
        agentDirectory.get(primaryEntry.card.linked_agent_id ?? ""),
        compact,
      ));
      xCursor += 300;
    }

    if (subEntries.length > 0) {
    if (topology === "branch") {
      // Tree: fan out vertically to the right of primary
      const startY = Math.max(40, 200 - ((subEntries.length - 1) * 130) / 2);
      subEntries.forEach((entry, i) => {
        nodes.push(makeCardNode(
          entry.card,
          readCardPosition(entry.card) ?? { x: xCursor, y: startY + i * 130 },
          "sub-agent",
          agentDirectory.get(entry.card.linked_agent_id ?? ""),
          compact,
        ));
      });
    } else {
      // Chain / single: vertical cascade below primary
      const baseX = primaryEntry ? xCursor - 300 : xCursor;
      subEntries.forEach((entry, i) => {
        nodes.push(makeCardNode(
          entry.card,
          readCardPosition(entry.card) ?? { x: baseX, y: 380 + i * 130 },
          "sub-agent",
          agentDirectory.get(entry.card.linked_agent_id ?? ""),
          compact,
        ));
      });
    }
  }
  }

  return nodes;
}

function makeCardNode(
  card: TaskCard,
  position: { x: number; y: number },
  role: CardNodeData["role"],
  agentMeta?: AgentDirectoryEntry,
  compact = false,
): CardNode {
  return {
    id: card.card_id,
    type: "task-card",
    position,
    zIndex: role === "project" ? 30 : role === "primary" ? 20 : 10,
    data: {
      card,
      role,
      compact,
      avatarUrl: agentMeta?.avatarUrl ?? null,
      agentLabel: agentMeta?.name ?? null,
    },
    draggable: true,
  };
}

function toReactFlowEdges(edges: TaskCardEdge[]): Edge[] {
  return edges.map((e) => ({
    id: e.edge_id,
    source: e.source_card_id,
    target: e.target_card_id,
    label: e.label ?? undefined,
    markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
    markerStart:
      e.label === "dispatches" || e.label === "reports" || e.label === "collaborates"
        ? { type: MarkerType.ArrowClosed, width: 14, height: 14 }
        : undefined,
    style: {
      strokeWidth: e.label === "orchestrates" ? 3 : 2,
      stroke:
        e.label === "dispatches"
          ? "oklch(0.65 0.18 145)"
          : e.label === "reports"
            ? "oklch(0.72 0.16 30)"
            : e.label === "collaborates"
              ? "oklch(0.68 0.15 220)"
              : "var(--foreground)",
    },
    animated: e.label === "reports" || e.label === "collaborates",
  }));
}

function buildRuntimeCardStates(
  cards: TaskCard[],
  runtime: RuntimeTopologyRuntime | null | undefined,
): Map<string, RuntimeCardState> {
  if (!runtime) {
    return new Map();
  }

  const cardIdByAgentId = new Map(
    cards
      .filter((card) => card.linked_agent_id)
      .map((card) => [card.linked_agent_id!, card.card_id]),
  );

  const runtimeCardStates = new Map<string, RuntimeCardState>();
  for (const agent of runtime.agents) {
    const linkedCardId = agent.linked_card_id ?? cardIdByAgentId.get(agent.agent_id);
    if (!linkedCardId) {
      continue;
    }

    const statusLabel = agent.last_execution_status ?? agent.status;
    runtimeCardStates.set(linkedCardId, {
      cardStatus: normalizeRuntimeCardStatus(statusLabel),
      statusLabel: formatRuntimeLabel(statusLabel),
      detail:
        agent.last_result_summary
        ?? agent.last_execution_target
        ?? agent.runtime_session_id
        ?? null,
    });
  }

  return runtimeCardStates;
}

function buildRenderedEdges(
  cardGraph: TaskCardGraph,
  agents: AgentHandle[],
  runtime: RuntimeTopologyRuntime | null | undefined,
): Edge[] {
  const baseEdges = toReactFlowEdges(cardGraph.edges);
  if (!runtime) {
    return baseEdges;
  }

  const projectCardId = cardGraph.cards.find(projectLikeCard)?.card_id ?? null;
  const cardIdByAgentId = new Map(
    cardGraph.cards
      .filter((card) => card.linked_agent_id)
      .map((card) => [card.linked_agent_id!, card.card_id]),
  );
  const linkedCardIdByAgentId = new Map(cardIdByAgentId);

  for (const runtimeAgent of runtime.agents) {
    if (runtimeAgent.linked_card_id) {
      linkedCardIdByAgentId.set(runtimeAgent.agent_id, runtimeAgent.linked_card_id);
    }
  }

  for (const agent of agents) {
    if (agent.linked_card_id && !linkedCardIdByAgentId.has(agent.agent_id)) {
      linkedCardIdByAgentId.set(agent.agent_id, agent.linked_card_id);
    }
  }

  const persistedPairs = new Map(
    cardGraph.edges.map((edge) => [runtimePairKey(edge.source_card_id, edge.target_card_id), edge.edge_id]),
  );
  const runtimePairs = new Map<string, RuntimeTopologyRuntime["handoffs"][number]>();
  const overlayEdges: Edge[] = [];

  for (const handoff of runtime.handoffs) {
    const targetCardId = handoff.linked_card_id ?? linkedCardIdByAgentId.get(handoff.target_agent_id);
    const sourceCardId = linkedCardIdByAgentId.get(handoff.source_agent_id) ?? projectCardId;
    if (!sourceCardId || !targetCardId || sourceCardId === targetCardId) {
      continue;
    }

    const pairKey = runtimePairKey(sourceCardId, targetCardId);
    if (runtimePairs.has(pairKey)) {
      continue;
    }

    runtimePairs.set(pairKey, handoff);
    if (persistedPairs.has(pairKey)) {
      continue;
    }

    const stroke = runtimeEdgeTone(handoff.status);
    overlayEdges.push({
      id: `runtime-${handoff.handoff_id}`,
      source: sourceCardId,
      target: targetCardId,
      label: `Workflow · ${formatRuntimeLabel(handoff.status)}`,
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
      style: {
        stroke,
        strokeWidth: 3,
        strokeDasharray: "6 4",
      },
      animated: true,
      selectable: false,
      deletable: false,
      focusable: false,
      data: { runtime: true },
    });
  }

  const mergedEdges = baseEdges.map((edge) => {
    const handoff = runtimePairs.get(runtimePairKey(String(edge.source), String(edge.target)));
    if (!handoff) {
      return edge;
    }

    const stroke = runtimeEdgeTone(handoff.status);
    return {
      ...edge,
      label: `Workflow · ${formatRuntimeLabel(handoff.status)}`,
      style: {
        ...edge.style,
        stroke,
        strokeWidth: 3,
        strokeDasharray: "6 4",
      },
      animated: true,
      data: {
        ...(typeof edge.data === "object" && edge.data != null ? edge.data : {}),
        runtime: true,
      },
    } satisfies Edge;
  });

  return [...mergedEdges, ...overlayEdges];
}

function RuntimeTopologySummary({
  runtime,
  preferredProvider,
}: {
  runtime?: RuntimeTopologyRuntime | null;
  preferredProvider?: TaskAgentRuntimeProvider;
}) {
  if (!runtime) {
    return null;
  }

  const providerLabel = formatTaskRuntimeProvider(
    runtime.runtime_summary.last_runtime_provider ?? preferredProvider,
  );

  return (
    <div
      className="pointer-events-none absolute left-3 top-3 z-10 max-w-[560px]"
      data-testid="task-runtime-topology-summary"
    >
      <div className="rounded-2xl border border-border/70 bg-background/90 px-3 py-2 shadow-[3px_3px_8px_var(--neu-dark),_-3px_-3px_8px_var(--neu-light)] backdrop-blur-md">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            LangGraph workflow topology
          </span>
          <Badge variant="outline" className="text-[10px] capitalize">
            {formatRuntimeLabel(runtime.status)}
          </Badge>
          <Badge variant="outline" className="text-[10px]">
            {runtime.agents.length} agents
          </Badge>
          <Badge variant="outline" className="text-[10px]">
            {runtime.handoffs.length} live handoffs
          </Badge>
          {runtime.readiness.requires_review ? (
            <Badge
              variant="outline"
              className="border-amber-400/60 bg-amber-500/10 text-[10px] text-amber-700 dark:text-amber-300"
            >
              review required
            </Badge>
          ) : null}
        </div>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
          <span>phase: {runtime.runtime_summary.current_phase ?? "pending"}</span>
          <span>provider: {providerLabel}</span>
          <span>session: {runtime.runtime_summary.latest_runtime_session_id ?? "unassigned"}</span>
        </div>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────
   Card Node Component
   ──────────────────────────────────────────── */

const taskCardNodeTypes = {
  "task-card": TaskCardNode,
};

function TaskCardNode({ data }: NodeProps<CardNode>) {
  const { t } = useI18n();
  const { card, role } = data;
  const compactCard = data.compact === true;
  const [editing, setEditing] = useState(false);
  const [desc, setDesc] = useState(card.description ?? "");
  const effectiveCardStatus = data.runtimeCardStatus ?? card.status;
  const statusTone = cardStatusTone(effectiveCardStatus);

  const toneClass =
    role === "project"
      ? "border-amber-400/80 bg-[linear-gradient(180deg,color-mix(in_srgb,var(--panel-start)_74%,white_26%),color-mix(in_srgb,var(--panel-end)_82%,var(--accent)_18%))] shadow-[0_20px_40px_rgba(217,119,6,0.16),3px_3px_8px_var(--neu-dark),_-3px_-3px_8px_var(--neu-light)]"
      : role === "primary"
        ? "border-primary/70 bg-[linear-gradient(180deg,color-mix(in_srgb,var(--panel-start)_78%,white_22%),color-mix(in_srgb,var(--panel-end)_82%,var(--primary)_18%))] shadow-[0_18px_38px_rgba(124,58,237,0.16),3px_3px_8px_var(--neu-dark),_-3px_-3px_8px_var(--neu-light)]"
        : role === "sub-agent"
          ? "border-chart-3/30 bg-[linear-gradient(180deg,var(--panel-start),var(--panel-end))]"
          : "border-border/70 bg-[linear-gradient(180deg,var(--panel-start),var(--panel-end))]";
  const selectedClass = data.isSelected
    ? "ring-2 ring-primary/70 ring-offset-2 ring-offset-background"
    : "";

  const icon =
    role === "project" ? (
      <BriefcaseIcon className="size-4 text-amber-500" />
    ) : role === "primary" ? (
      <CrownIcon className="size-4 text-primary" />
    ) : role === "sub-agent" ? (
      <UserIcon className="size-4 text-chart-3" />
    ) : (
      <SettingsIcon className="size-4 text-muted-foreground" />
    );

  const roleLabel =
    role === "project"
      ? "project"
      : role === "primary"
        ? t.taskGraph.primaryAgent
        : role === "sub-agent"
          ? t.taskGraph.subAgent
          : card.kind;

          const isEditable = !compactCard && (role === "primary" || role === "sub-agent");

  return (
    <>
      <Handle
        className="!size-3 !border-2 !border-white !bg-primary"
        position={Position.Left}
        type="target"
      />
      <div
        className={cn(
          compactCard
            ? "min-w-[108px] max-w-[108px] rounded-[0.95rem] border px-2 py-2 shadow-[2px_2px_6px_var(--neu-dark),_-2px_-2px_6px_var(--neu-light)]"
            : "min-w-[190px] max-w-[260px] rounded-[1.35rem] border p-3 shadow-[3px_3px_8px_var(--neu-dark),_-3px_-3px_8px_var(--neu-light)] backdrop-blur-md",
          toneClass,
          statusTone.container,
          selectedClass,
        )}
      >
        <div className={cn(compactCard ? "space-y-1" : "space-y-1.5")}>
          {!compactCard && (role === "project" || role === "primary") ? (
            <div className="flex items-center justify-between gap-2 rounded-full border border-border/60 bg-background/60 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-foreground/80">
              <span>{role === "project" ? "Workflow Root" : "Primary Flow"}</span>
              <span className={cn("h-2.5 w-2.5 rounded-full", role === "project" ? "bg-amber-500" : "bg-primary")} />
            </div>
          ) : null}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {role === "primary" || role === "sub-agent" ? (
                <AgentAvatar avatarUrl={data.avatarUrl} size={compactCard ? 16 : 22} />
              ) : (
                icon
              )}
              <span className={cn("font-medium uppercase tracking-[0.22em] text-muted-foreground", compactCard ? "text-[8px]" : "text-[10px]")}>
                {roleLabel}
              </span>
            </div>
            <Badge variant="outline" className={cn("capitalize", statusTone.badge, compactCard ? "px-1 py-0 text-[8px]" : "")}>
              {data.runtimeStatusLabel ?? effectiveCardStatus}
            </Badge>
          </div>
          <div className={cn(
            "tracking-[-0.04em] text-foreground",
            compactCard
              ? "truncate text-[10px] font-semibold"
              : role === "project"
                ? "text-base font-extrabold"
                : role === "primary"
                  ? "text-[15px] font-bold"
                  : "text-sm font-semibold",
          )}>
            {card.title}
          </div>
          {data.agentLabel && data.agentLabel !== card.title ? (
            <div className={cn("text-muted-foreground", compactCard ? "truncate text-[9px]" : "text-[11px]")}>{data.agentLabel}</div>
          ) : null}
          {data.runtimeDetail ? (
            <p className={cn("leading-4 text-muted-foreground", compactCard ? "truncate text-[8px]" : "text-[11px]")}>
              {data.runtimeDetail}
            </p>
          ) : null}
          {isEditable && !editing && card.description ? (
            <p
              className="cursor-pointer text-xs leading-5 text-muted-foreground hover:text-foreground"
              onDoubleClick={() => setEditing(true)}
              title={t.taskGraph.doubleClickToEdit}
            >
              {card.description}
            </p>
          ) : !isEditable && card.description ? (
            <p className="text-xs leading-5 text-muted-foreground">
              {card.description}
            </p>
          ) : null}
          {isEditable && editing ? (
            <Textarea
              className="min-h-[48px] text-xs"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              onBlur={() => {
                setEditing(false);
                data.onDescriptionChange?.(card.card_id, desc);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  setEditing(false);
                  data.onDescriptionChange?.(card.card_id, desc);
                }
              }}
              autoFocus
            />
          ) : null}
          {!compactCard && card.tags.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {card.tags
                .filter(
                  (t) =>
                    !["project", "primary", "entry", "agent", "sub-agent", "interface", "runtime"].includes(t),
                )
                .map((tag) => (
                  <Badge key={tag} variant="outline" className="text-[9px]">
                    {tag}
                  </Badge>
                ))}
            </div>
          ) : null}
        </div>
      </div>
      <Handle
        className="!size-3 !border-2 !border-white !bg-primary"
        position={Position.Right}
        type="source"
      />
    </>
  );
}

/* ────────────────────────────────────────────
   Inner component (inside ReactFlowProvider)
   ──────────────────────────────────────────── */

function TaskCardGraphInner({
  cardGraph,
  agents = EMPTY_AGENT_HANDLES,
  runtime,
  compactNodes = false,
  selectedCardId,
  onCardSelect,
  onGraphChange,
}: {
  cardGraph: TaskCardGraph;
  agents?: AgentHandle[];
  runtime?: RuntimeTopologyRuntime | null;
  compactNodes?: boolean;
  selectedCardId?: string | null;
  onCardSelect?: (cardId: string) => void;
  onGraphChange?: (graph: TaskCardGraph) => void;
}) {
  const agentDirectory = useMemo(
    () => new Map(
      agents.map((agent, index) => [
        agent.agent_id,
        {
          avatarUrl: metadataString(agent.metadata, "avatar_url"),
          name: agent.name,
          role: agent.role,
          index,
        },
      ]),
    ),
    [agents],
  );
  const initialNodes = useMemo(
    () => layoutNodes(cardGraph.cards, cardGraph.edges, agentDirectory, compactNodes),
    [agentDirectory, cardGraph.cards, cardGraph.edges, compactNodes],
  );
  const initialEdges = useMemo(() => toReactFlowEdges(cardGraph.edges), [cardGraph.edges]);
  const runtimeCardStates = useMemo(
    () => buildRuntimeCardStates(cardGraph.cards, runtime),
    [cardGraph.cards, runtime],
  );
  const renderedEdges = useMemo(
    () => buildRenderedEdges(cardGraph, agents, runtime),
    [agents, cardGraph, runtime],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync when cardGraph prop changes externally
  useEffect(() => {
    setNodes(layoutNodes(cardGraph.cards, cardGraph.edges, agentDirectory, compactNodes));
    setEdges(toReactFlowEdges(cardGraph.edges));
  }, [agentDirectory, cardGraph, compactNodes, setNodes, setEdges]);

  const handleDescriptionChange = useCallback(
    (cardId: string, newDesc: string) => {
      setNodes((current) => {
        const nextNodes = current.map((node) =>
          node.id === cardId
            ? {
              ...node,
              data: {
                ...node.data,
                card: {
                  ...node.data.card,
                  description: newDesc,
                },
              },
            }
            : node,
        );
        onGraphChange?.({ cards: buildCardsFromNodes(nextNodes), edges: buildCardEdges(edges) });
        return nextNodes;
      });
    },
    [edges, onGraphChange, setNodes],
  );

  const nodesWithHandlers = useMemo(
    () =>
      nodes.map((n) => ({
        ...n,
        selected: n.id === selectedCardId,
        data: {
          ...n.data,
          card: runtimeCardStates.has(n.id)
            ? {
              ...n.data.card,
              status: runtimeCardStates.get(n.id)?.cardStatus ?? n.data.card.status,
            }
            : n.data.card,
          isSelected: n.id === selectedCardId,
          runtimeCardStatus: runtimeCardStates.get(n.id)?.cardStatus ?? null,
          runtimeStatusLabel: runtimeCardStates.get(n.id)?.statusLabel ?? null,
          runtimeDetail: runtimeCardStates.get(n.id)?.detail ?? null,
          onDescriptionChange: handleDescriptionChange,
        },
      })),
    [handleDescriptionChange, nodes, runtimeCardStates, selectedCardId],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      const id = `edge-${Date.now()}`;
      const newEdge: Edge = {
        ...connection,
        id,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
        style: { strokeWidth: 2, stroke: "var(--foreground)" },
        label: "custom",
      };
      setEdges((current) => {
        const nextEdges = [...current, newEdge];
        onGraphChange?.({ cards: buildCardsFromNodes(nodes), edges: buildCardEdges(nextEdges) });
        return nextEdges;
      });
    },
    [nodes, onGraphChange, setEdges],
  );

  const onEdgesDelete = useCallback(
    (deleted: Edge[]) => {
      const ids = new Set(deleted.map((e) => e.id));
      setEdges((current) => {
        const nextEdges = current.filter((edge) => !ids.has(edge.id));
        onGraphChange?.({ cards: buildCardsFromNodes(nodes), edges: buildCardEdges(nextEdges) });
        return nextEdges;
      });
    },
    [nodes, onGraphChange, setEdges],
  );

  const onNodeDragStop = useCallback(
    (_event: unknown, node: Node) => {
      setNodes((current) => {
        const nextNodes = current.map((entry) =>
          entry.id === node.id
            ? {
              ...entry,
              position: node.position,
            }
            : entry,
        );
        onGraphChange?.({ cards: buildCardsFromNodes(nextNodes), edges: buildCardEdges(edges) });
        return nextNodes;
      });
    },
    [edges, onGraphChange, setNodes],
  );

  return (
    <ReactFlow
      nodes={nodesWithHandlers as Node[]}
      edges={renderedEdges}
      onNodesChange={onNodesChange as OnNodesChange<Node>}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      onEdgesDelete={onEdgesDelete}
      onNodeClick={(_event, node) => onCardSelect?.(node.id)}
      onNodeDragStop={onNodeDragStop}
      nodeTypes={taskCardNodeTypes}
      deleteKeyCode={["Backspace", "Delete"]}
      fitView
      fitViewOptions={{ padding: compactNodes ? 1.4 : 0.9, maxZoom: compactNodes ? 0.72 : 1.1 }}
      minZoom={compactNodes ? 0.12 : 0.35}
      panOnDrag
      panOnScroll
      zoomOnPinch
      zoomOnDoubleClick={false}
      proOptions={{ hideAttribution: true }}
    >
      <Background
        color="rgba(204, 145, 108, 0.22)"
        gap={22}
        size={1.25}
        variant={BackgroundVariant.Dots}
      />
      <MiniMap
        pannable
        zoomable
        bgColor="rgba(255,255,255,0.75)"
        className="rounded-2xl border border-border/40 shadow-[3px_3px_8px_var(--neu-dark),_-3px_-3px_8px_var(--neu-light)]"
        maskColor="rgba(244,233,222,0.22)"
        nodeBorderRadius={16}
        nodeColor="rgba(199, 119, 89, 0.72)"
        position="bottom-left"
      />
      <Controls
        className="rounded-2xl border border-border/40 bg-card/75 p-1 shadow-[3px_3px_8px_var(--neu-dark),_-3px_-3px_8px_var(--neu-light)] backdrop-blur"
        position="bottom-right"
      />
    </ReactFlow>
  );
}

/* ────────────────────────────────────────────
   Exported wrapper (provides ReactFlowProvider)
   ──────────────────────────────────────────── */

interface TaskCardGraphCanvasProps {
  cardGraph: TaskCardGraph;
  agents?: AgentHandle[];
  runtime?: RuntimeTopologyRuntime | null;
  preferredProvider?: TaskAgentRuntimeProvider;
  showRuntimeTopologySummary?: boolean;
  compactNodes?: boolean;
  selectedCardId?: string | null;
  onCardSelect?: (cardId: string) => void;
  onGraphChange?: (graph: TaskCardGraph) => void;
  className?: string;
}

export function TaskCardGraphCanvas({
  cardGraph,
  agents = EMPTY_AGENT_HANDLES,
  runtime,
  preferredProvider,
  showRuntimeTopologySummary = true,
  compactNodes = false,
  selectedCardId,
  onCardSelect,
  onGraphChange,
  className,
}: TaskCardGraphCanvasProps) {
  return (
    <div
      className={cn(
        "relative h-[520px] overflow-hidden rounded-xl border",
        className,
      )}
      data-testid="task-card-graph-panel"
    >
      {showRuntimeTopologySummary ? (
        <RuntimeTopologySummary preferredProvider={preferredProvider} runtime={runtime} />
      ) : null}
      <ReactFlowProvider>
        <TaskCardGraphInner
          agents={agents}
          cardGraph={cardGraph}
          compactNodes={compactNodes}
          onCardSelect={onCardSelect}
          onGraphChange={onGraphChange}
          runtime={runtime}
          selectedCardId={selectedCardId}
        />
      </ReactFlowProvider>
    </div>
  );
}
