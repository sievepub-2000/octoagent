"use client";

import { CheckCircle2Icon, CpuIcon, Edit3Icon, EyeIcon, PlusIcon, SaveIcon, Trash2Icon, ZapIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useCreateModel, useDeleteModel, useModels, useSetDefaultModel, useTestModelConnection, useUpdateModel } from "@/core/models/hooks";
import type { Model, ModelCreateRequest } from "@/core/models/types";

const PROVIDERS = [
  { value: "openai", label: "OpenAI", interfaceType: "openai_compatible", baseUrl: "https://api.openai.com/v1" },
  { value: "anthropic", label: "Anthropic", interfaceType: "anthropic_messages", baseUrl: "https://api.anthropic.com" },
  { value: "google", label: "Google Gemini", interfaceType: "google_genai", baseUrl: "https://generativelanguage.googleapis.com/v1beta" },
  { value: "openrouter", label: "OpenRouter", interfaceType: "openai_compatible", baseUrl: "https://openrouter.ai/api/v1" },
  { value: "deepseek", label: "DeepSeek", interfaceType: "deepseek_reasoner", baseUrl: "https://api.deepseek.com/v1" },
  { value: "local", label: "Local / OpenAI compatible", interfaceType: "openai_compatible", baseUrl: "http://localhost:8000/v1" },
  { value: "custom", label: "Custom", interfaceType: "openai_compatible", baseUrl: "" },
] as const;

type FormState = {
  name: string;
  displayName: string;
  description: string;
  provider: string;
  model: string;
  interfaceType: string;
  apiKey: string;
  baseUrl: string;
  contextTokens: string;
  supportsThinking: boolean;
  supportsReasoning: boolean;
  supportsVision: boolean;
};

const EMPTY_FORM: FormState = {
  name: "", displayName: "", description: "", provider: "openai", model: "",
  interfaceType: "openai_compatible", apiKey: "", baseUrl: "https://api.openai.com/v1",
  contextTokens: "", supportsThinking: false, supportsReasoning: false, supportsVision: false,
};

function formFromModel(model: Model): FormState {
  return {
    name: model.name,
    displayName: model.display_name ?? "",
    description: model.description ?? "",
    provider: model.provider_name ?? "custom",
    model: model.model ?? "",
    interfaceType: model.interface_type ?? model.resolved_interface_type ?? "openai_compatible",
    apiKey: "",
    baseUrl: "",
    contextTokens: model.max_context_tokens ? String(model.max_context_tokens) : "",
    supportsThinking: Boolean(model.supports_thinking),
    supportsReasoning: Boolean(model.supports_reasoning_effort),
    supportsVision: Boolean(model.supports_vision),
  };
}

