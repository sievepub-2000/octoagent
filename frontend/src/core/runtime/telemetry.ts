import type {
  AgentThreadState,
  ThreadRuntimeState,
} from "@/core/threads";
import {
  createWorkflowEvent,
  type WorkflowEvent,
} from "@/core/workflows";

import type { RuntimeCapabilities, RuntimeModelCapability } from "./types";

export type RuntimeTelemetryCopy = {
  primaryModel: string;
  fallbackChain: string;
  continuation: string;
  workflowState: string;
  agentBudget: string;
  agentBudgetValue: (
    maxActivePerThread: number,
    maxTotalPerThread: number,
    maxConcurrentGlobal: number,
  ) => string;
  memoryGuard: string;
  unavailable: string;
  noFallbackChain: string;
  freshThread: string;
  noSavedWorkflow: string;
  workflowResumed: (count: number) => string;
  workflowLoaded: (count: number) => string;
  continuationLoadedTitle: string;
  continuationLoadedDetail: (source: string) => string;
  workflowRestoredTitle: string;
  workflowRestoredDetail: (count: number) => string;
  fallbackReadyTitle: string;
  fallbackReadyDetail: (model: string, chain: string) => string;
  memoryGuardTightTitle: string;
  memoryGuardTightDetail: string;
  embeddedBackupOnlyTitle: string;
  embeddedBackupOnlyDetail: string;
};

export type RuntimeSummaryItem = {
  id: string;
  label: string;
  value: string;
  tone: "default" | "success" | "warning";
};

function hasText(value: string | null | undefined): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function getDefaultModelCapability(
  runtime?: RuntimeCapabilities | null,
): RuntimeModelCapability | null {
  if (!runtime?.default_model) {
    return null;
  }
  return (
    runtime.models.find((model) => model.name === runtime.default_model) ?? null
  );
}

function formatFallbackChain(model: RuntimeModelCapability | null) {
  if (!model) {
    return null;
  }
  if (model.effective_fallback_models.length === 0) {
    return null;
  }
  return model.effective_fallback_models.join(" -> ");
}

function getPersistedFallbackChain(threadState: AgentThreadState) {
  const fallbackChain = threadState.runtime?.fallback_chain ?? [];
  if (fallbackChain.length === 0) {
    return null;
  }
  return fallbackChain.join(" -> ");
}

function formatMemoryGuardState(
  runtime: RuntimeCapabilities | null | undefined,
  threadState: AgentThreadState,
) {
  return (
    runtime?.runtime_status.memory_guard_state ??
    threadState.runtime?.memory_guard_state ??
    "unknown"
  );
}

function memoryGuardTone(
  runtime: RuntimeCapabilities | null | undefined,
  threadState: AgentThreadState,
): RuntimeSummaryItem["tone"] {
  const state = formatMemoryGuardState(runtime, threadState);
  if (state === "tight") {
    return "warning";
  }
  if (state === "ok") {
    return "success";
  }
  return "default";
}

function formatPrimaryModel(
  threadState: AgentThreadState,
  runtime: RuntimeCapabilities | null | undefined,
  copy: RuntimeTelemetryCopy,
) {
  const activeModel = threadState.runtime?.active_model?.trim();
  if (activeModel) {
    return activeModel;
  }
  const persistedPrimaryModel = threadState.runtime?.primary_model?.trim();
  if (persistedPrimaryModel) {
    return persistedPrimaryModel;
  }
  const defaultModel = getDefaultModelCapability(runtime);
  return defaultModel?.display_name ?? defaultModel?.name ?? copy.unavailable;
}

function primaryModelTone(
  threadState: AgentThreadState,
  runtime: RuntimeCapabilities | null | undefined,
) {
  const activeModel = threadState.runtime?.active_model;
  const primaryModel = threadState.runtime?.primary_model;
  if (!hasText(activeModel) && !hasText(primaryModel) && !runtime?.default_model) {
    return "warning" as const;
  }
  if (hasText(activeModel) && hasText(primaryModel) && activeModel !== primaryModel) {
    return "warning" as const;
  }
  if (hasText(activeModel) || hasText(primaryModel) || runtime?.default_model) {
    return "success" as const;
  }
  return "default" as const;
}

function formatContinuation(
  threadState: AgentThreadState,
  copy: RuntimeTelemetryCopy,
): string {
  const freshThreadLabel = copy.freshThread ?? "";
  const continuationSource = threadState.runtime?.continuation_source;
  if (hasText(continuationSource)) {
    return continuationSource;
  }
  const continuation = threadState.continuation;
  if (!continuation) {
    return freshThreadLabel;
  }
  return continuation.source_title ?? continuation.source_thread_id ?? freshThreadLabel;
}

