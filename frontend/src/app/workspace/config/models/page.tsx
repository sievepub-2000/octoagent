"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2Icon,
  CpuIcon,
  Edit3Icon,
  EyeIcon,
  InfoIcon,
  PlusIcon,
  SaveIcon,
  Trash2Icon,
  ZapIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { getJSON } from "@/core/api/http";
import { useI18n } from "@/core/i18n/hooks";
import { getWorkspaceLocaleCopy } from "@/core/i18n/workspace-copy";
import { useCreateModel, useDeleteModel, useModels, useUpdateModel } from "@/core/models/hooks";
import type { Model, ModelCreateRequest } from "@/core/models/types";

type FallbackPoolStatus = {
  enabled: boolean;
  reason: string;
  api_key_present: boolean;
  base_url: string;
  pool_models: string[];
  operator_override: boolean;
};

const INTERFACE_OPTIONS = [
  "cli_proxy_api",
  "openai_compatible",
  "anthropic_messages",
  "google_genai",
  "deepseek_reasoner",
  "generic",
] as const;

// Provider presets: auto-set interface_type and base_url when a known provider is selected
const PROVIDER_PRESETS: Array<{
  value: string;
  label: string;
  interface_type: string;
  base_url?: string;
}> = [
  { value: "openrouter", label: "OpenRouter", interface_type: "cli_proxy_api", base_url: "https://openrouter.ai/api/v1" },
  { value: "openai", label: "OpenAI", interface_type: "cli_proxy_api" },
  { value: "anthropic", label: "Anthropic", interface_type: "anthropic_messages" },
  { value: "google", label: "Google (Gemini)", interface_type: "google_genai" },
  { value: "deepseek", label: "DeepSeek", interface_type: "deepseek_reasoner", base_url: "https://api.deepseek.com/v1" },
  { value: "groq", label: "Groq", interface_type: "cli_proxy_api", base_url: "https://api.groq.com/openai/v1" },
  { value: "local", label: "Local (llama.cpp / vLLM / Ollama)", interface_type: "cli_proxy_api", base_url: "http://localhost:8000/v1" },
  { value: "custom", label: "Custom", interface_type: "cli_proxy_api" },
];

type ModelFormState = {
  name: string;
  display_name: string;
  description: string;
  model: string;
  interface_type: string;
  provider_name: string;
  use: string;
  api_key: string;
  base_url: string;
  fallback_models: string;
  max_context_tokens: string;
  supports_thinking: boolean;
  supports_reasoning_effort: boolean;
  supports_vision: boolean;
  showAdvanced: boolean;
};

const EMPTY_FORM: ModelFormState = {
  name: "",
  display_name: "",
  description: "",
  model: "",
  interface_type: "cli_proxy_api",
  provider_name: "",
  use: "",
  api_key: "",
  base_url: "",
  fallback_models: "",
  max_context_tokens: "",
  supports_thinking: false,
  supports_reasoning_effort: false,
  supports_vision: false,
  showAdvanced: false,
};

function modelToForm(model: Model): ModelFormState {
  return {
    name: model.name,
    display_name: model.display_name ?? "",
    description: model.description ?? "",
    model: model.model ?? "",
    interface_type: model.interface_type ?? model.resolved_interface_type ?? "cli_proxy_api",
    provider_name: model.provider_name ?? "",
    use: model.use ?? "",
    api_key: "",
    base_url: "",
    fallback_models: (model.fallback_models ?? []).join(", "),
    max_context_tokens: model.max_context_tokens ? String(model.max_context_tokens) : "",
    supports_thinking: Boolean(model.supports_thinking),
    supports_reasoning_effort: Boolean(model.supports_reasoning_effort),
    supports_vision: Boolean(model.supports_vision),
    showAdvanced: Boolean(
      (model.use?.trim().length ?? 0) > 0 || (model.fallback_models?.length ?? 0) > 0,
    ),
  };
}