export default function ModelsConfigPage() {
  const { models, isLoading } = useModels();
  const createModel = useCreateModel();
  const updateModel = useUpdateModel();
  const deleteModel = useDeleteModel();
  const setDefaultModel = useSetDefaultModel();
  const testConnection = useTestModelConnection();
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const detail = models.find((model) => model.name === selected);

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((current) => ({ ...current, [key]: value }));
  const closeForm = () => { setEditing(null); setForm(EMPTY_FORM); setShowForm(false); };

  const startEdit = (model: Model) => {
    setSelected(model.name);
    setEditing(model.name);
    setForm(formFromModel(model));
    setShowForm(true);
  };

  const save = async () => {
    if (!form.name.trim() || !form.model.trim()) {
      toast.error("Configuration name and provider model ID are required.");
      return;
    }
    const payload: ModelCreateRequest = {
      name: form.name.trim(),
      display_name: form.displayName.trim() || undefined,
      description: form.description.trim() || undefined,
      provider_name: form.provider.trim() || undefined,
      model: form.model.trim(),
      interface_type: form.interfaceType,
      api_key: form.apiKey.trim() || undefined,
      google_api_key: form.interfaceType === "google_genai" ? (form.apiKey.trim() || undefined) : undefined,
      base_url: form.baseUrl.trim() || undefined,
      max_context_tokens: form.contextTokens.trim() ? Number(form.contextTokens) : undefined,
      supports_thinking: form.supportsThinking,
      supports_reasoning_effort: form.supportsReasoning,
      supports_vision: form.supportsVision,
      fallback_models: [],
    };
    try {
      if (editing) await updateModel.mutateAsync({ modelName: editing, payload });
      else await createModel.mutateAsync(payload);
      toast.success(editing ? "Model updated." : "Model added.");
      setSelected(form.name.trim());
      closeForm();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save model.");
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Models</h1>
          <p className="text-sm text-muted-foreground">Connect local models or any supported open-source and commercial API.</p>
        </div>
        <Button size="sm" onClick={() => { setEditing(null); setForm(EMPTY_FORM); setShowForm(true); }}><PlusIcon className="size-4" />Add model</Button>
      </header>

      {showForm ? (
        <section className="octo-panel mb-6 rounded-[1.5rem] p-5">
          <div className="mb-4">
            <h2 className="text-sm font-medium">{editing ? "Edit model" : "Add model"}</h2>
            <p className="text-xs text-muted-foreground">Credentials are stored as environment-variable references, never as raw keys.</p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1"><span className="text-xs text-muted-foreground">Configuration name</span><Input value={form.name} disabled={Boolean(editing)} onChange={(event) => setField("name", event.target.value)} placeholder="openai-gpt" /></label>
            <label className="space-y-1"><span className="text-xs text-muted-foreground">Display name</span><Input value={form.displayName} onChange={(event) => setField("displayName", event.target.value)} placeholder="GPT" /></label>
            <label className="space-y-1"><span className="text-xs text-muted-foreground">Provider</span><select className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm" value={form.provider} onChange={(event) => { const preset = PROVIDERS.find((item) => item.value === event.target.value); if (preset) setForm((current) => ({ ...current, provider: preset.value, interfaceType: preset.interfaceType, baseUrl: preset.baseUrl })); }}>{PROVIDERS.map((provider) => <option key={provider.value} value={provider.value}>{provider.label}</option>)}</select></label>
            <label className="space-y-1"><span className="text-xs text-muted-foreground">Provider model ID</span><Input value={form.model} onChange={(event) => setField("model", event.target.value)} placeholder="gpt-5.2 or local-model-name" /></label>
            <label className="space-y-1"><span className="text-xs text-muted-foreground">API key environment variable</span><Input value={form.apiKey} onChange={(event) => setField("apiKey", event.target.value)} placeholder="$OPENAI_API_KEY (blank for no-auth local model)" /><span className="block text-[11px] text-muted-foreground">Set the referenced variable in the service environment before testing.</span></label>
            <label className="space-y-1"><span className="text-xs text-muted-foreground">Base URL</span><Input value={form.baseUrl} onChange={(event) => setField("baseUrl", event.target.value)} placeholder="https://api.example.com/v1" /></label>
            <label className="space-y-1"><span className="text-xs text-muted-foreground">Interface</span><select className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm" value={form.interfaceType} onChange={(event) => setField("interfaceType", event.target.value)}><option value="openai_compatible">OpenAI compatible</option><option value="anthropic_messages">Anthropic Messages</option><option value="google_genai">Google GenAI</option><option value="deepseek_reasoner">DeepSeek Reasoner</option><option value="generic">Custom LangChain adapter</option></select></label>
            <label className="space-y-1"><span className="text-xs text-muted-foreground">Context window</span><Input inputMode="numeric" value={form.contextTokens} onChange={(event) => setField("contextTokens", event.target.value)} placeholder="128000" /></label>
            <label className="space-y-1 md:col-span-2"><span className="text-xs text-muted-foreground">Description</span><Textarea value={form.description} onChange={(event) => setField("description", event.target.value)} /></label>
            <div className="flex flex-wrap gap-4 text-xs text-muted-foreground md:col-span-2">
              <label className="flex items-center gap-2"><input type="checkbox" checked={form.supportsThinking} onChange={(event) => setField("supportsThinking", event.target.checked)} />Thinking</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={form.supportsReasoning} onChange={(event) => setField("supportsReasoning", event.target.checked)} />Reasoning effort</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={form.supportsVision} onChange={(event) => setField("supportsVision", event.target.checked)} />Vision</label>
            </div>
          </div>
          <div className="mt-4 flex gap-2"><Button size="sm" onClick={() => void save()} disabled={createModel.isPending || updateModel.isPending}><SaveIcon className="size-4" />Save</Button><Button size="sm" variant="outline" onClick={closeForm}>Cancel</Button></div>
        </section>
      ) : null}

      {isLoading ? <p className="text-sm text-muted-foreground">Loading models…</p> : models.length === 0 ? <div className="py-16 text-center text-sm text-muted-foreground"><CpuIcon className="mx-auto mb-3 size-10 opacity-30" />No models configured.</div> : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {models.map((model) => (
            <article key={model.name} className={`octo-panel rounded-[1.5rem] p-4 ${selected === model.name ? "ring-2 ring-primary" : ""}`}>
              <button type="button" className="w-full text-left" onClick={() => setSelected(selected === model.name ? null : model.name)}>
                <div className="flex items-start justify-between gap-2"><h2 className="text-sm font-medium">{model.display_name ?? model.name}</h2>{model.is_default ? <Badge>Default</Badge> : null}</div>
                <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{model.description || model.model}</p>
                <div className="mt-3 flex flex-wrap gap-1.5"><Badge variant="outline">{model.provider_name || "custom"}</Badge><Badge variant="secondary">{model.interface_type ?? model.resolved_interface_type}</Badge>{model.supports_thinking ? <Badge variant="outline"><ZapIcon className="mr-1 size-3" />Thinking</Badge> : null}{model.supports_vision ? <Badge variant="outline"><EyeIcon className="mr-1 size-3" />Vision</Badge> : null}</div>
              </button>
            </article>
          ))}
        </div>
      )}

      {detail ? (
        <section className="octo-panel mt-5 rounded-[1.5rem] p-5">
          <div className="flex flex-wrap items-center gap-2"><h2 className="mr-auto text-sm font-medium">{detail.display_name ?? detail.name}</h2>{!detail.is_default ? <Button size="sm" variant="outline" disabled={setDefaultModel.isPending} onClick={() => setDefaultModel.mutate(detail.name, { onSuccess: () => toast.success("Default model updated.") })}><CheckCircle2Icon className="size-4" />Set default</Button> : null}<Button size="sm" variant="outline" disabled={testConnection.isPending} onClick={() => testConnection.mutate(detail.name, { onSuccess: (result) => toast.success(`Healthy · ${result.latency_ms} ms · ${result.response_preview}`) })}>{testConnection.isPending ? "Testing…" : "Test connection"}</Button><Button size="sm" variant="outline" onClick={() => startEdit(detail)}><Edit3Icon className="size-4" />Edit</Button><Button size="sm" variant="outline" onClick={() => { if (window.confirm(`Delete ${detail.display_name ?? detail.name}?`)) deleteModel.mutate(detail.name, { onSuccess: () => { setSelected(null); toast.success("Model deleted."); } }); }}><Trash2Icon className="size-4" />Delete</Button></div>
          <dl className="mt-4 grid gap-2 text-xs md:grid-cols-2"><div><dt className="text-muted-foreground">Provider model</dt><dd className="font-mono">{detail.model}</dd></div><div><dt className="text-muted-foreground">Interface</dt><dd className="font-mono">{detail.interface_type ?? detail.resolved_interface_type}</dd></div><div><dt className="text-muted-foreground">Adapter</dt><dd className="font-mono">{detail.adapter_type}</dd></div><div><dt className="text-muted-foreground">Context</dt><dd>{detail.max_context_tokens?.toLocaleString() ?? "Not declared"} tokens</dd></div></dl>
        </section>
      ) : null}
    </div>
  );
}
