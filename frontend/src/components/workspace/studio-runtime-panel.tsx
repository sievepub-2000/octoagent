"use client";

import React from "react";

import { formatTaskRuntimeProvider } from "@/core/task-workspaces/runtime-provider";
import type {
  TaskAgentRuntimeProvider,
  TaskStudioRuntimeResponse,
} from "@/core/task-workspaces/types";

/* ------------------------------------------------------------------ */
/* Studio Runtime Panel — normalized data display (Rowboat-inspired)   */
/* ------------------------------------------------------------------ */

interface StudioRuntimePanelProps {
  runtime: TaskStudioRuntimeResponse;
  className?: string;
  preferredProvider?: TaskAgentRuntimeProvider;
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    running: "bg-green-500/20 text-green-400 border-green-500/30",
    completed: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    failed: "bg-red-500/20 text-red-400 border-red-500/30",
    waiting_review: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    paused: "bg-orange-500/20 text-orange-400 border-orange-500/30",
    idle: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
  };
  const colorClass = colors[status] ?? colors.idle;
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${colorClass}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string | number;
  detail?: string | null;
}) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border border-zinc-700/50 bg-zinc-800/50 px-3 py-2">
      <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
        {label}
      </span>
      <span className="text-sm font-semibold text-zinc-200">{value}</span>
      {detail && (
        <span className="truncate text-[11px] text-zinc-500">{detail}</span>
      )}
    </div>
  );
}

export function StudioRuntimePanel({
  runtime,
  className,
  preferredProvider,
}: StudioRuntimePanelProps) {
  const rs = runtime.runtime_summary;
  const rd = runtime.readiness;
  const ws = runtime.workflow_summary;
  const lastProviderLabel = formatTaskRuntimeProvider(rs.last_runtime_provider ?? preferredProvider);
  const langGraphAssistant = rs.last_langgraph_assistant_id ?? runtime.agents.find((agent) => agent.langgraph_assistant_id)?.langgraph_assistant_id ?? null;

  return (
    <section
      className={`flex flex-col gap-4 ${className ?? ""}`}
      aria-label="Studio Runtime"
      data-testid="studio-runtime-panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-zinc-200">Runtime</h3>
          <StatusBadge status={runtime.status} />
        </div>
        {rs.current_phase && (
          <span className="text-xs text-zinc-500">
            phase: {rs.current_phase}
          </span>
        )}
      </div>

      {/* Metric grid */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        <MetricCard
          label="Agents"
          value={runtime.agents.length}
          detail={`${runtime.agents.filter((a) => a.status === "running" || a.status === "waiting_handoff").length} active`}
        />
        <MetricCard
          label="Cards"
          value={ws.cards_total}
          detail={`${ws.completed_cards} done · ${ws.blocked_cards} blocked`}
        />
        <MetricCard
          label="Sessions"
          value={`${rs.active_query_sessions ?? 0}/${rs.active_runtime_sessions ?? 0}`}
          detail="query / runtime"
        />
        <MetricCard
          label="Agent Runtime"
          value={lastProviderLabel}
          detail={rs.last_execution_target ?? "No execution target recorded yet"}
        />
        <MetricCard
          label="Handoffs"
          value={rd.active_handoffs}
          detail={`${runtime.handoffs.length} total`}
        />
        <MetricCard
          label="Bindings"
          value={rd.enabled_bindings}
          detail={`ch=${runtime.bindings.channels.length} mcp=${runtime.bindings.mcp_servers.length}`}
        />
        <MetricCard
          label="Artifacts"
          value={rd.artifact_count}
        />
        <MetricCard
          label="Checkpoints"
          value={runtime.checkpoints_summary.total}
          detail={runtime.checkpoints_summary.ready_for_review ? "ready for review" : undefined}
        />
        <MetricCard
          label="Memory"
          value={rs.memory_guard_state ?? "unknown"}
          detail={rs.project_memory_updated_at ? `updated ${rs.project_memory_updated_at}` : undefined}
        />
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <MetricCard
          label="LangGraph Graph"
          value={rs.langgraph_graph_id ?? "uncompiled"}
          detail={rs.langgraph_native_runtime ? "native workflow runtime" : "compat workflow runtime"}
        />
        <MetricCard
          label="Assistant Binding"
          value={langGraphAssistant ?? "lead_agent"}
          detail={rs.langgraph_thread_scope ? `thread scope: ${rs.langgraph_thread_scope}` : undefined}
        />
      </div>

      {/* Agent table */}
      {runtime.agents.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs" role="table">
            <thead>
              <tr className="border-b border-zinc-700/50 text-zinc-500">
                <th scope="col" className="pb-1.5 pr-3 font-medium">Agent</th>
                <th scope="col" className="pb-1.5 pr-3 font-medium">Role</th>
                <th scope="col" className="pb-1.5 pr-3 font-medium">Status</th>
                <th scope="col" className="pb-1.5 pr-3 font-medium">Runtime</th>
                <th scope="col" className="pb-1.5 pr-3 font-medium">Model</th>
                <th scope="col" className="pb-1.5 font-medium text-right">Msgs</th>
              </tr>
            </thead>
            <tbody>
              {runtime.agents.map((agent) => (
                <tr
                  key={agent.agent_id}
                  className="border-b border-zinc-800/50 text-zinc-300"
                >
                  <td className="py-1.5 pr-3 font-medium">{agent.name}</td>
                  <td className="py-1.5 pr-3 text-zinc-400">{agent.role}</td>
                  <td className="py-1.5 pr-3">
                    <StatusBadge status={agent.status} />
                  </td>
                  <td className="py-1.5 pr-3 text-zinc-400">
                    <div>{formatTaskRuntimeProvider(agent.last_runtime_provider)}</div>
                    {(agent.langgraph_assistant_id ?? agent.langgraph_thread_scope) ? (
                      <div className="text-[11px] text-zinc-500">
                        {[agent.langgraph_assistant_id, agent.langgraph_thread_scope].filter(Boolean).join(" · ")}
                      </div>
                    ) : null}
                  </td>
                  <td className="py-1.5 pr-3 text-zinc-500">
                    {agent.model_name ?? "—"}
                  </td>
                  <td className="py-1.5 text-right text-zinc-400">
                    {agent.message_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Readiness summary */}
      <div className="flex flex-wrap gap-2 text-[11px] text-zinc-500">
        {rd.can_run && <span className="text-green-400">▸ can run</span>}
        {rd.can_resume && <span className="text-yellow-400">▸ can resume</span>}
        {rd.requires_review && (
          <span className="text-orange-400">▸ review required</span>
        )}
        <span>
          last provider: {lastProviderLabel}
        </span>
        <span>
          last sync: {rs.last_runtime_sync_at ?? "—"}
        </span>
        <span>
          workflow graph: {rs.langgraph_graph_id ?? "uncompiled"}
        </span>
      </div>
    </section>
  );
}

export default StudioRuntimePanel;