export default function ModelsConfigPage() {
  const { locale, t } = useI18n();
  const copy = getWorkspaceLocaleCopy(locale);
  const { models, isLoading } = useModels();
  const createModel = useCreateModel();
  const updateModel = useUpdateModel();
  const deleteModel = useDeleteModel();
  const { data: fallbackStatus } = useQuery<FallbackPoolStatus>({
    queryKey: ["models", "fallback-pool", "status"],
    queryFn: () => getJSON<FallbackPoolStatus>("/api/fallback-pool/status"),
    refetchOnWindowFocus: false,
    retry: false,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [form, setForm] = useState<ModelFormState>(EMPTY_FORM);

  const detail = models.find((m) => m.name === selected || m.id === selected);
  const isEditing = editingName != null;

  useEffect(() => {
    if (detail?.name && editingName === detail.name) {
      setForm(modelToForm(detail));
    }
  }, [detail, editingName]);

  const contractPreview = (() => {
    if (form.interface_type === "anthropic_messages") {
      return {
        adapter: "anthropic_native",
        request: "anthropic.messages.create",
        response: "anthropic.message",
        streaming: "anthropic.messages.stream",
        auth: "x_api_key",
        semantics: "messages",
        thinking: "thinking_blocks",
      };
    }
    if (form.interface_type === "google_genai") {
      return {
        adapter: "google_genai",
        request: "google.genai.generate_content",
        response: "google.genai.response",
        streaming: "google.genai.stream_generate_content",
        auth: "bearer_or_key",
        semantics: "parts",
        thinking: "provider_native",
      };
    }
    if (form.interface_type === "generic") {
      return {
        adapter: "generic",
        request: "generic.invoke",
        response: "generic.invoke",
        streaming: "generic.stream",
        auth: "provider_native",
        semantics: "generic",
        thinking: "none",
      };
    }
    return {
      adapter: "cli_proxy_api",
      request: "chat.completions",
      response: "chat.completion",
      streaming: "chat.completions.chunk",
      auth: "bearer_header",
      semantics: "openai_chat",
      thinking: "extra_body",
    };
  })();

  function updateField<K extends keyof ModelFormState>(key: K, value: ModelFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function startCreate() {
    setEditingName(null);
    setForm(EMPTY_FORM);
    setIsFormOpen(true);
  }

  function startEdit(model?: Model) {
    const target = model ?? detail;
    if (!target || target.is_embedded_backup) return;
    setEditingName(target.name);
    setForm(modelToForm(target));
    setIsFormOpen(true);
  }

  async function handleSave() {
    if (!form.name.trim() || !form.model.trim()) {
      toast.error(copy.modelsPage.requiredError);
      return;
    }

    const payload: ModelCreateRequest = {
      name: form.name.trim(),
      display_name: form.display_name.trim() || undefined,
      description: form.description.trim() || undefined,
      model: form.model.trim(),
      interface_type: form.interface_type || undefined,
      provider_name: form.provider_name.trim() || undefined,
      use: form.use.trim() || undefined,
      api_key: form.api_key.trim() || undefined,
      base_url: form.base_url.trim() || undefined,
      google_api_key: form.interface_type === "google_genai" ? (form.api_key.trim() || undefined) : undefined,
      fallback_models: form.fallback_models
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      max_context_tokens: form.max_context_tokens.trim()
        ? Number(form.max_context_tokens.trim())
        : undefined,
      supports_thinking: form.supports_thinking,
      supports_reasoning_effort: form.supports_reasoning_effort,
      supports_vision: form.supports_vision,
    };

    try {
      if (isEditing && editingName) {
        await updateModel.mutateAsync({ modelName: editingName, payload });
        toast.success(copy.modelsPage.modelUpdated);
      } else {
        await createModel.mutateAsync(payload);
        toast.success(copy.modelsPage.modelCreated);
      }
      setEditingName(form.name.trim());
      setSelected(form.name.trim());
      setIsFormOpen(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : copy.modelsPage.saveFailed);
    }
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-foreground">{t.sidebar.models}</h1>
          <p className="text-sm text-muted-foreground">
            {copy.modelsPage.pageDescription}
          </p>
        </div>
        <Button size="sm" onClick={startCreate}>
          <PlusIcon className="size-4" />
          {copy.modelsPage.addModel}
        </Button>
      </header>

      {fallbackStatus ? (
        <section
          data-testid="fallback-pool-status"
          aria-label="Free fallback model pool status"
          className="octo-panel mb-5 flex flex-col gap-2 rounded-[1rem] p-4 text-sm sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="flex items-center gap-2">
            <Badge variant={fallbackStatus.enabled ? "default" : "secondary"} className="text-[10px]">
              {fallbackStatus.enabled ? "Fallback pool: active" : "Fallback pool: disabled"}
            </Badge>
            <span className="text-muted-foreground">{fallbackStatus.reason}</span>
          </div>
          <div className="flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
            <span className="font-mono">{fallbackStatus.base_url}</span>
            {fallbackStatus.pool_models.slice(0, 3).map((name) => (
              <Badge key={name} variant="outline" className="text-[10px]">
                {name}
              </Badge>
            ))}
            {fallbackStatus.pool_models.length > 3 ? (
              <span>+{fallbackStatus.pool_models.length - 3}</span>
            ) : null}
          </div>
        </section>
      ) : null}

      {isFormOpen ? (
      <div className="octo-panel mb-6 rounded-[1.5rem] p-5">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-foreground">{isEditing ? copy.modelsPage.editModel : copy.modelsPage.addModel}</div>
            <p className="text-xs text-muted-foreground">
              {copy.modelsPage.formHint}
            </p>
          </div>
          {detail && !detail.is_embedded_backup ? (
            <Button size="sm" variant="outline" onClick={() => startEdit()}>
              <Edit3Icon className="size-4" />
              {copy.modelsPage.editSelected}
            </Button>
          ) : null}
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.configName}</span>
            <Input value={form.name} disabled={isEditing} onChange={(e) => updateField("name", e.target.value)} placeholder="openrouter-sonnet" />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.displayName}</span>
            <Input value={form.display_name} onChange={(e) => updateField("display_name", e.target.value)} placeholder="OpenRouter Sonnet" />
          </label>

          {/* Provider preset — auto-sets interface_type + base_url */}
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.providerName}</span>
            <select
              className="border-input dark:bg-input/30 h-9 w-full rounded-md border bg-transparent px-3 text-sm"
              value={PROVIDER_PRESETS.find((p) => p.value === form.provider_name)?.value ?? "custom"}
              onChange={(e) => {
                const preset = PROVIDER_PRESETS.find((p) => p.value === e.target.value);
                if (preset) {
                  updateField("provider_name", preset.value);
                  updateField("interface_type", preset.interface_type);
                  if (preset.base_url && !form.base_url) {
                    updateField("base_url", preset.base_url);
                  }
                } else {
                  updateField("provider_name", "custom");
                }
              }}
            >
              {PROVIDER_PRESETS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.providerModel}</span>
            <Input value={form.model} onChange={(e) => updateField("model", e.target.value)} placeholder="anthropic/claude-sonnet-4" />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.apiKey}</span>
            <Input type="password" value={form.api_key} onChange={(e) => updateField("api_key", e.target.value)} placeholder={form.interface_type === "google_genai" ? "$GOOGLE_API_KEY" : "$OPENROUTER_API_KEY"} />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.baseUrl}</span>
            <Input value={form.base_url} onChange={(e) => updateField("base_url", e.target.value)} placeholder="https://openrouter.ai/api/v1" />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.interfaceType}</span>
            <select className="border-input dark:bg-input/30 h-9 w-full rounded-md border bg-transparent px-3 text-sm" value={form.interface_type} onChange={(e) => updateField("interface_type", e.target.value)}>
              {INTERFACE_OPTIONS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.maxContextTokens}</span>
            <Input value={form.max_context_tokens} onChange={(e) => updateField("max_context_tokens", e.target.value)} placeholder="200000" />
          </label>
          <div className="flex flex-wrap items-center gap-4 pt-4 text-xs text-muted-foreground md:col-span-2">
            <label className="flex items-center gap-2"><input type="checkbox" checked={form.supports_thinking} onChange={(e) => updateField("supports_thinking", e.target.checked)} /> {copy.modelFields.thinking}</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={form.supports_reasoning_effort} onChange={(e) => updateField("supports_reasoning_effort", e.target.checked)} /> {copy.modelFields.reasoning}</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={form.supports_vision} onChange={(e) => updateField("supports_vision", e.target.checked)} /> {copy.modelFields.vision}</label>
          </div>
          <label className="space-y-1 md:col-span-2">
            <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.description}</span>
            <Textarea value={form.description} onChange={(e) => updateField("description", e.target.value)} placeholder={copy.modelFields.descriptionPlaceholder} />
          </label>

          <div className="rounded-xl border bg-muted/20 p-4 text-xs md:col-span-2">
            <div className="mb-2 text-sm font-medium text-foreground">Unified interface profile</div>
            <p className="mb-3 text-muted-foreground">
              CLI Proxy API compatible providers are now first-class interface options in the model pool.
            </p>
            <div className="grid gap-2 md:grid-cols-3">
              <div><span className="text-muted-foreground">Adapter:</span> <span className="font-mono text-foreground">{contractPreview.adapter}</span></div>
              <div><span className="text-muted-foreground">Request:</span> <span className="font-mono text-foreground">{contractPreview.request}</span></div>
              <div><span className="text-muted-foreground">Response:</span> <span className="font-mono text-foreground">{contractPreview.response}</span></div>
              <div><span className="text-muted-foreground">Streaming:</span> <span className="font-mono text-foreground">{contractPreview.streaming}</span></div>
              <div><span className="text-muted-foreground">Auth:</span> <span className="font-mono text-foreground">{contractPreview.auth}</span></div>
              <div><span className="text-muted-foreground">Semantics:</span> <span className="font-mono text-foreground">{contractPreview.semantics}</span></div>
              <div className="md:col-span-3"><span className="text-muted-foreground">Thinking:</span> <span className="font-mono text-foreground">{contractPreview.thinking}</span></div>
            </div>
          </div>

          {/* Advanced section — collapsible */}
          <div className="md:col-span-2">
            <button
              type="button"
              className="mb-2 text-xs font-medium text-primary hover:underline"
              onClick={() => updateField("showAdvanced", !form.showAdvanced)}
            >
              {form.showAdvanced ? "▼ Hide Advanced" : "▶ Show Advanced (Custom Use Path, Fallback Chain)"}
            </button>
            {form.showAdvanced && (
              <div className="grid gap-3 md:grid-cols-2">
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.customUsePath}</span>
                  <Input value={form.use} onChange={(e) => updateField("use", e.target.value)} placeholder="langchain_openai:ChatOpenAI" />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{copy.modelFields.fallbackModels}</span>
                  <Input value={form.fallback_models} onChange={(e) => updateField("fallback_models", e.target.value)} placeholder="gpt-4o-mini, local-backup" />
                </label>
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 flex gap-2">
          <Button size="sm" onClick={() => void handleSave()} disabled={createModel.isPending || updateModel.isPending}>
            <SaveIcon className="size-4" />
            {isEditing ? copy.modelsPage.saveChanges : copy.modelsPage.createModel}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setIsFormOpen(false);
              setEditingName(null);
              setForm(EMPTY_FORM);
            }}
          >
            Close
          </Button>
        </div>
      </div>
      ) : null}

      {isLoading ? (
        <div className="text-sm text-muted-foreground">{t.common.loading}</div>
      ) : models.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <CpuIcon className="mb-3 size-10 opacity-30" />
          <p className="text-sm">{copy.modelsPage.noModels}</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {models.map((model) => (
            <div
              key={model.id ?? model.name}
              role="button"
              tabIndex={0}
              className={`octo-panel flex min-w-0 cursor-pointer flex-col rounded-[1.5rem] p-4 transition-shadow hover:translate-y-[-1px] hover:shadow-[3px_3px_7px_var(--neu-dark-strong),_-3px_-3px_7px_var(--neu-light-strong)] ${selected === (model.id ?? model.name) ? "ring-2 ring-primary" : ""}`}
              onClick={() => setSelected(selected === (model.id ?? model.name) ? null : (model.id ?? model.name))}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  setSelected(selected === (model.id ?? model.name) ? null : (model.id ?? model.name));
                }
              }}
            >
              <div className="mb-2 flex items-start justify-between">
                <h3 className="min-w-0 break-words text-sm font-medium text-foreground">{model.display_name ?? model.name}</h3>
                <div className="ml-2 flex shrink-0 items-center gap-1">
                  {model.is_embedded_backup && (
                    <Badge variant="secondary" className="text-[10px]">{copy.modelsPage.backup}</Badge>
                  )}
                  {!model.is_embedded_backup && (
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-6"
                      title={copy.modelsPage.editModelTitle}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelected(model.id ?? model.name);
                        startEdit(model);
                      }}
                    >
                      <Edit3Icon className="size-3.5 text-muted-foreground hover:text-primary" />
                    </Button>
                  )}
                  {!model.is_embedded_backup && (
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-6"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (window.confirm(copy.modelsPage.deleteConfirm(model.display_name ?? model.name))) {
                          deleteModel.mutate(
                            model.name,
                            {
                              onSuccess: () => {
                                toast.success(copy.modelsPage.modelDeleted);
                                if (selected === (model.id ?? model.name)) setSelected(null);
                              },
                              onError: (err) => toast.error(err instanceof Error ? err.message : copy.modelsPage.deleteFailed),
                            },
                          );
                        }
                      }}
                    >
                      <Trash2Icon className="size-3.5 text-muted-foreground hover:text-destructive" />
                    </Button>
                  )}
                </div>
              </div>
              {model.description && (
                <p className="mb-3 break-words line-clamp-2 text-xs text-muted-foreground">{model.description}</p>
              )}
              <div className="mt-auto flex flex-wrap gap-1.5">
                {(model.interface_type ?? model.resolved_interface_type) && (
                  <Badge variant="secondary" className="text-[10px]">{model.interface_type ?? model.resolved_interface_type}</Badge>
                )}
                {model.provider_name && <Badge variant="outline" className="text-[10px]">{model.provider_name}</Badge>}
                {model.supports_thinking && (
                  <Badge variant="outline" className="border-primary/30 text-[10px] text-primary"><ZapIcon className="mr-0.5 size-3" />{copy.modelFields.thinking}</Badge>
                )}
                {model.supports_reasoning_effort && (
                  <Badge variant="outline" className="border-primary/30 text-[10px] text-primary">{copy.modelFields.reasoning}</Badge>
                )}
                {model.supports_vision && (
                  <Badge variant="outline" className="border-primary/30 text-[10px] text-primary"><EyeIcon className="mr-0.5 size-3" />{copy.modelFields.vision}</Badge>
                )}
                {model.max_context_tokens && (
                  <Badge variant="outline" className="text-[10px]">{copy.modelsPage.contextBadge(Math.round(model.max_context_tokens / 1000))}</Badge>
                )}
                {model.fallback_models && model.fallback_models.length > 0 && (
                  <Badge variant="outline" className="text-[10px]"><CheckCircle2Icon className="mr-0.5 size-3" />{copy.modelsPage.fallbackBadge(model.fallback_models.length)}</Badge>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {detail && (
        <div className="octo-panel mt-6 rounded-[1.5rem] p-5">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-foreground">
            <InfoIcon className="size-4 text-primary" />
            {detail.display_name ?? detail.name}
          </div>
          <dl className="grid gap-y-1.5 text-xs">
            <div className="flex gap-2"><dt className="text-muted-foreground">{copy.modelsPage.nameLabel}:</dt><dd className="font-mono text-foreground">{detail.name}</dd></div>
            {detail.model && <div className="flex gap-2"><dt className="text-muted-foreground">{copy.modelFields.providerModel}:</dt><dd className="font-mono text-foreground">{detail.model}</dd></div>}
            {(detail.interface_type ?? detail.resolved_interface_type) && <div className="flex gap-2"><dt className="text-muted-foreground">{copy.modelsPage.interfaceLabel}:</dt><dd className="font-mono text-foreground">{detail.interface_type ?? detail.resolved_interface_type}</dd></div>}
            {detail.provider_name && <div className="flex gap-2"><dt className="text-muted-foreground">{copy.modelsPage.providerLabel}:</dt><dd className="text-foreground">{detail.provider_name}</dd></div>}
            {detail.use && <div className="flex gap-2"><dt className="text-muted-foreground">{copy.modelsPage.customUseLabel}:</dt><dd className="font-mono text-foreground">{detail.use}</dd></div>}
            {detail.resolved_use_path && <div className="flex gap-2"><dt className="text-muted-foreground">Resolved use:</dt><dd className="font-mono text-foreground">{detail.resolved_use_path}</dd></div>}
            {detail.adapter_type && <div className="flex gap-2"><dt className="text-muted-foreground">Adapter:</dt><dd className="font-mono text-foreground">{detail.adapter_type}</dd></div>}
            {detail.adapter_request_contract && <div className="flex gap-2"><dt className="text-muted-foreground">Request contract:</dt><dd className="font-mono text-foreground">{detail.adapter_request_contract}</dd></div>}
            {detail.adapter_response_contract && <div className="flex gap-2"><dt className="text-muted-foreground">Response contract:</dt><dd className="font-mono text-foreground">{detail.adapter_response_contract}</dd></div>}
            {detail.adapter_streaming_contract && <div className="flex gap-2"><dt className="text-muted-foreground">Streaming contract:</dt><dd className="font-mono text-foreground">{detail.adapter_streaming_contract}</dd></div>}
            {detail.adapter_auth_mode && <div className="flex gap-2"><dt className="text-muted-foreground">Auth mode:</dt><dd className="font-mono text-foreground">{detail.adapter_auth_mode}</dd></div>}
            {detail.semantic_format && <div className="flex gap-2"><dt className="text-muted-foreground">Semantic format:</dt><dd className="font-mono text-foreground">{detail.semantic_format}</dd></div>}
            {detail.thinking_semantics && <div className="flex gap-2"><dt className="text-muted-foreground">Thinking semantics:</dt><dd className="font-mono text-foreground">{detail.thinking_semantics}</dd></div>}
            {typeof detail.proxy_compatible === "boolean" && <div className="flex gap-2"><dt className="text-muted-foreground">Proxy compatible:</dt><dd>{detail.proxy_compatible ? copy.modelsPage.yes : copy.modelsPage.no}</dd></div>}
            {detail.description && <div className="flex gap-2"><dt className="text-muted-foreground">{copy.modelsPage.descriptionLabel}:</dt><dd className="text-foreground">{detail.description}</dd></div>}
            <div className="flex gap-2"><dt className="text-muted-foreground">{copy.modelsPage.thinkingLabel}:</dt><dd>{detail.supports_thinking ? copy.modelsPage.yes : copy.modelsPage.no}</dd></div>
            <div className="flex gap-2"><dt className="text-muted-foreground">{copy.modelsPage.reasoningLabel}:</dt><dd>{detail.supports_reasoning_effort ? copy.modelsPage.yes : copy.modelsPage.no}</dd></div>
            <div className="flex gap-2"><dt className="text-muted-foreground">{copy.modelsPage.visionLabel}:</dt><dd>{detail.supports_vision ? copy.modelsPage.yes : copy.modelsPage.no}</dd></div>
            {detail.max_context_tokens && <div className="flex gap-2"><dt className="text-muted-foreground">{copy.modelsPage.contextWindowLabel}:</dt><dd>{detail.max_context_tokens.toLocaleString()} tokens</dd></div>}
            {detail.fallback_models && detail.fallback_models.length > 0 && <div className="flex gap-2"><dt className="text-muted-foreground">{copy.modelsPage.fallbackChainLabel}:</dt><dd className="font-mono">{detail.fallback_models.join(" -> ")}</dd></div>}
          </dl>
        </div>
      )}
    </div>
  );
}
