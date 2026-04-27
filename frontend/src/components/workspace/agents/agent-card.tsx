"use client";

import {
  ImagePlusIcon,
  MessageSquareIcon,
  SettingsIcon,
  Trash2Icon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { AgentAvatar } from "@/components/brand/octo-mark";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useDeleteAgent, useUpdateAgent } from "@/core/agents";
import type { Agent } from "@/core/agents";
import { agentAvatarUrl, uploadAgentAvatar } from "@/core/agents/api";
import { useI18n } from "@/core/i18n/hooks";
import { useModels } from "@/core/models/hooks";
import {
  findModelByValue,
  getModelProviderValue,
  listModelOptionsForProvider,
  listProviderValues,
  MODEL_NONE,
  PROVIDER_ALL,
  resolveModelDisplayName,
} from "@/core/models/model-selection";

interface AgentCardProps {
  agent: Agent;
}

export function AgentCard({ agent }: AgentCardProps) {
  const { t } = useI18n();
  const router = useRouter();
  const deleteAgent = useDeleteAgent();
  const updateAgent = useUpdateAgent();
  const { models } = useModels();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Settings form state
  const [agentName, setAgentName] = useState(agent.name);
  const [description, setDescription] = useState(agent.description ?? "");
  const [model, setModel] = useState(agent.model ?? MODEL_NONE);
  const [provider, setProvider] = useState(PROVIDER_ALL);
  const [soul, setSoul] = useState(agent.soul ?? "");
  const [avatarUploading, setAvatarUploading] = useState(false);
  const [avatarKey, setAvatarKey] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync form when agent prop changes
  useEffect(() => {
    setAgentName(agent.name);
    setDescription(agent.description ?? "");
    setModel(agent.model ?? MODEL_NONE);
    setProvider(getModelProviderValue(models, agent.model ?? MODEL_NONE));
    setSoul(agent.soul ?? "");
  }, [agent, models]);

  const providerOptions = useMemo(() => listProviderValues(models), [models]);
  const selectedModelDefinition = useMemo(
    () => findModelByValue(models, model),
    [models, model],
  );
  const visibleModels = useMemo(
    () => listModelOptionsForProvider(models, provider, model),
    [models, provider, model],
  );
  const currentProviderLabel =
    selectedModelDefinition?.provider_name?.trim() ?? t.agents.providerAuto;
  const currentModelLabel =
    resolveModelDisplayName(models, model) ?? t.agents.modelNone;

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

  function handleChat() {
    router.push(`/workspace/agents/${agent.name}/chats/new`);
  }

  async function handleDelete() {
    try {
      await deleteAgent.mutateAsync(agent.name);
      toast.success(t.agents.deleteSuccess);
      setDeleteOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleSaveSettings() {
    try {
      const trimmedName = agentName.trim().toLowerCase();
      if (!trimmedName || !/^[a-z0-9-]+$/.test(trimmedName)) {
        toast.error(t.agents.nameStepInvalidError);
        return;
      }
      await updateAgent.mutateAsync({
        name: agent.name,
        request: {
          name: trimmedName !== agent.name ? trimmedName : undefined,
          description: description || null,
          model: model === MODEL_NONE ? null : model,
          soul: soul || null,
        },
      });
      toast.success(t.agents.saveSuccess);
      setSettingsOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleAvatarUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setAvatarUploading(true);
    try {
      await uploadAgentAvatar(agent.name, file);
      setAvatarKey((k) => k + 1);
      toast.success("Avatar uploaded");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setAvatarUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  const customAvatarUrl = agent.avatar
    ? `${agentAvatarUrl(agent.name)}?v=${avatarKey}`
    : null;

  return (
    <>
      <Card className="octo-panel group flex flex-col rounded-[1.5rem] border-primary/20 transition-shadow hover:translate-y-[-1px] hover:shadow-[3px_3px_7px_var(--neu-dark-strong),_-3px_-3px_7px_var(--neu-light-strong)]">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <AgentAvatar size={40} avatarUrl={customAvatarUrl} />
              <div className="min-w-0">
                <CardTitle className="break-words text-base leading-5">
                  {agent.name}
                </CardTitle>
                {agent.model && (
                  <Badge variant="secondary" className="mt-0.5 max-w-full text-xs">
                    {agent.model}
                  </Badge>
                )}
              </div>
            </div>
          </div>
          {agent.description && (
            <CardDescription className="mt-2 break-words line-clamp-2 text-sm">
              {agent.description}
            </CardDescription>
          )}
        </CardHeader>

        <CardFooter className="mt-auto flex items-center justify-between gap-2 pt-3">
          <Button size="sm" className="flex-1" onClick={handleChat}>
            <MessageSquareIcon className="mr-1.5 h-3.5 w-3.5" />
            {t.agents.chat}
          </Button>
          <div className="flex gap-1">
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 shrink-0"
              onClick={() => setSettingsOpen(true)}
              title={t.agents.settings}
            >
              <SettingsIcon className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="text-destructive hover:text-destructive h-8 w-8 shrink-0"
              onClick={() => setDeleteOpen(true)}
              title={t.agents.delete}
            >
              <Trash2Icon className="h-3.5 w-3.5" />
            </Button>
          </div>
        </CardFooter>
      </Card>

      {/* Settings Dialog */}
      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t.agents.settingsTitle}</DialogTitle>
            <DialogDescription>{agent.name}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-2">
            {/* Agent Name + Avatar — side by side, full width */}
            <div className="flex items-center gap-4">
              {/* Name (left, takes remaining space) */}
              <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                <span className="text-sm font-medium">{t.agents.nameLabel}</span>
                <Input
                  value={agentName}
                  onChange={(e) => setAgentName(e.target.value)}
                />
              </div>
              {/* Avatar (right, fixed) */}
              <div className="flex shrink-0 flex-col items-center gap-1.5">
                <span className="text-sm font-medium">{t.agents.avatarLabel}</span>
                <div className="relative cursor-pointer" onClick={() => fileInputRef.current?.click()}>
                  <AgentAvatar size={48} avatarUrl={customAvatarUrl} />
                  <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/30 opacity-0 transition-opacity hover:opacity-100">
                    <ImagePlusIcon className="h-4 w-4 text-white" />
                  </div>
                </div>
                <span className="text-[10px] text-muted-foreground">{avatarUploading ? t.agents.avatarUploading : t.agents.avatarClickToChange}</span>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".png,.jpg,.jpeg,.gif,.webp,.svg"
                  aria-label={t.agents.avatarLabel}
                  className="hidden"
                  onChange={handleAvatarUpload}
                />
              </div>
            </div>
            {/* Description */}
            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">
                {t.agents.descriptionLabel}
              </span>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
              />
            </div>
            {/* Model */}
            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">
                {t.agents.providerLabel}
              </span>
              <div className="flex items-center gap-2">
                <Select value={provider} onValueChange={handleProviderChange}>
                  <SelectTrigger className="flex-1">
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
                <Badge variant="outline" className="shrink-0 text-xs">
                  {currentProviderLabel}
                </Badge>
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">
                {t.agents.modelLabel}
              </span>
              <div className="flex items-center gap-2">
                <Select value={model} onValueChange={handleModelChange}>
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder={t.agents.modelNone} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={MODEL_NONE}>{t.agents.modelNone}</SelectItem>
                    {visibleModels.map((option) => (
                      <SelectItem key={option.name} value={option.name}>
                        {option.display_name ?? option.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Badge variant="outline" className="shrink-0 text-xs">
                  {currentModelLabel}
                </Badge>
              </div>
            </div>
            {/* Soul */}
            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">
                {t.agents.soulLabel}
              </span>
              <Textarea
                value={soul}
                onChange={(e) => setSoul(e.target.value)}
                rows={6}
                className="font-mono text-xs"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setSettingsOpen(false)}
              disabled={updateAgent.isPending}
            >
              {t.common.cancel}
            </Button>
            <Button
              onClick={handleSaveSettings}
              disabled={updateAgent.isPending}
            >
              {updateAgent.isPending ? t.common.loading : t.common.save}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirm */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t.agents.delete}</DialogTitle>
            <DialogDescription>{t.agents.deleteConfirm}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteOpen(false)}
              disabled={deleteAgent.isPending}
            >
              {t.common.cancel}
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteAgent.isPending}
            >
              {deleteAgent.isPending ? t.common.loading : t.common.delete}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