function formatWorkflowResume(threadState: AgentThreadState, copy: RuntimeTelemetryCopy) {
  const workflowCount = threadState.workflows?.length ?? 0;
  const persistedState = threadState.runtime?.workflow_resume_state;
  if (persistedState === "resumed") {
    return workflowCount > 0
      ? copy.workflowResumed(workflowCount)
      : copy.noSavedWorkflow;
  }
  if (persistedState === "loaded") {
    return workflowCount > 0
      ? copy.workflowLoaded(workflowCount)
      : copy.noSavedWorkflow;
  }
  if (persistedState === "fresh") {
    return copy.noSavedWorkflow;
  }
  if (workflowCount === 0) {
    return copy.noSavedWorkflow;
  }
  if (threadState.continuation) {
    return copy.workflowResumed(workflowCount);
  }
  return copy.workflowLoaded(workflowCount);
}

function formatAgentBudget(
  runtime: RuntimeCapabilities | null | undefined,
  copy: RuntimeTelemetryCopy,
) {
  if (!runtime) {
    return copy.unavailable;
  }
  return copy.agentBudgetValue(
    runtime.agent_limits.max_active_subagents_per_thread,
    runtime.agent_limits.max_total_subagents_per_thread,
    runtime.agent_limits.max_concurrent_subagents,
  );
}

function agentBudgetTone(runtime: RuntimeCapabilities | null | undefined) {
  if (!runtime) {
    return "warning" as const;
  }
  const limits = runtime.agent_limits;
  if (
    limits.max_active_subagents_per_thread <= 0 ||
    limits.max_total_subagents_per_thread <= 0 ||
    limits.max_concurrent_subagents <= 0
  ) {
    return "warning" as const;
  }
  return "default" as const;
}

function fallbackReadyState(
  threadState: AgentThreadState,
  defaultModel: RuntimeModelCapability | null,
) {
  return threadState.runtime?.fallback_ready ?? defaultModel?.degraded_mode_supported ?? false;
}

function formatFallbackState(
  threadState: AgentThreadState,
  defaultModel: RuntimeModelCapability | null,
  copy: RuntimeTelemetryCopy,
) {
  return getPersistedFallbackChain(threadState) ?? formatFallbackChain(defaultModel) ?? copy.noFallbackChain;
}

function workflowStateTone(threadState: AgentThreadState) {
  const persistedState = threadState.runtime?.workflow_resume_state;
  if (persistedState === "loaded" || persistedState === "resumed") {
    return "success" as const;
  }
  return (threadState.workflows?.length ?? 0) > 0 ? "success" as const : "default" as const;
}

export function buildRuntimeSummaryItems(
  threadState: AgentThreadState,
  runtime?: RuntimeCapabilities | null,
  copy?: RuntimeTelemetryCopy,
): RuntimeSummaryItem[] {
  if (!copy) {
    return [];
  }
  const defaultModel = getDefaultModelCapability(runtime);
  const memoryGuardState = formatMemoryGuardState(runtime, threadState);
  const fallbackReady = fallbackReadyState(threadState, defaultModel);
  return [
    {
      id: "primary-model",
      label: copy.primaryModel,
      value: formatPrimaryModel(threadState, runtime, copy),
      tone: primaryModelTone(threadState, runtime),
    },
    {
      id: "fallback-chain",
      label: copy.fallbackChain,
      value: formatFallbackState(threadState, defaultModel, copy),
      tone: fallbackReady ? "success" : "warning",
    },
    {
      id: "continuation",
      label: copy.continuation,
      value: formatContinuation(threadState, copy),
      tone:
        threadState.continuation || hasText(threadState.runtime?.continuation_source)
          ? "success"
          : "default",
    },
    {
      id: "workflow-state",
      label: copy.workflowState,
      value: formatWorkflowResume(threadState, copy),
      tone: workflowStateTone(threadState),
    },
    {
      id: "memory-guard",
      label: copy.memoryGuard,
      value: memoryGuardState,
      tone: memoryGuardTone(runtime, threadState),
    },
    {
      id: "agent-budget",
      label: copy.agentBudget,
      value: formatAgentBudget(runtime, copy),
      tone: agentBudgetTone(runtime),
    },
  ];
}

