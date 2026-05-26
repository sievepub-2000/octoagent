"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { ChatStatus } from "ai";
import {
  BotIcon,
  CheckIcon,
  GraduationCapIcon,
  LightbulbIcon,
  MicIcon,
  MicOffIcon,
  PaperclipIcon,
  PlusIcon,
  ShieldCheckIcon,
  ShieldQuestionIcon,
  ShieldIcon,
  SparklesIcon,
  RocketIcon,
  UserIcon,
  XIcon,
  ZapIcon,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
} from "react";
import { toast } from "sonner";

import {
  PromptInput,
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuItem,
  PromptInputActionMenuTrigger,
  PromptInputAttachment,
  PromptInputAttachments,
  PromptInputBody,
  PromptInputButton,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  usePromptInputAttachments,
  usePromptInputController,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";
import { ConfettiButton } from "@/components/ui/confetti-button";
import {
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { useAgents } from "@/core/agents/hooks";
import {
  CONTEXT_AUTO_COMPACT_THRESHOLD,
  computeContextTokenUsage,
  type ContextTokenUsage,
} from "@/core/context/context-token-counter";
import { useI18n } from "@/core/i18n/hooks";
import { useModels } from "@/core/models/hooks";
import { useLocalSettings } from "@/core/settings/hooks";
import { useApplySetup, useSetupStatus } from "@/core/setup/hooks";
import type { AgentThreadContext, AgentThreadState } from "@/core/threads";
import { useVoiceInput } from "@/hooks/use-voice-input";
import { cn } from "@/lib/utils";

import {
  ModelSelector,
  ModelSelectorContent,
  ModelSelectorEmpty,
  ModelSelectorGroup,
  ModelSelectorInput,
  ModelSelectorItem,
  ModelSelectorList,
  ModelSelectorName,
  ModelSelectorSeparator,
  ModelSelectorTrigger,
} from "../ai-elements/model-selector";
import { Suggestion, Suggestions } from "../ai-elements/suggestion";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";

import { ModeHoverGuide } from "./mode-hover-guide";

type InputMode = "flash" | "thinking" | "pro" | "ultra";
type ReasoningEffort = "minimal" | "low" | "medium" | "high";
type PermissionMode = "approval" | "directory" | "system";

const PERMISSION_MODE_OPTIONS: Array<{
  value: PermissionMode;
  label: string;
  detail: string;
  icon: typeof ShieldQuestionIcon;
}> = [
  {
    value: "approval",
    label: "审批",
    detail: "默认审批；隐藏系统级工具，敏感操作先请求确认。",
    icon: ShieldQuestionIcon,
  },
  {
    value: "directory",
    label: "目录",
    detail: "允许仓库/任务目录内操作；不暴露 host/system 工具。",
    icon: ShieldCheckIcon,
  },
  {
    value: "system",
    label: "系统",
    detail: "允许系统级 host/shell/network/process 工具，所有命令可追踪。",
    icon: ShieldIcon,
  },
];

function normalizePermissionMode(value: unknown): PermissionMode {
  if (value === "system" || value === "yolo") return "system";
  if (value === "directory" || value === "workspace") return "directory";
  return "approval";
}

function normalizeLegacyMode(
  mode: InputMode | undefined,
  reasoningEffort?: ReasoningEffort,
): InputMode | undefined {
  // Older builds auto-saved Pro mode without an effort value. Treat that as
  // an unset default so simple prompts stay fast after upgrades.
  if (mode === "pro" && (!reasoningEffort || reasoningEffort === "minimal")) {
    return undefined;
  }
  return mode;
}

function getResolvedMode(
  mode: InputMode | undefined,
  supportsThinking: boolean,
): InputMode {
  if (!supportsThinking && mode !== "flash") {
    return "flash";
  }
  return mode ?? "flash";
}

function getDefaultReasoningEffort(mode: InputMode): ReasoningEffort {
  if (mode === "ultra") return "high";
  if (mode === "pro") return "medium";
  if (mode === "thinking") return "low";
  return "minimal";
}

function formatTokenCount(tokens: number): string {
  if (!Number.isFinite(tokens) || tokens <= 0) return "0";
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 10_000) return `${Math.round(tokens / 1_000)}K`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}K`;
  return `${Math.round(tokens)}`;
}

export function InputBox({
  className,
  disabled,
  autoFocus,
  status = "ready",
  context,
  extraHeader,
  isNewThread,
  initialValue,
  threadState,
  threadId,
  contextCycleBaseTokens = 0,
  onContextChange,
  onContextThreshold,
  onSubmit,
  onStop,
  ...props
}: Omit<ComponentProps<typeof PromptInput>, "onSubmit"> & {
  assistantId?: string | null;
  status?: ChatStatus;
  disabled?: boolean;
  context: Omit<
    AgentThreadContext,
    "thread_id" | "is_plan_mode" | "thinking_enabled" | "subagent_enabled"
  > & {
    mode: "flash" | "thinking" | "pro" | "ultra" | undefined;
    reasoning_effort?: "minimal" | "low" | "medium" | "high";
    permission_mode?: PermissionMode;
  };
  extraHeader?: React.ReactNode;
  isNewThread?: boolean;
  threadId: string;
  initialValue?: string;
  threadState?: AgentThreadState;
  contextCycleBaseTokens?: number;
  onContextChange?: (
    context: Omit<
      AgentThreadContext,
      "thread_id" | "is_plan_mode" | "thinking_enabled" | "subagent_enabled"
    > & {
      mode: "flash" | "thinking" | "pro" | "ultra" | undefined;
      reasoning_effort?: "minimal" | "low" | "medium" | "high";
      permission_mode?: PermissionMode;
    },
  ) => void;
  onContextThreshold?: (usage: ContextTokenUsage) => void;
  onSubmit?: (message: PromptInputMessage) => void;
  onStop?: () => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const [modelDialogOpen, setModelDialogOpen] = useState(false);
  const [localSettings, setLocalSettings] = useLocalSettings();
  const { models } = useModels();
  const { status: setupStatus } = useSetupStatus();
  const applySetup = useApplySetup();
  const { agents } = useAgents();
  const { textInput } = usePromptInputController();
  const promptRootRef = useRef<HTMLDivElement | null>(null);
  const autoCompactTriggeredRef = useRef(false);
  const [draftText, setDraftText] = useState(initialValue ?? "");
  const [queuedMessage, setQueuedMessage] = useState<PromptInputMessage | null>(null);
  const configuredWorkspacePath =
    setupStatus?.workspace_path.trim()
      ? setupStatus.workspace_path
      : localSettings.setup.workspace_path;
  const configuredSandboxMode =
    setupStatus?.configured_sandbox_mode ?? localSettings.setup.sandbox_mode ?? "local";
  const configuredDefaultModelName =
    setupStatus?.configured_default_model.trim()
      ? setupStatus.configured_default_model
      : localSettings.setup.default_model;

  // Agent selector
  const selectedAgent = useMemo(() => {
    if (!context.agent_name) return null;
    return agents.find((a) => a.name === context.agent_name) ?? null;
  }, [context.agent_name, agents]);

  const handleAgentSelect = useCallback(
    (agentName: string | undefined) => {
      if (!agentName) {
        // Switch to default (clear agent)
        onContextChange?.({
          ...context,
          agent_name: undefined,
        });
        return;
      }
      const agent = agents.find((a) => a.name === agentName);
      if (!agent) return;
      // Set agent and sync model if agent has one configured
      const nextModelName = agent.model ?? context.model_name;
      const nextModel = models.find((m) => m.name === nextModelName);
      const supportsThinking = nextModel?.supports_thinking ?? false;
      const nextMode = getResolvedMode(
        normalizeLegacyMode(context.mode, context.reasoning_effort),
        supportsThinking,
      );
      onContextChange?.({
        ...context,
        agent_name: agentName,
        model_name: nextModelName,
        mode: nextMode,
        reasoning_effort: getDefaultReasoningEffort(nextMode),
      });
    },
    [onContextChange, context, agents, models],
  );

  const explicitModel = useMemo(() => {
    if (!context.model_name) {
      return null;
    }
    return models.find((m) => m.name === context.model_name) ?? null;
  }, [context.model_name, models]);

  const systemDefaultModel = useMemo(() => {
    const configuredModel = configuredDefaultModelName.trim();
    if (configuredModel.length > 0) {
      const matchedModel = models.find((m) => m.name === configuredModel);
      if (matchedModel) {
        return matchedModel;
      }
    }
    return models[0] ?? null;
  }, [configuredDefaultModelName, models]);

  // Voice input
  const { isSupported: voiceSupported, isListening, toggle: toggleVoice, interimTranscript } = useVoiceInput(
    undefined,
    useCallback((text: string) => {
      const current = textInput.value;
      textInput.setInput(current ? `${current} ${text}` : text);
    }, [textInput]),
  );

  useEffect(() => {
    if (models.length === 0) {
      return;
    }
    const fallbackModel = explicitModel ?? systemDefaultModel ?? models[0] ?? null;
    if (!fallbackModel) {
      return;
    }
    const supportsThinking = fallbackModel.supports_thinking ?? false;
    const requestedMode = normalizeLegacyMode(context.mode, context.reasoning_effort);
    const nextMode = getResolvedMode(requestedMode, supportsThinking);
    const nextReasoningEffort =
      context.mode === nextMode && context.reasoning_effort
        ? context.reasoning_effort
        : getDefaultReasoningEffort(nextMode);
    const nextModelName = explicitModel?.name;

    if (
      context.model_name === nextModelName &&
      context.mode === nextMode &&
      context.reasoning_effort === nextReasoningEffort
    ) {
      return;
    }

    onContextChange?.({
      ...context,
      model_name: nextModelName,
      mode: nextMode,
      reasoning_effort: nextReasoningEffort,
    });
  }, [context, explicitModel, models, onContextChange, systemDefaultModel]);

  const selectedModel = useMemo(() => {
    return explicitModel ?? systemDefaultModel ?? undefined;
  }, [explicitModel, systemDefaultModel]);

  const usingSystemDefault = explicitModel == null;

  const supportThinking = useMemo(
    () => selectedModel?.supports_thinking ?? false,
    [selectedModel],
  );

  const supportReasoningEffort = useMemo(
    () => selectedModel?.supports_reasoning_effort ?? false,
    [selectedModel],
  );

  const contextUsage = useMemo(
    () => computeContextTokenUsage({
      state: threadState,
      draftText: textInput.value || draftText,
      maxTokens: selectedModel?.max_context_tokens,
      cycleBaseTokens: contextCycleBaseTokens,
      thresholdRatio: CONTEXT_AUTO_COMPACT_THRESHOLD,
    }),
    [contextCycleBaseTokens, draftText, selectedModel?.max_context_tokens, textInput.value, threadState],
  );
  const contextTokenLabel = contextUsage.maxTokens === null
    ? `${formatTokenCount(contextUsage.rawUsedTokens)} tok`
    : `${formatTokenCount(contextUsage.usedTokens)} / ${formatTokenCount(contextUsage.maxTokens)} tok`;
  const contextTokenTitle = contextUsage.maxTokens === null
    ? `Estimated context tokens: ${contextUsage.rawUsedTokens.toLocaleString()}`
    : [
        `Estimated live context: ${contextUsage.usedTokens.toLocaleString()} tokens`,
        `Window: ${contextUsage.maxTokens.toLocaleString()} tokens`,
        contextUsage.cycleBaseTokens > 0
          ? `Compacted cycle base: ${contextUsage.cycleBaseTokens.toLocaleString()} tokens; raw estimate: ${contextUsage.rawUsedTokens.toLocaleString()} tokens`
          : `Raw estimate: ${contextUsage.rawUsedTokens.toLocaleString()} tokens`,
      ].join(" · ");

  useEffect(() => {
    autoCompactTriggeredRef.current = false;
  }, [contextCycleBaseTokens, threadId]);

  useEffect(() => {
    if (!contextUsage.shouldAutoCompact) {
      if (contextUsage.ratio < 0.75) {
        autoCompactTriggeredRef.current = false;
      }
      return;
    }
    if (autoCompactTriggeredRef.current || status !== "ready") {
      return;
    }
    autoCompactTriggeredRef.current = true;
    onContextThreshold?.(contextUsage);
  }, [contextUsage, onContextThreshold, status]);

  const effectiveMode = useMemo(
    () => getResolvedMode(
      normalizeLegacyMode(context.mode, context.reasoning_effort),
      supportThinking,
    ),
    [context.mode, context.reasoning_effort, supportThinking],
  );
  const effectivePermissionMode = normalizePermissionMode(context.permission_mode);
  const selectedPermissionMode = PERMISSION_MODE_OPTIONS.find((item) => item.value === effectivePermissionMode) ?? PERMISSION_MODE_OPTIONS[0]!;
  const SelectedPermissionIcon = selectedPermissionMode.icon;

  const handleModelSelect = useCallback(
    (model_name: string) => {
      const model = models.find((m) => m.name === model_name);
      if (!model) {
        return;
      }
      onContextChange?.({
        ...context,
        model_name,
        mode: getResolvedMode(
          normalizeLegacyMode(context.mode, context.reasoning_effort),
          model.supports_thinking ?? false,
        ),
        reasoning_effort: getDefaultReasoningEffort(
          getResolvedMode(
            normalizeLegacyMode(context.mode, context.reasoning_effort),
            model.supports_thinking ?? false,
          ),
        ),
      });
      setModelDialogOpen(false);
    },
    [onContextChange, context, models],
  );

  const handleUseSystemDefault = useCallback(() => {
    onContextChange?.({
      ...context,
      model_name: undefined,
      mode: getResolvedMode(
        normalizeLegacyMode(context.mode, context.reasoning_effort),
        systemDefaultModel?.supports_thinking ?? false,
      ),
      reasoning_effort: getDefaultReasoningEffort(
        getResolvedMode(
          normalizeLegacyMode(context.mode, context.reasoning_effort),
          systemDefaultModel?.supports_thinking ?? false,
        ),
      ),
    });
    setModelDialogOpen(false);
  }, [context, onContextChange, systemDefaultModel]);

  const handleSystemDefaultModelSelect = useCallback(
    async (modelName: string) => {
      if (configuredWorkspacePath.trim().length === 0) {
        toast.error("Workspace path is not configured yet.");
        return;
      }

      if (modelName === systemDefaultModel?.name) {
        setModelDialogOpen(false);
        return;
      }

      try {
        const result = await applySetup.mutateAsync({
          workspace_path: configuredWorkspacePath,
          default_model: modelName,
          sandbox_mode: configuredSandboxMode,
        });
        if (!result.success) {
          throw new Error(result.error || "Failed to update system default model.");
        }
        setLocalSettings("setup", {
          completed: true,
          default_model: result.default_model,
          sandbox_mode: result.sandbox_mode,
          workspace_path: result.workspace_path,
        });
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["setup-status"] }),
          queryClient.invalidateQueries({ queryKey: ["runtime-capabilities"] }),
        ]);
        setModelDialogOpen(false);
        toast.success(
          `System default model updated to ${
            models.find((model) => model.name === result.default_model)?.display_name
            ?? result.default_model
          }`,
        );
      } catch (setupError) {
        toast.error(
          setupError instanceof Error
            ? setupError.message
            : "Failed to update system default model.",
        );
      }
    },
    [
      applySetup,
      configuredSandboxMode,
      configuredWorkspacePath,
      models,
      queryClient,
      setLocalSettings,
      systemDefaultModel,
    ],
  );

  const formatModelProvider = useCallback((modelName?: string | null) => {
    const model = models.find((item) => item.name === modelName);
    if (!model) {
      return null;
    }
    return model.provider_name ?? model.resolved_provider_family ?? model.interface_type ?? null;
  }, [models]);

  const handleModeSelect = useCallback(
    (mode: InputMode) => {
      const nextMode = getResolvedMode(mode, supportThinking);
      onContextChange?.({
        ...context,
        mode: nextMode,
        reasoning_effort: getDefaultReasoningEffort(nextMode),
      });
    },
    [onContextChange, context, supportThinking],
  );

  const handleReasoningEffortSelect = useCallback(
    (effort: "minimal" | "low" | "medium" | "high") => {
      onContextChange?.({
        ...context,
        reasoning_effort: effort,
      });
    },
    [onContextChange, context],
  );

  const handlePermissionModeSelect = useCallback(
    (permission_mode: PermissionMode) => {
      onContextChange?.({
        ...context,
        permission_mode,
      });
      setLocalSettings("context", {
        ...localSettings.context,
        permission_mode,
      });
    },
    [context, localSettings.context, onContextChange, setLocalSettings],
  );

  useEffect(() => {
    if (status !== "ready" || !queuedMessage) {
      return;
    }
    const nextMessage = queuedMessage;
    setQueuedMessage(null);
    onSubmit?.(nextMessage);
  }, [onSubmit, queuedMessage, status]);

  const handleSubmit = useCallback(
    async (message: PromptInputMessage) => {
      if (!message.text) {
        if (status === "streaming") {
          onStop?.();
        }
        return;
      }
      if (status === "streaming") {
        setQueuedMessage(message);
        toast.info("Follow-up queued and will send after the current response finishes.");
        return;
      }
      onSubmit?.(message);
    },
    [onSubmit, onStop, status],
  );

  return (
    <div ref={promptRootRef} className="relative">
      <div className="sr-only" aria-live="polite">
        {contextUsage.maxTokens === null
          ? "Context usage is waiting for the selected model context window."
          : `Context usage ${contextUsage.percent}% of ${Math.round(contextUsage.maxTokens / 1000)}k tokens.`}
      </div>
      <PromptInput
        className={cn(
          "bg-background/85 rounded-2xl backdrop-blur-sm transition-all duration-300 ease-out *:data-[slot='input-group']:rounded-2xl",
          className,
        )}
        disabled={disabled}
        globalDrop
        multiple
        onSubmit={handleSubmit}
        {...props}
      >
        {extraHeader && (
          <div className="absolute top-0 right-0 left-0 z-10">
            <div className="absolute right-0 bottom-0 left-0 flex items-center justify-center">
              {extraHeader}
            </div>
          </div>
        )}
        {queuedMessage?.text ? (
          <div className="absolute -top-8 right-40 left-4 flex min-w-0 items-center gap-2 rounded-md border bg-background/95 px-2 py-1 shadow-sm">
            <span className="text-muted-foreground min-w-0 flex-1 truncate text-xs">
              Queued follow-up: {queuedMessage.text}
            </span>
            <button
              aria-label="Remove queued follow-up"
              className="text-muted-foreground rounded p-0.5 transition-colors hover:bg-muted hover:text-foreground"
              onClick={() => {
                setQueuedMessage(null);
                toast.info("Queued follow-up removed.");
              }}
              title="Remove queued follow-up"
              type="button"
            >
              <XIcon className="size-3" />
            </button>
          </div>
        ) : null}

        <PromptInputAttachments>
          {(attachment) => <PromptInputAttachment data={attachment} />}
        </PromptInputAttachments>
        <PromptInputBody className="absolute top-0 right-0 left-0 z-3">
          <PromptInputTextarea
            className={cn("size-full")}
            disabled={disabled}
            placeholder={t.inputBox.placeholder}
            autoFocus={autoFocus}
            defaultValue={initialValue}
            onChange={(event) => setDraftText(event.currentTarget.value)}
          />
        </PromptInputBody>
        <PromptInputFooter className="flex flex-wrap gap-2">
          <PromptInputTools className="min-w-0 flex-wrap">
          {/* Agent Selector */}
          <PromptInputActionMenu>
            <PromptInputActionMenuTrigger className="gap-1! px-2!">
              <div>
                {selectedAgent ? (
                  <BotIcon className="size-3" />
                ) : (
                  <UserIcon className="size-3" />
                )}
              </div>
              <div className="max-w-[80px] truncate text-xs font-normal">
                {selectedAgent ? selectedAgent.name : t.inputBox.agentDefault}
              </div>
            </PromptInputActionMenuTrigger>
            <PromptInputActionMenuContent className="w-56">
              <DropdownMenuGroup>
                <DropdownMenuLabel className="text-muted-foreground text-xs">
                  {t.inputBox.agentLabel}
                </DropdownMenuLabel>
                <PromptInputActionMenuItem
                  className={cn(
                    !context.agent_name
                      ? "text-accent-foreground"
                      : "text-muted-foreground/65",
                  )}
                  onSelect={() => handleAgentSelect(undefined)}
                >
                  <div className="flex items-center gap-2">
                    <UserIcon className="size-4" />
                    <span className="font-medium">{t.inputBox.agentDefault}</span>
                  </div>
                  {!context.agent_name ? (
                    <CheckIcon className="ml-auto size-4" />
                  ) : (
                    <div className="ml-auto size-4" />
                  )}
                </PromptInputActionMenuItem>
                {agents.length > 0 && <DropdownMenuSeparator />}
                {agents.map((a) => (
                  <PromptInputActionMenuItem
                    key={a.name}
                    className={cn(
                      context.agent_name === a.name
                        ? "text-accent-foreground"
                        : "text-muted-foreground/65",
                    )}
                    onSelect={() => handleAgentSelect(a.name)}
                  >
                    <div className="flex items-center gap-2">
                      <BotIcon className="size-4" />
                      <div className="flex flex-col">
                        <span className="font-medium">{a.name}</span>
                        {a.model && (
                          <span className="text-muted-foreground text-[10px]">{a.model}</span>
                        )}
                      </div>
                    </div>
                    {context.agent_name === a.name ? (
                      <CheckIcon className="ml-auto size-4" />
                    ) : (
                      <div className="ml-auto size-4" />
                    )}
                  </PromptInputActionMenuItem>
                ))}
              </DropdownMenuGroup>
            </PromptInputActionMenuContent>
          </PromptInputActionMenu>
          {/* TODO: Add more connectors here
          <PromptInputActionMenu>
            <PromptInputActionMenuTrigger className="px-2!" />
            <PromptInputActionMenuContent>
              <PromptInputActionAddAttachments
                label={t.inputBox.addAttachments}
              />
            </PromptInputActionMenuContent>
          </PromptInputActionMenu> */}
          <AddAttachmentsButton className="px-2!" />
          {voiceSupported && (
            <VoiceInputButton
              isListening={isListening}
              interimTranscript={interimTranscript}
              onToggle={toggleVoice}
            />
          )}
          <PromptInputActionMenu>
            <ModeHoverGuide
              mode={
                effectiveMode === "flash" ||
                  effectiveMode === "thinking" ||
                  effectiveMode === "pro" ||
                  effectiveMode === "ultra"
                  ? effectiveMode
                  : "flash"
              }
            >
              <PromptInputActionMenuTrigger className="gap-1! px-2!">
                <div>
                  {effectiveMode === "flash" && <ZapIcon className="size-3" />}
                  {effectiveMode === "thinking" && (
                    <LightbulbIcon className="size-3" />
                  )}
                  {effectiveMode === "pro" && (
                    <GraduationCapIcon className="size-3" />
                  )}
                  {effectiveMode === "ultra" && (
                    <RocketIcon className="size-3 text-[#dabb5e]" />
                  )}
                </div>
                <div
                  className={cn(
                    "text-xs font-normal",
                    effectiveMode === "ultra" ? "golden-text" : "",
                  )}
                >
                  {(effectiveMode === "flash" && t.inputBox.flashMode) ||
                    (effectiveMode === "thinking" && t.inputBox.reasoningMode) ||
                    (effectiveMode === "pro" && t.inputBox.proMode) ||
                    (effectiveMode === "ultra" && t.inputBox.ultraMode)}
                </div>
              </PromptInputActionMenuTrigger>
            </ModeHoverGuide>
            <PromptInputActionMenuContent className="w-80">
              <DropdownMenuGroup>
                <DropdownMenuLabel className="text-muted-foreground text-xs">
                  {t.inputBox.mode}
                </DropdownMenuLabel>
                <PromptInputActionMenu>
                  <PromptInputActionMenuItem
                    className={cn(
                      effectiveMode === "flash"
                        ? "text-accent-foreground"
                        : "text-muted-foreground/65",
                    )}
                    onSelect={() => handleModeSelect("flash")}
                  >
                    <div className="flex flex-col gap-2">
                      <div className="flex items-center gap-1 font-bold">
                        <ZapIcon
                          className={cn(
                            "mr-2 size-4",
                            effectiveMode === "flash" &&
                            "text-accent-foreground",
                          )}
                        />
                        {t.inputBox.flashMode}
                      </div>
                      <div className="pl-7 text-xs">
                        {t.inputBox.flashModeDescription}
                      </div>
                    </div>
                    {effectiveMode === "flash" ? (
                      <CheckIcon className="ml-auto size-4" />
                    ) : (
                      <div className="ml-auto size-4" />
                    )}
                  </PromptInputActionMenuItem>
                  {supportThinking && (
                    <PromptInputActionMenuItem
                      className={cn(
                        effectiveMode === "thinking"
                          ? "text-accent-foreground"
                          : "text-muted-foreground/65",
                      )}
                      onSelect={() => handleModeSelect("thinking")}
                    >
                      <div className="flex flex-col gap-2">
                        <div className="flex items-center gap-1 font-bold">
                          <LightbulbIcon
                            className={cn(
                              "mr-2 size-4",
                              effectiveMode === "thinking" &&
                              "text-accent-foreground",
                            )}
                          />
                          {t.inputBox.reasoningMode}
                        </div>
                        <div className="pl-7 text-xs">
                          {t.inputBox.reasoningModeDescription}
                        </div>
                      </div>
                      {effectiveMode === "thinking" ? (
                        <CheckIcon className="ml-auto size-4" />
                      ) : (
                        <div className="ml-auto size-4" />
                      )}
                    </PromptInputActionMenuItem>
                  )}
                  <PromptInputActionMenuItem
                    className={cn(
                      effectiveMode === "pro"
                        ? "text-accent-foreground"
                        : "text-muted-foreground/65",
                    )}
                    onSelect={() => handleModeSelect("pro")}
                  >
                    <div className="flex flex-col gap-2">
                      <div className="flex items-center gap-1 font-bold">
                        <GraduationCapIcon
                          className={cn(
                            "mr-2 size-4",
                            effectiveMode === "pro" && "text-accent-foreground",
                          )}
                        />
                        {t.inputBox.proMode}
                      </div>
                      <div className="pl-7 text-xs">
                        {t.inputBox.proModeDescription}
                      </div>
                    </div>
                    {effectiveMode === "pro" ? (
                      <CheckIcon className="ml-auto size-4" />
                    ) : (
                      <div className="ml-auto size-4" />
                    )}
                  </PromptInputActionMenuItem>
                  <PromptInputActionMenuItem
                    className={cn(
                      effectiveMode === "ultra"
                        ? "text-accent-foreground"
                        : "text-muted-foreground/65",
                    )}
                    onSelect={() => handleModeSelect("ultra")}
                  >
                    <div className="flex flex-col gap-2">
                      <div className="flex items-center gap-1 font-bold">
                        <RocketIcon
                          className={cn(
                            "mr-2 size-4",
                            effectiveMode === "ultra" && "text-[#dabb5e]",
                          )}
                        />
                        <div
                          className={cn(
                            effectiveMode === "ultra" && "golden-text",
                          )}
                        >
                          {t.inputBox.ultraMode}
                        </div>
                      </div>
                      <div className="pl-7 text-xs">
                        {t.inputBox.ultraModeDescription}
                      </div>
                    </div>
                    {effectiveMode === "ultra" ? (
                      <CheckIcon className="ml-auto size-4" />
                    ) : (
                      <div className="ml-auto size-4" />
                    )}
                  </PromptInputActionMenuItem>
                </PromptInputActionMenu>
              </DropdownMenuGroup>
            </PromptInputActionMenuContent>
          </PromptInputActionMenu>
          {supportReasoningEffort && effectiveMode !== "flash" && (
            <PromptInputActionMenu>
              <PromptInputActionMenuTrigger className="gap-1! px-2!">
                <div className="text-xs font-normal">
                  {t.inputBox.reasoningEffort}:
                  {context.reasoning_effort === "minimal" && " " + t.inputBox.reasoningEffortMinimal}
                  {context.reasoning_effort === "low" && " " + t.inputBox.reasoningEffortLow}
                  {context.reasoning_effort === "medium" && " " + t.inputBox.reasoningEffortMedium}
                  {context.reasoning_effort === "high" && " " + t.inputBox.reasoningEffortHigh}
                </div>
              </PromptInputActionMenuTrigger>
              <PromptInputActionMenuContent className="w-70">
                <DropdownMenuGroup>
                  <DropdownMenuLabel className="text-muted-foreground text-xs">
                    {t.inputBox.reasoningEffort}
                  </DropdownMenuLabel>
                  <PromptInputActionMenu>
                    <PromptInputActionMenuItem
                      className={cn(
                        context.reasoning_effort === "minimal"
                          ? "text-accent-foreground"
                          : "text-muted-foreground/65",
                      )}
                      onSelect={() => handleReasoningEffortSelect("minimal")}
                    >
                      <div className="flex flex-col gap-2">
                        <div className="flex items-center gap-1 font-bold">
                          {t.inputBox.reasoningEffortMinimal}
                        </div>
                        <div className="pl-2 text-xs">
                          {t.inputBox.reasoningEffortMinimalDescription}
                        </div>
                      </div>
                      {context.reasoning_effort === "minimal" ? (
                        <CheckIcon className="ml-auto size-4" />
                      ) : (
                        <div className="ml-auto size-4" />
                      )}
                    </PromptInputActionMenuItem>
                    <PromptInputActionMenuItem
                      className={cn(
                        context.reasoning_effort === "low"
                          ? "text-accent-foreground"
                          : "text-muted-foreground/65",
                      )}
                      onSelect={() => handleReasoningEffortSelect("low")}
                    >
                      <div className="flex flex-col gap-2">
                        <div className="flex items-center gap-1 font-bold">
                          {t.inputBox.reasoningEffortLow}
                        </div>
                        <div className="pl-2 text-xs">
                          {t.inputBox.reasoningEffortLowDescription}
                        </div>
                      </div>
                      {context.reasoning_effort === "low" ? (
                        <CheckIcon className="ml-auto size-4" />
                      ) : (
                        <div className="ml-auto size-4" />
                      )}
                    </PromptInputActionMenuItem>
                    <PromptInputActionMenuItem
                      className={cn(
                        context.reasoning_effort === "medium" || !context.reasoning_effort
                          ? "text-accent-foreground"
                          : "text-muted-foreground/65",
                      )}
                      onSelect={() => handleReasoningEffortSelect("medium")}
                    >
                      <div className="flex flex-col gap-2">
                        <div className="flex items-center gap-1 font-bold">
                          {t.inputBox.reasoningEffortMedium}
                        </div>
                        <div className="pl-2 text-xs">
                          {t.inputBox.reasoningEffortMediumDescription}
                        </div>
                      </div>
                      {context.reasoning_effort === "medium" || !context.reasoning_effort ? (
                        <CheckIcon className="ml-auto size-4" />
                      ) : (
                        <div className="ml-auto size-4" />
                      )}
                    </PromptInputActionMenuItem>
                    <PromptInputActionMenuItem
                      className={cn(
                        context.reasoning_effort === "high"
                          ? "text-accent-foreground"
                          : "text-muted-foreground/65",
                      )}
                      onSelect={() => handleReasoningEffortSelect("high")}
                    >
                      <div className="flex flex-col gap-2">
                        <div className="flex items-center gap-1 font-bold">
                          {t.inputBox.reasoningEffortHigh}
                        </div>
                        <div className="pl-2 text-xs">
                          {t.inputBox.reasoningEffortHighDescription}
                        </div>
                      </div>
                      {context.reasoning_effort === "high" ? (
                        <CheckIcon className="ml-auto size-4" />
                      ) : (
                        <div className="ml-auto size-4" />
                      )}
                    </PromptInputActionMenuItem>
                  </PromptInputActionMenu>
                </DropdownMenuGroup>
              </PromptInputActionMenuContent>
            </PromptInputActionMenu>
          )}
          <PromptInputActionMenu>
            <PromptInputActionMenuTrigger className="gap-1! px-2!" data-testid="permission-mode-trigger" title="Permission mode">
              <SelectedPermissionIcon className="size-3" />
              <span className="text-xs font-normal">{selectedPermissionMode.label}</span>
            </PromptInputActionMenuTrigger>
            <PromptInputActionMenuContent className="w-72">
              <DropdownMenuGroup>
                <DropdownMenuLabel className="text-muted-foreground text-xs">
                  权限模式
                </DropdownMenuLabel>
                {PERMISSION_MODE_OPTIONS.map((item) => {
                  const Icon = item.icon;
                  const selected = item.value === effectivePermissionMode;
                  return (
                    <PromptInputActionMenuItem
                      key={item.value}
                      className={cn(selected ? "text-accent-foreground" : "text-muted-foreground/65")}
                      data-testid={`permission-mode-option-${item.value}`}
                      onSelect={() => handlePermissionModeSelect(item.value)}
                    >
                      <div className="flex min-w-0 items-start gap-2">
                        <Icon className="mt-0.5 size-4 shrink-0" />
                        <div className="flex min-w-0 flex-col gap-1">
                          <span className="font-medium">{item.label}</span>
                          <span className="text-muted-foreground text-xs leading-4">{item.detail}</span>
                        </div>
                      </div>
                      {selected ? <CheckIcon className="ml-auto size-4" /> : <div className="ml-auto size-4" />}
                    </PromptInputActionMenuItem>
                  );
                })}
              </DropdownMenuGroup>
            </PromptInputActionMenuContent>
          </PromptInputActionMenu>
          <div
            aria-label="对话上下文"
            className="border-border/70 bg-background/72 text-muted-foreground inline-flex h-8 max-w-[13rem] items-center gap-1.5 rounded-md border px-2.5 text-xs shadow-none"
            data-context-cycle-base-tokens={contextUsage.cycleBaseTokens}
            data-context-raw-tokens={contextUsage.rawUsedTokens}
            data-context-used-tokens={contextUsage.usedTokens}
            data-testid="context-token-counter"
            role="status"
            title={contextTokenTitle}
          >
            <span className="shrink-0 font-normal">对话上下文</span>
            <span className="min-w-0 truncate font-mono tabular-nums">{contextTokenLabel}</span>
          </div>
        </PromptInputTools>
        <PromptInputTools className="min-w-0 flex-wrap justify-end">
          <ModelSelector
            open={modelDialogOpen}
            onOpenChange={setModelDialogOpen}
          >
            <ModelSelectorTrigger asChild>
              <PromptInputButton>
                <ModelSelectorName className="text-xs font-normal">
                  {usingSystemDefault
                    ? `${t.workflows.systemDefault}: ${selectedModel?.display_name ?? selectedModel?.name ?? "-"}`
                    : selectedModel?.display_name ?? selectedModel?.name}
                </ModelSelectorName>
              </PromptInputButton>
            </ModelSelectorTrigger>
            <ModelSelectorContent>
              <ModelSelectorInput placeholder={t.inputBox.searchModels} />
              <ModelSelectorList>
                {models.length === 0 ? <ModelSelectorEmpty>No models available.</ModelSelectorEmpty> : null}
                {models.length > 0 ? (
                  <>
                    <ModelSelectorGroup heading="This Chat">
                      <ModelSelectorItem
                        value={`chat system default ${systemDefaultModel?.display_name ?? systemDefaultModel?.name ?? ""}`}
                        onSelect={handleUseSystemDefault}
                      >
                        <div className="flex min-w-0 flex-1 flex-col">
                          <ModelSelectorName>{t.workflows.systemDefault}</ModelSelectorName>
                          <span className="text-muted-foreground text-[10px]">
                            {systemDefaultModel?.display_name ?? systemDefaultModel?.name ?? "No system default configured"}
                          </span>
                        </div>
                        {usingSystemDefault ? (
                          <CheckIcon className="ml-auto size-4" />
                        ) : (
                          <div className="ml-auto size-4" />
                        )}
                      </ModelSelectorItem>
                      {models.map((m) => (
                        <ModelSelectorItem
                          key={`chat-${m.name}`}
                          value={`chat override ${m.name} ${m.display_name ?? m.name}`}
                          onSelect={() => handleModelSelect(m.name)}
                        >
                          <div className="flex min-w-0 flex-1 flex-col">
                            <ModelSelectorName>{m.display_name ?? m.name}</ModelSelectorName>
                            {formatModelProvider(m.name) ? (
                              <span className="text-muted-foreground text-[10px]">
                                {formatModelProvider(m.name)}
                              </span>
                            ) : null}
                          </div>
                          {m.name === explicitModel?.name ? (
                            <CheckIcon className="ml-auto size-4" />
                          ) : (
                            <div className="ml-auto size-4" />
                          )}
                        </ModelSelectorItem>
                      ))}
                    </ModelSelectorGroup>
                    <ModelSelectorSeparator />
                    <ModelSelectorGroup heading={t.workflows.systemDefault}>
                      {models.map((m) => (
                        <ModelSelectorItem
                          key={`system-${m.name}`}
                          value={`system-default ${m.name} ${m.display_name ?? m.name}`}
                          onSelect={() => void handleSystemDefaultModelSelect(m.name)}
                        >
                          <div className="flex min-w-0 flex-1 flex-col">
                            <ModelSelectorName>{m.display_name ?? m.name}</ModelSelectorName>
                            {formatModelProvider(m.name) ? (
                              <span className="text-muted-foreground text-[10px]">
                                {formatModelProvider(m.name)}
                              </span>
                            ) : null}
                          </div>
                          {m.name === systemDefaultModel?.name ? (
                            <CheckIcon className="ml-auto size-4" />
                          ) : (
                            <div className="ml-auto size-4" />
                          )}
                        </ModelSelectorItem>
                      ))}
                    </ModelSelectorGroup>

                  </>
                ) : null}
              </ModelSelectorList>
            </ModelSelectorContent>
          </ModelSelector>
          <PromptInputSubmit
            className="rounded-full"
            disabled={disabled}
            variant="outline"
            status={status}
          />
        </PromptInputTools>
      </PromptInputFooter>
      {isNewThread && searchParams.get("mode") !== "skill" && (
        <div className="absolute right-0 -bottom-24 left-0 z-0 flex items-center justify-center px-2 sm:-bottom-20">
          <SuggestionList />
        </div>
      )}
      {!isNewThread && (
        <div className="bg-background absolute right-0 -bottom-[17px] left-0 z-0 h-4"></div>
      )}
      </PromptInput>
    </div>
  );
}

function SuggestionList() {
  const { t } = useI18n();
  const { textInput } = usePromptInputController();
  const handleSuggestionClick = useCallback(
    (prompt: string | undefined) => {
      if (!prompt) return;
      textInput.setInput(prompt);
      setTimeout(() => {
        const textarea = document.querySelector<HTMLTextAreaElement>(
          "textarea[name='message']",
        );
        if (textarea) {
          const selStart = prompt.indexOf("[");
          const selEnd = prompt.indexOf("]");
          if (selStart !== -1 && selEnd !== -1) {
            textarea.setSelectionRange(selStart, selEnd + 1);
            textarea.focus();
          }
        }
      }, 500);
    },
    [textInput],
  );
  return (
    <Suggestions className="min-h-16 w-full items-start justify-center">
      <ConfettiButton
        className="text-muted-foreground cursor-pointer whitespace-normal rounded-full px-4 text-xs font-normal"
        variant="outline"
        size="sm"
        onClick={() => handleSuggestionClick(t.inputBox.surpriseMePrompt)}
      >
        <SparklesIcon className="size-4" /> {t.inputBox.surpriseMe}
      </ConfettiButton>
      {t.inputBox.suggestions.map((suggestion) => (
        <Suggestion
          key={suggestion.suggestion}
          icon={suggestion.icon}
          suggestion={suggestion.suggestion}
          onClick={() => handleSuggestionClick(suggestion.prompt)}
        />
      ))}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Suggestion icon={PlusIcon} suggestion={t.common.create} />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuGroup>
            {t.inputBox.suggestionsCreate.map((suggestion, index) =>
              "type" in suggestion && suggestion.type === "separator" ? (
                <DropdownMenuSeparator key={index} />
              ) : (
                !("type" in suggestion) && (
                  <DropdownMenuItem
                    key={suggestion.suggestion}
                    onClick={() => handleSuggestionClick(suggestion.prompt)}
                  >
                    {suggestion.icon && <suggestion.icon className="size-4" />}
                    {suggestion.suggestion}
                  </DropdownMenuItem>
                )
              ),
            )}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </Suggestions>
  );
}

function AddAttachmentsButton({ className }: { className?: string }) {
  const { t } = useI18n();
  const attachments = usePromptInputAttachments();
  const label = t.inputBox.addAttachments;

  return (
    <PromptInputButton
      aria-label={label}
      className={cn("px-2!", className)}
      onClick={() => attachments.openFileDialog()}
      title={label}
    >
      <PaperclipIcon className="size-3" />
    </PromptInputButton>
  );
}

function VoiceInputButton({
  isListening,
  interimTranscript,
  onToggle,
}: {
  isListening: boolean;
  interimTranscript: string;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  const label = isListening
    ? (t.inputBox.voiceStop ?? "Stop")
    : (t.inputBox.voiceStart ?? "Voice input");

  return (
    <PromptInputButton
      aria-label={label}
      className={cn("px-2!", isListening && "text-red-500 animate-pulse")}
      onClick={onToggle}
      title={label}
    >
      {isListening ? (
        <MicOffIcon className="size-3" />
      ) : (
        <MicIcon className="size-3" />
      )}
      {isListening && interimTranscript && (
        <span className="ml-1 max-w-24 truncate text-[10px] opacity-60">
          {interimTranscript}
        </span>
      )}
    </PromptInputButton>
  );
}
