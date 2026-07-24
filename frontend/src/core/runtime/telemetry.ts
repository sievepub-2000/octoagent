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
  memoryGuardTruncated: string;
  memoryGuardTruncatedTitle: string;
  memoryGuardTruncatedDetail: string;
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

function getModelCapability(
  runtime: RuntimeCapabilities | null | undefined,
  modelName: string | null | undefined,
): RuntimeModelCapability | null {
  if (!runtime || !hasText(modelName)) {
    return null;
  }
  return runtime.models.find((model) => model.name === modelName) ?? null;
}

function getDefaultModelCapability(
  runtime?: RuntimeCapabilities | null,
): RuntimeModelCapability | null {
  return getModelCapability(runtime, runtime?.default_model);
}

function getSelectedModelCapability(
  runtime: RuntimeCapabilities | null | undefined,
  selectedModelName?: string | null,
): RuntimeModelCapability | null {
  return getModelCapability(runtime, selectedModelName) ?? getDefaultModelCapability(runtime);
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

function hasContextGuardTruncation(threadState: AgentThreadState) {
  return (
    threadState.runtime?.recommended_memory_action === "truncate_oversized_messages" ||
    threadState.runtime?.context_guard_state === "truncated" ||
    threadState.runtime?.context_guard_state === "trimmed" ||
    threadState.runtime?.context_guard_state === "compacted"
  );
}

function formatMemoryGuardSummary(
  runtime: RuntimeCapabilities | null | undefined,
  threadState: AgentThreadState,
) {
  return formatMemoryGuardState(runtime, threadState);
}

function formatPrimaryModel(
  threadState: AgentThreadState,
  runtime: RuntimeCapabilities | null | undefined,
  copy: RuntimeTelemetryCopy,
  selectedModelName?: string | null,
) {
  const selectedModel = getSelectedModelCapability(runtime, selectedModelName);
  if (selectedModel) {
    return selectedModel.display_name ?? selectedModel.name;
  }
  const persistedPrimaryModel = threadState.runtime?.primary_model?.trim();
  if (persistedPrimaryModel) {
    return persistedPrimaryModel;
  }
  const activeModel = threadState.runtime?.active_model?.trim();
  if (activeModel) {
    return activeModel;
  }
  return copy.unavailable;
}

function primaryModelTone(
  threadState: AgentThreadState,
  runtime: RuntimeCapabilities | null | undefined,
  selectedModelName?: string | null,
) {
  const selectedModel = selectedModelName ?? runtime?.default_model;
  const activeModel = threadState.runtime?.active_model;
  const primaryModel = threadState.runtime?.primary_model;
  if (hasText(selectedModel) || hasText(activeModel) || hasText(primaryModel)) {
    return "success" as const;
  }
  return "warning" as const;
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
  selectedModelName?: string | null,
): RuntimeSummaryItem[] {
  if (!copy) {
    return [];
  }
  const defaultModel = getDefaultModelCapability(runtime);
  const fallbackReady = fallbackReadyState(threadState, defaultModel);
  const items: RuntimeSummaryItem[] = [
    {
      id: "primary-model",
      label: copy.primaryModel,
      value: formatPrimaryModel(threadState, runtime, copy, selectedModelName),
      tone: primaryModelTone(threadState, runtime, selectedModelName),
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
      value: formatMemoryGuardSummary(runtime, threadState),
      tone: memoryGuardTone(runtime, threadState),
    },
    {
      id: "agent-budget",
      label: copy.agentBudget,
      value: formatAgentBudget(runtime, copy),
      tone: agentBudgetTone(runtime),
    },
  ];
  if (hasContextGuardTruncation(threadState)) {
    items.splice(5, 0, {
      id: "context-guard",
      label: copy.memoryGuardTruncatedTitle,
      value: copy.memoryGuardTruncated,
      tone: "warning",
    });
  }
  return items;
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
  }

  if (hasContextGuardTruncation(threadState)) {
    events.push(
      createWorkflowEvent(
        "runtime_degraded",
        copy.memoryGuardTruncatedTitle,
        copy.memoryGuardTruncatedDetail,
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
  selectedModelName?: string | null,
): ThreadRuntimeState {
  const defaultModel = getDefaultModelCapability(runtime);
  const selectedModel = getSelectedModelCapability(runtime, selectedModelName);
  const workflowCount = threadState.workflows?.length ?? 0;
  const persistedPrimaryModel = threadState.runtime?.primary_model;
  const resolvedPrimaryModel =
    selectedModel?.display_name ??
    selectedModel?.name ??
    persistedPrimaryModel ??
    null;
  const resolvedActiveModel =
    selectedModelName ??
    runtime?.default_model ??
    selectedModel?.name ??
    resolvedPrimaryModel;

  return {
    primary_model: resolvedPrimaryModel,
    active_model: resolvedActiveModel,
    fallback_chain:
      threadState.runtime?.fallback_chain ??
      defaultModel?.effective_fallback_models ??
      [],
    fallback_ready:
      threadState.runtime?.fallback_ready ??
      defaultModel?.degraded_mode_supported ??
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
            memoryGuardTruncated: "",
            memoryGuardTruncatedTitle: "",
            memoryGuardTruncatedDetail: "",
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
    context_pressure: threadState.runtime?.context_pressure ?? null,
    recommended_memory_action:
      threadState.runtime?.recommended_memory_action ?? null,
    task_state_status: threadState.runtime?.task_state_status ?? null,
    recoverable_failure: threadState.runtime?.recoverable_failure ?? null,
    incomplete_state: threadState.runtime?.incomplete_state ?? null,
    instruction_contract: threadState.runtime?.instruction_contract ?? null,
    memory_write: threadState.runtime?.memory_write ?? null,
    last_run_record: threadState.runtime?.last_run_record ?? null,
    compaction_strategy: threadState.runtime?.compaction_strategy ?? null,
    compaction_trigger: threadState.runtime?.compaction_trigger ?? null,
    pressure_ratio: threadState.runtime?.pressure_ratio ?? null,
    updated_at: new Date().toISOString(),
  };
}