export function buildRuntimeTelemetryEvents(
  threadState: AgentThreadState,
  runtime?: RuntimeCapabilities | null,
  copy?: RuntimeTelemetryCopy,
): WorkflowEvent[] {
  if (!copy) {
    return [];
  }
  const defaultModel = getDefaultModelCapability(runtime);
  const events: WorkflowEvent[] = [];

  if (threadState.continuation) {
    events.push(
      createWorkflowEvent(
        "continuation_loaded",
        copy.continuationLoadedTitle,
        copy.continuationLoadedDetail(formatContinuation(threadState, copy)),
        "info",
      ),
    );
  }

  if (threadState.continuation && (threadState.workflows?.length ?? 0) > 0) {
    events.push(
      createWorkflowEvent(
        "workflow_resumed",
        copy.workflowRestoredTitle,
        copy.workflowRestoredDetail(threadState.workflows?.length ?? 0),
        "success",
      ),
    );
  }

  if (defaultModel?.degraded_mode_supported) {
    events.push(
      createWorkflowEvent(
        "runtime_ready",
        copy.fallbackReadyTitle,
        copy.fallbackReadyDetail(
          defaultModel.name,
          formatFallbackChain(defaultModel) ?? copy.noFallbackChain,
        ),
        "info",
      ),
    );
  }

  if (runtime?.runtime_status.memory_guard_state === "tight") {
    events.push(
      createWorkflowEvent(
        "runtime_degraded",
        copy.memoryGuardTightTitle,
        copy.memoryGuardTightDetail,
        "warning",
      ),
    );
  } else if (!runtime?.default_model && runtime?.embedded_backup_enabled) {
    events.push(
      createWorkflowEvent(
        "runtime_degraded",
        copy.embeddedBackupOnlyTitle,
        copy.embeddedBackupOnlyDetail,
        "warning",
      ),
    );
  }

  return events;
}

export function buildThreadRuntimeTelemetry(
  threadState: AgentThreadState,
  runtime?: RuntimeCapabilities | null,
  copy?: RuntimeTelemetryCopy,
): ThreadRuntimeState {
  const defaultModel = getDefaultModelCapability(runtime);
  const workflowCount = threadState.workflows?.length ?? 0;
  const persistedPrimaryModel = threadState.runtime?.primary_model;
  const persistedActiveModel = threadState.runtime?.active_model;

  return {
    primary_model:
      persistedPrimaryModel ??
      defaultModel?.display_name ??
      defaultModel?.name ??
      null,
    active_model:
      persistedActiveModel ??
      persistedPrimaryModel ??
      defaultModel?.name ??
      null,
    fallback_chain:
      threadState.runtime?.fallback_chain ??
      defaultModel?.effective_fallback_models ??
      [],
    fallback_ready:
      threadState.runtime?.fallback_ready ??
      defaultModel?.degraded_mode_supported ??
      false,
    embedded_backup_enabled:
      runtime?.embedded_backup_enabled ??
      threadState.runtime?.embedded_backup_enabled ??
      false,
    continuation_source: threadState.continuation
      ? formatContinuation(
          threadState,
          copy ?? {
            primaryModel: "",
            fallbackChain: "",
            continuation: "",
            workflowState: "",
            agentBudget: "",
            agentBudgetValue: () => "",
            memoryGuard: "",
            unavailable: "Unavailable",
            noFallbackChain: "No fallback chain",
            freshThread: "Fresh thread",
            noSavedWorkflow: "No saved workflow",
            workflowResumed: (count) => `${count} resumed`,
            workflowLoaded: (count) => `${count} loaded`,
            continuationLoadedTitle: "",
            continuationLoadedDetail: (source) => source,
            workflowRestoredTitle: "",
            workflowRestoredDetail: (count) => `${count}`,
            fallbackReadyTitle: "",
            fallbackReadyDetail: (model, chain) => `${model} ${chain}`,
            memoryGuardTightTitle: "",
            memoryGuardTightDetail: "",
            embeddedBackupOnlyTitle: "",
            embeddedBackupOnlyDetail: "",
          },
        )
      : threadState.runtime?.continuation_source ?? null,
    workflow_resume_state:
      threadState.runtime?.workflow_resume_state ??
      workflowCount === 0
        ? "fresh"
        : threadState.continuation || hasText(threadState.runtime?.continuation_source)
          ? "resumed"
          : "loaded",
    memory_guard_state:
      runtime?.runtime_status.memory_guard_state ??
      threadState.runtime?.memory_guard_state ??
      "unknown",
    updated_at: new Date().toISOString(),
  };
}
