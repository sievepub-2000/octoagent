"use client";

import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  CpuIcon,
  EyeIcon,
  InfoIcon,
  Loader2Icon,
  SaveIcon,
  SparklesIcon,
  WrenchIcon,
  ZapIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { BrandMark } from "@/components/brand/octo-mark";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import { getWorkspaceLocaleCopy } from "@/core/i18n/workspace-copy";
import { useCreateModel, useModels } from "@/core/models/hooks";
import type { ModelCreateRequest } from "@/core/models/types";
import { useLocalSettings } from "@/core/settings";
import { useApplySetup, useSetupStatus } from "@/core/setup";
import { cn } from "@/lib/utils";

const INTERFACE_OPTIONS = [
  "openai_compatible",
  "anthropic_messages",
  "google_genai",
  "deepseek_reasoner",
  "generic",
] as const;

type FirstModelFormState = {
  name: string;
  display_name: string;
  description: string;
  model: string;
  interface_type: string;
  provider_name: string;
  use: string;
  api_key: string;
  base_url: string;
  google_api_key: string;
  fallback_models: string;
  max_context_tokens: string;
  supports_thinking: boolean;
  supports_reasoning_effort: boolean;
  supports_vision: boolean;
};

const EMPTY_FIRST_MODEL_FORM: FirstModelFormState = {
  name: "",
  display_name: "",
  description: "",
  model: "",
  interface_type: "openai_compatible",
  provider_name: "",
  use: "",
  api_key: "",
  base_url: "",
  google_api_key: "",
  fallback_models: "",
  max_context_tokens: "",
  supports_thinking: false,
  supports_reasoning_effort: false,
  supports_vision: false,
};

