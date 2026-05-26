"use client";

import { ArrowLeftIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { AgentAvatar } from "@/components/brand/octo-mark";
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
import { useAgentTemplate, useAgentTemplates, useCreateAgent } from "@/core/agents";
import { checkAgentName } from "@/core/agents/api";
import { useI18n } from "@/core/i18n/hooks";
import { useModels } from "@/core/models/hooks";
import {
  getModelProviderValue,
  listModelOptionsForProvider,
  listProviderValues,
  MODEL_NONE,
  PROVIDER_ALL,
  resolveModelDisplayName,
} from "@/core/models/model-selection";
import { useInstallAgencyAgents } from "@/core/skills/hooks";
import { cn } from "@/lib/utils";

const NAME_RE = /^[A-Za-z0-9-]+$/;
const TEMPLATE_NONE = "__none__";

export default function NewAgentPage() {
  const { t } = useI18n();
  const router = useRouter();
  const createAgent = useCreateAgent();
  const installAgencyAgents = useInstallAgencyAgents();
  const { models } = useModels();
  const { templates, isLoading: templatesLoading } = useAgentTemplates();

  const [nameInput, setNameInput] = useState("");
  const [nameError, setNameError] = useState("");
  const [selectedTemplateKey, setSelectedTemplateKey] = useState(TEMPLATE_NONE);
  const [description, setDescription] = useState("");
  const [model, setModel] = useState(MODEL_NONE);
  const [provider, setProvider] = useState(PROVIDER_ALL);
  const [soul, setSoul] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [requestedTemplateKey, setRequestedTemplateKey] = useState(TEMPLATE_NONE);

  const providerOptions = useMemo(() => listProviderValues(models), [models]);
  const visibleModels = useMemo(
    () => listModelOptionsForProvider(models, provider, model),
    [models, provider, model],
  );
  const currentProviderLabel =
    (model === MODEL_NONE
      ? null
      : models.find((candidate) => candidate.name === model)?.provider_name?.trim())
    ?? t.agents.providerAuto;
  const currentModelLabel =
    resolveModelDisplayName(models, model) ?? t.agents.modelNone;
  const selectedTemplateParts = useMemo(() => {
    if (selectedTemplateKey === TEMPLATE_NONE) {
      return { skillName: null, templateId: null };
    }
    const [rawSkillName, ...rest] = selectedTemplateKey.split(":");
    const skillName = rawSkillName ?? "";
    const templateId = rest.join(":");
    return {
      skillName: skillName.length > 0 ? skillName : null,
      templateId: templateId.length > 0 ? templateId : null,
    };
  }, [selectedTemplateKey]);
  const { template, isLoading: templateLoading } = useAgentTemplate(
    selectedTemplateParts.skillName,
    selectedTemplateParts.templateId,
  );
  const selectedTemplateSummary = useMemo(
    () => templates.find((entry) => `${entry.skill_name}:${entry.template_id}` === selectedTemplateKey) ?? null,
    [selectedTemplateKey, templates],
  );
  const hasAgencyAgentsInstalled = useMemo(
    () => templates.some((entry) => entry.skill_name === "agency-agents"),
    [templates],
  );

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setRequestedTemplateKey(params.get("template") ?? TEMPLATE_NONE);
  }, []);

  useEffect(() => {
    if (requestedTemplateKey === TEMPLATE_NONE || templates.length === 0) {
      return;
    }
    if (templates.some((entry) => `${entry.skill_name}:${entry.template_id}` === requestedTemplateKey)) {
      setSelectedTemplateKey(requestedTemplateKey);
    }
  }, [requestedTemplateKey, templates]);

  useEffect(() => {
    if (!template) {
      return;
    }
    setDescription(template.description ?? "");
    setSoul(template.soul ?? "");
    if (template.model) {
      setModel(template.model);
      setProvider(getModelProviderValue(models, template.model));
    }
  }, [models, template]);

  const handleProviderChange = (nextProvider: string) => {
    setProvider(nextProvider);
    if (nextProvider === PROVIDER_ALL) {
      return;
    }
    const nextModel = models.find(
      (candidate) => (candidate.provider_name?.trim() ?? "") === nextProvider,
    );
    if (nextModel) {
      setModel(nextModel.name);
    }
  };

  const handleModelChange = (nextModel: string) => {
    setModel(nextModel);
    setProvider(getModelProviderValue(models, nextModel));
  };

  const handleSubmit = useCallback(async () => {
    const trimmedName = nameInput.trim();
    if (!trimmedName) return;

    if (!NAME_RE.test(trimmedName)) {
      setNameError(t.agents.nameStepInvalidError);
      return;
    }

    setNameError("");
    setIsSubmitting(true);

    try {
      const result = await checkAgentName(trimmedName);
      if (!result.available) {
        setNameError(t.agents.nameStepAlreadyExistsError);
        return;
      }

      await createAgent.mutateAsync({
        name: trimmedName,
        description: description || undefined,
        model: model === MODEL_NONE ? null : model,
        soul: soul || undefined,
      });

      toast.success(t.agents.agentCreated);
      router.push(`/workspace/agents/${trimmedName}/chats/new`);
    } catch (err) {
      if (!nameError) {
        toast.error(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setIsSubmitting(false);
    }
  }, [
    nameInput,
    description,
    model,
    soul,
    nameError,
    createAgent,
    router,
    t.agents,
  ]);

  const handleInstallAgencyAgents = useCallback(async () => {
    try {
      const result = await installAgencyAgents.mutateAsync();
      toast.success(result.message);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t.agents.installAgencyAgentsFailed);
    }
  }, [installAgencyAgents, t.agents.installAgencyAgentsFailed]);

  return (
    <div className="flex size-full flex-col">
      <header className="flex shrink-0 items-center gap-3 border-b px-4 py-3">
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={t.agents.backToGallery}
          title={t.agents.backToGallery}
          onClick={() => router.push("/workspace/agents")}
        >
          <ArrowLeftIcon className="h-4 w-4" />
        </Button>
        <h1 className="text-sm font-semibold">{t.agents.createPageTitle}</h1>
      </header>

      <div className="flex flex-1 justify-center overflow-y-auto px-4 py-8">
        <div className="w-full max-w-lg space-y-8">
          {/* Header */}
          <div className="space-y-3 text-center">
            <div className="mx-auto flex justify-center">
              <AgentAvatar size={56} />
            </div>
            <div className="space-y-1">
              <h2 className="text-xl font-semibold">
                {t.agents.nameStepTitle}
              </h2>
              <p className="text-muted-foreground text-sm">
                {t.agents.nameStepHint}
              </p>
            </div>
          </div>

          {/* Form card */}
          <div className="octo-panel space-y-5 rounded-2xl border p-6">
            {/* Name */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="agent-name" className="text-sm font-medium">
                {t.agents.nameStepPlaceholder}
              </label>
              <Input
                id="agent-name"
                placeholder="code-reviewer"
                value={nameInput}
                onChange={(e) => {
                  setNameInput(e.target.value);
                  setNameError("");
                }}
                className={cn(nameError && "border-destructive")}
              />
              {nameError && (
                <p className="text-destructive text-sm">{nameError}</p>
              )}
            </div>

            {/* Description */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-3">
                <span id="agent-template-label" className="text-sm font-medium">{t.agents.templateLabel}</span>
                {!hasAgencyAgentsInstalled ? (
                  <Button
                    data-testid="agent-template-install-agency-agents"
                    size="sm"
                    variant="outline"
                    onClick={() => void handleInstallAgencyAgents()}
                    disabled={installAgencyAgents.isPending}
                  >
                    {installAgencyAgents.isPending
                      ? t.agents.installingAgencyAgents
                      : t.agents.installAgencyAgents}
                  </Button>
                ) : null}
              </div>
              <Select value={selectedTemplateKey} onValueChange={setSelectedTemplateKey}>
                <SelectTrigger aria-labelledby="agent-template-label" data-testid="agent-template-select">
                  <SelectValue placeholder={t.agents.templateNone} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={TEMPLATE_NONE}>{t.agents.templateNone}</SelectItem>
                  {templates.map((entry) => (
                    <SelectItem
                      key={`${entry.skill_name}:${entry.template_id}`}
                      value={`${entry.skill_name}:${entry.template_id}`}
                    >
                      {entry.name} · {entry.skill_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-muted-foreground text-xs">
                {templatesLoading
                  ? t.common.loading
                  : selectedTemplateSummary
                    ? `${selectedTemplateSummary.description}${selectedTemplateSummary.source_category ? ` · ${selectedTemplateSummary.source_category}` : ""}`
                    : hasAgencyAgentsInstalled
                      ? t.agents.templateHint
                      : t.agents.templateInstallHint}
              </p>
              {templateLoading ? (
                <p className="text-muted-foreground text-xs">{t.common.loading}</p>
              ) : null}
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="agent-description" className="text-sm font-medium">
                {t.agents.descriptionLabel}
              </label>
              <Textarea
                id="agent-description"
                data-testid="agent-template-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
              />
            </div>

            {/* Model */}
            <div className="flex flex-col gap-1.5">
              <span id="agent-provider-label" className="text-sm font-medium">
                {t.agents.providerLabel}
              </span>
              <div className="flex items-center gap-2">
                <Select value={provider} onValueChange={handleProviderChange}>
                  <SelectTrigger aria-labelledby="agent-provider-label" className="flex-1">
                    <SelectValue placeholder={t.agents.providerAll} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={PROVIDER_ALL}>{t.agents.providerAll}</SelectItem>
                    {providerOptions.map((providerName) => (
                      <SelectItem key={providerName} value={providerName}>
                        {providerName}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Badge variant="outline" className="h-9 shrink-0 rounded-md px-3 text-xs">
                  {currentProviderLabel}
                </Badge>
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <span id="agent-model-label" className="text-sm font-medium">
                {t.agents.modelLabel}
              </span>
              <div className="flex items-center gap-2">
                <Select value={model} onValueChange={handleModelChange}>
                  <SelectTrigger aria-labelledby="agent-model-label" className="flex-1">
                    <SelectValue placeholder={t.agents.modelNone} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={MODEL_NONE}>
                      {t.agents.modelNone}
                    </SelectItem>
                    {visibleModels.map((option) => (
                      <SelectItem key={option.name} value={option.name}>
                        {option.display_name ?? option.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Badge variant="outline" className="h-9 shrink-0 rounded-md px-3 text-xs">
                  {currentModelLabel}
                </Badge>
              </div>
            </div>

            {/* Soul */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="agent-soul" className="text-sm font-medium">
                {t.agents.soulLabel}
              </label>
              <Textarea
                id="agent-soul"
                data-testid="agent-template-soul"
                value={soul}
                onChange={(e) => setSoul(e.target.value)}
                rows={6}
                className="font-mono text-xs"
              />
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-2 pt-2">
              <Button
                variant="outline"
                onClick={() => router.push("/workspace/agents")}
                disabled={isSubmitting}
              >
                {t.common.cancel}
              </Button>
              <Button
                onClick={() => void handleSubmit()}
                disabled={!nameInput.trim() || isSubmitting}
              >
                {isSubmitting ? t.common.loading : t.agents.nameStepContinue}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