export function SetupWizard({ onComplete }: { onComplete: () => void }) {
  const { locale, t } = useI18n();
  const copy = getWorkspaceLocaleCopy(locale);
  const router = useRouter();
  const { models } = useModels();
  const createModelMutation = useCreateModel();
  const [localSettings, setLocalSettings] = useLocalSettings();
  const { status: systemStatus } = useSetupStatus();
  const applySetupMutation = useApplySetup();

  const [workspacePath, setWorkspacePath] = useState(
    localSettings.setup.workspace_path || "",
  );
  const [defaultModel, setDefaultModel] = useState(
    localSettings.setup.default_model ?? "",
  );
  const [firstModelForm, setFirstModelForm] = useState<FirstModelFormState>(
    EMPTY_FIRST_MODEL_FORM,
  );
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState("");
  const [modelError, setModelError] = useState("");

  useEffect(() => {
    if (systemStatus?.workspace_path && !localSettings.setup.workspace_path) {
      setWorkspacePath(systemStatus.workspace_path);
    }
    if (
      systemStatus?.configured_default_model
      && !localSettings.setup.default_model
    ) {
      setDefaultModel(systemStatus.configured_default_model);
    }
  }, [
    localSettings.setup.default_model,
    localSettings.setup.workspace_path,
    systemStatus,
  ]);

  useEffect(() => {
    if (localSettings.setup.workspace_path) {
      setWorkspacePath(localSettings.setup.workspace_path);
    }
  }, [localSettings.setup.workspace_path]);

  useEffect(() => {
    if (models.length === 0) {
      if (defaultModel) {
        setDefaultModel("");
      }
      return;
    }
    if (models.some((model) => model.name === defaultModel)) {
      return;
    }
    const nextDefaultModel = [
      localSettings.setup.default_model,
      systemStatus?.configured_default_model,
      models[0]?.name,
    ].find(
      (candidate) =>
        typeof candidate === "string"
        && candidate.length > 0
        && models.some((model) => model.name === candidate),
    );
    if (nextDefaultModel) {
      setDefaultModel(nextDefaultModel);
    }
  }, [
    defaultModel,
    localSettings.setup.default_model,
    models,
    systemStatus?.configured_default_model,
  ]);

  const updateFirstModelField = useCallback(
    <K extends keyof FirstModelFormState>(
      key: K,
      value: FirstModelFormState[K],
    ) => {
      setFirstModelForm((current) => ({
        ...current,
        [key]: value,
      }));
    },
    [],
  );

  const handleCreateFirstModel = useCallback(async () => {
    if (!firstModelForm.name.trim() || !firstModelForm.model.trim()) {
      setModelError(copy.setupWizard.modelRequiredError);
      return;
    }

    setModelError("");
    setApplyError("");

    const payload: ModelCreateRequest = {
      name: firstModelForm.name.trim(),
      display_name: firstModelForm.display_name.trim() || undefined,
      description: firstModelForm.description.trim() || undefined,
      model: firstModelForm.model.trim(),
      interface_type: firstModelForm.interface_type || undefined,
      provider_name: firstModelForm.provider_name.trim() || undefined,
      use: firstModelForm.use.trim() || undefined,
      api_key: firstModelForm.api_key.trim() || undefined,
      base_url: firstModelForm.base_url.trim() || undefined,
      google_api_key: firstModelForm.google_api_key.trim() || undefined,
      fallback_models: firstModelForm.fallback_models
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
      max_context_tokens: firstModelForm.max_context_tokens.trim()
        ? Number(firstModelForm.max_context_tokens.trim())
        : undefined,
      supports_thinking: firstModelForm.supports_thinking,
      supports_reasoning_effort: firstModelForm.supports_reasoning_effort,
      supports_vision: firstModelForm.supports_vision,
    };

    try {
      const createdModel = await createModelMutation.mutateAsync(payload);
      setDefaultModel(createdModel.name);
      setFirstModelForm(EMPTY_FIRST_MODEL_FORM);
    } catch (error) {
      setModelError(
        error instanceof Error
          ? error.message
          : copy.setupWizard.createFirstModelFailed,
      );
    }
  }, [copy.setupWizard.createFirstModelFailed, copy.setupWizard.modelRequiredError, createModelMutation, firstModelForm]);

  const handleFinish = useCallback(async () => {
    const resolvedDefaultModel = defaultModel ?? models[0]?.name ?? "";
    if (!resolvedDefaultModel) {
      setApplyError(copy.setupWizard.finishRequiresModel);
      return;
    }

    const resolvedWorkspacePath = workspacePath.trim()
      ? workspacePath.trim()
      : (systemStatus?.workspace_path ?? "");

    setApplying(true);
    setApplyError("");
    try {
      const resp = await applySetupMutation.mutateAsync({
        workspace_path: resolvedWorkspacePath,
        default_model: resolvedDefaultModel,
        sandbox_mode: "local",
      });
      if (!resp.success) {
        setApplyError(resp.error ?? copy.setupWizard.setupFailed);
        return;
      }

      setLocalSettings("setup", {
        completed: true,
        workspace_path: resp.workspace_path ?? resolvedWorkspacePath,
        default_model: resp.default_model ?? resolvedDefaultModel,
        sandbox_mode: resp.sandbox_mode ?? "local",
      });
      setLocalSettings("context", {
        model_name: undefined,
      });
      onComplete();
    } catch {
      setApplyError(t.setupWizard.serverError ?? "Failed to connect to server");
    } finally {
      setApplying(false);
    }
  }, [
    applySetupMutation,
    copy.setupWizard.finishRequiresModel,
    copy.setupWizard.setupFailed,
    defaultModel,
    models,
    onComplete,
    setLocalSettings,
    t.setupWizard.serverError,
    systemStatus?.workspace_path,
    workspacePath,
  ]);

  const selectedModel = models.find((model) => model.name === defaultModel);

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-8">
      <div className="text-center">
        <div className="flex items-center justify-center gap-3">
          <BrandMark className="size-10" priority size={40} />
          <h2 className="text-xl font-bold">{t.setupWizard.title}</h2>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {t.setupWizard.subtitle}
        </p>
      </div>

      <div className="flex items-center justify-center">
        <Badge
          variant="outline"
          className="border-primary/30 px-3 py-1 text-[11px] tracking-[0.12em]"
        >
          {copy.setupWizard.progressBadge}
        </Badge>
      </div>

      <div className="rounded-xl border border-primary/25 bg-card p-5 shadow-sm">
        <div className="flex items-start gap-3">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <CheckCircle2Icon className="size-4" />
          </div>
          <div className="min-w-0 flex-1 space-y-2">
            <div>
              <h3 className="text-sm font-semibold">{t.setupWizard.stepWorkspace}</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                {t.setupWizard.stepWorkspaceDesc}
              </p>
            </div>
            <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs">
              <div className="font-medium text-foreground">
                {workspacePath.trim() ? workspacePath.trim() : (systemStatus?.workspace_path ?? "")}
              </div>
              <div className="mt-2 space-y-1 text-muted-foreground">
                <div>{copy.setupWizard.workspaceLayoutDefault}</div>
                <div>{copy.setupWizard.workspaceLayoutEnv}</div>
                <div>{copy.setupWizard.workspaceLayoutTaskwork}</div>
              </div>
            </div>
            {systemStatus ? (
              <p className="text-[10px] text-muted-foreground/70">
                {t.setupWizard.currentBackendPath}: {" "}
                <span className="font-mono">{systemStatus.workspace_path}</span>
                {systemStatus.models_configured > 0
                  ? <> {" "}· {systemStatus.models_configured} {t.setupWizard.modelsReady}</>
                  : null}
                {systemStatus.skills_available > 0
                  ? <>{" "}· {systemStatus.skills_available} {t.setupWizard.skillsAvailable}</>
                  : null}
              </p>
            ) : null}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-4 rounded-xl border border-primary/25 bg-card p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <SparklesIcon className="size-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold">{t.setupWizard.stepModel}</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {copy.setupWizard.modelOnlyStepDesc}
            </p>
          </div>
        </div>

        {models.length > 0 ? (
          <>
            <div className="rounded-lg border border-primary/15 bg-primary/5 p-3 text-xs text-muted-foreground">
              {copy.setupWizard.defaultModelNotice}
            </div>

            <Select value={defaultModel} onValueChange={setDefaultModel}>
              <SelectTrigger>
                <SelectValue placeholder={t.setupWizard.stepModelHint} />
              </SelectTrigger>
              <SelectContent>
                {models.map((model) => (
                  <SelectItem key={model.name} value={model.name}>
                    {model.display_name ?? model.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <div className="grid gap-2 lg:grid-cols-2">
              {models.map((model) => {
                const active = model.name === defaultModel;
                return (
                  <button
                    key={model.name}
                    type="button"
                    onClick={() => setDefaultModel(model.name)}
                    className={cn(
                      "rounded-lg border p-3 text-left transition-colors",
                      active
                        ? "border-primary bg-primary/5"
                        : "border-border hover:border-primary/40",
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium">
                          {model.display_name ?? model.name}
                        </div>
                        <div className="font-mono text-[11px] text-muted-foreground">
                          {model.name}
                        </div>
                      </div>
                      {active ? (
                        <Badge variant="default" className="text-[10px]">
                          {copy.setupWizard.selected}
                        </Badge>
                      ) : null}
                    </div>
                    {model.description ? (
                      <p className="mt-2 text-xs text-muted-foreground">
                        {model.description}
                      </p>
                    ) : null}
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {(model.interface_type ?? model.resolved_interface_type) ? (
                        <Badge variant="secondary" className="text-[10px]">
                          {model.interface_type ?? model.resolved_interface_type}
                        </Badge>
                      ) : null}
                      {model.provider_name ? (
                        <Badge variant="outline" className="text-[10px]">
                          {model.provider_name}
                        </Badge>
                      ) : null}
                      {model.supports_thinking ? (
                        <Badge variant="outline" className="text-[10px]">
                          <ZapIcon className="mr-0.5 size-3" />{copy.modelFields.thinking}
                        </Badge>
                      ) : null}
                      {model.supports_reasoning_effort ? (
                        <Badge variant="outline" className="text-[10px]">
                          {copy.modelFields.reasoning}
                        </Badge>
                      ) : null}
                      {model.supports_vision ? (
                        <Badge variant="outline" className="text-[10px]">
                          <EyeIcon className="mr-0.5 size-3" />{copy.modelFields.vision}
                        </Badge>
                      ) : null}
                    </div>
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)]">
            <div className="rounded-xl border border-dashed p-4">
              <div className="flex items-start gap-3">
                <div className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <CpuIcon className="size-4" />
                </div>
                <div className="space-y-2">
                  <div>
                    <div className="text-sm font-semibold">{copy.setupWizard.createFirstModelTitle}</div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {copy.setupWizard.createFirstModelDesc}
                    </p>
                  </div>
                  <div className="rounded-lg border border-primary/15 bg-primary/5 p-3 text-xs text-muted-foreground">
                    {copy.setupWizard.createFirstModelFootnote}
                  </div>
                </div>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.configName}</span>
                  <Input
                    value={firstModelForm.name}
                    onChange={(event) => updateFirstModelField("name", event.target.value)}
                    placeholder="openrouter-sonnet"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.displayName}</span>
                  <Input
                    value={firstModelForm.display_name}
                    onChange={(event) => updateFirstModelField("display_name", event.target.value)}
                    placeholder="OpenRouter Sonnet"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.providerModel}</span>
                  <Input
                    value={firstModelForm.model}
                    onChange={(event) => updateFirstModelField("model", event.target.value)}
                    placeholder="anthropic/claude-sonnet-4"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.interfaceType}</span>
                  <select
                    className="border-input dark:bg-input/30 h-9 w-full rounded-md border bg-transparent px-3 text-sm"
                    value={firstModelForm.interface_type}
                    onChange={(event) => updateFirstModelField("interface_type", event.target.value)}
                  >
                    {INTERFACE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.providerName}</span>
                  <Input
                    value={firstModelForm.provider_name}
                    onChange={(event) => updateFirstModelField("provider_name", event.target.value)}
                    placeholder="openrouter / anthropic / google / groq"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.customUsePath}</span>
                  <Input
                    value={firstModelForm.use}
                    onChange={(event) => updateFirstModelField("use", event.target.value)}
                    placeholder="langchain_openai:ChatOpenAI"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.apiKey}</span>
                  <Input
                    value={firstModelForm.api_key}
                    onChange={(event) => updateFirstModelField("api_key", event.target.value)}
                    placeholder="$OPENROUTER_API_KEY"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.baseUrl}</span>
                  <Input
                    value={firstModelForm.base_url}
                    onChange={(event) => updateFirstModelField("base_url", event.target.value)}
                    placeholder="https://openrouter.ai/api/v1"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.googleApiKey}</span>
                  <Input
                    value={firstModelForm.google_api_key}
                    onChange={(event) => updateFirstModelField("google_api_key", event.target.value)}
                    placeholder="$GOOGLE_API_KEY"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.fallbackModels}</span>
                  <Input
                    value={firstModelForm.fallback_models}
                    onChange={(event) => updateFirstModelField("fallback_models", event.target.value)}
                    placeholder="gpt-4o-mini, local-backup"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.maxContextTokens}</span>
                  <Input
                    value={firstModelForm.max_context_tokens}
                    onChange={(event) => updateFirstModelField("max_context_tokens", event.target.value)}
                    placeholder="200000"
                  />
                </label>
                <label className="space-y-1 md:col-span-2">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.description}</span>
                  <Textarea
                    value={firstModelForm.description}
                    onChange={(event) => updateFirstModelField("description", event.target.value)}
                    placeholder={copy.modelFields.descriptionPlaceholder}
                  />
                </label>
                <div className="flex flex-wrap items-center gap-4 pt-2 text-xs text-muted-foreground md:col-span-2">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={firstModelForm.supports_thinking}
                      onChange={(event) => updateFirstModelField("supports_thinking", event.target.checked)}
                    />
                    {copy.modelFields.thinking}
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={firstModelForm.supports_reasoning_effort}
                      onChange={(event) => updateFirstModelField("supports_reasoning_effort", event.target.checked)}
                    />
                    {copy.modelFields.reasoning}
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={firstModelForm.supports_vision}
                      onChange={(event) => updateFirstModelField("supports_vision", event.target.checked)}
                    />
                    {copy.modelFields.vision}
                  </label>
                </div>
              </div>

              {modelError ? (
                <div className="mt-4 flex items-center gap-1.5 rounded bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  <AlertTriangleIcon className="size-3" />
                  {modelError}
                </div>
              ) : null}

              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  onClick={() => {
                    void handleCreateFirstModel();
                  }}
                  disabled={createModelMutation.isPending}
                >
                  {createModelMutation.isPending ? (
                    <>
                      <Loader2Icon className="mr-1.5 size-3.5 animate-spin" />
                      {copy.setupWizard.creatingModel}
                    </>
                  ) : (
                    <>
                      <SaveIcon className="size-3.5" />
                      {copy.setupWizard.createModel}
                    </>
                  )}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => router.push("/workspace/config/models")}
                >
                  <WrenchIcon className="size-3.5" />
                  {copy.setupWizard.openFullModelSettings}
                </Button>
              </div>
            </div>

            <div className="rounded-xl border bg-muted/10 p-4">
              <div className="flex items-center gap-2 text-sm font-medium">
                <InfoIcon className="size-4 text-primary" />
                {copy.setupWizard.firstRunChecklistTitle}
              </div>
              <div className="mt-3 space-y-3 text-xs text-muted-foreground">
                <div>
                  <div className="font-medium text-foreground">{copy.setupWizard.checklistModelTitle}</div>
                  <div className="mt-1">
                    {copy.setupWizard.checklistModelDesc}
                  </div>
                </div>
                <div>
                  <div className="font-medium text-foreground">{copy.setupWizard.checklistFinishTitle}</div>
                  <div className="mt-1">
                    {copy.setupWizard.checklistFinishDesc}
                  </div>
                </div>
                <div>
                  <div className="font-medium text-foreground">{copy.setupWizard.checklistAdjustTitle}</div>
                  <div className="mt-1">
                    {copy.setupWizard.checklistAdjustDesc}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-4 rounded-xl border border-primary/25 bg-card p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <CheckCircle2Icon className="size-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold">{copy.setupWizard.applySetupTitle}</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {copy.setupWizard.applySetupDesc}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {workspacePath ? (
            <Badge variant="outline" className="border-primary/30">
              {copy.setupWizard.workspaceLabel}: {workspacePath}
            </Badge>
          ) : null}
          {defaultModel ? (
            <Badge variant="outline" className="border-primary/30">
              {copy.setupWizard.defaultModelLabel}: {selectedModel?.display_name ?? defaultModel}
            </Badge>
          ) : null}
          {selectedModel?.provider_name ? (
            <Badge variant="outline" className="border-primary/30">
              {copy.setupWizard.providerLabel}: {selectedModel.provider_name}
            </Badge>
          ) : null}
          {(selectedModel?.interface_type ?? selectedModel?.resolved_interface_type) ? (
            <Badge variant="outline" className="border-primary/30">
              {copy.setupWizard.interfaceLabel}: {selectedModel?.interface_type ?? selectedModel?.resolved_interface_type}
            </Badge>
          ) : null}
        </div>

        {applyError ? (
          <div className="flex items-center gap-1.5 rounded bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <AlertTriangleIcon className="size-3" />
            {applyError}
          </div>
        ) : null}

        <div className="flex justify-end gap-2">
          <Button
            onClick={() => {
              void handleFinish();
            }}
            disabled={
              applying
              || createModelMutation.isPending
              || (models.length > 0 && !defaultModel)
            }
          >
            {applying ? (
              <>
                <Loader2Icon className="mr-1.5 size-3.5 animate-spin" />
                {t.setupWizard.applying}
              </>
            ) : (
              t.setupWizard.finish
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
