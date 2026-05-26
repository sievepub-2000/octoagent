"use client";

import { AlertCircleIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { AgentAvatar } from "@/components/brand/octo-mark";
import { Button } from "@/components/ui/button";
import { useAgents, useDeleteAgent } from "@/core/agents";
import { useI18n } from "@/core/i18n/hooks";

import { AgentCard } from "./agent-card";

export function AgentGallery() {
  const { t } = useI18n();
  const { agents, isLoading, error } = useAgents();
  const deleteAgent = useDeleteAgent();
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);

  const handleNewAgent = () => {
    router.push("/workspace/agents/new");
  };

  const handleDeleteAll = async () => {
    const deletableAgents = agents.filter((agent) => agent.deletable !== false);
    if (!deletableAgents.length) return;
    if (!window.confirm(t.common.deleteAllConfirm)) return;
    setDeleting(true);
    try {
      for (const agent of deletableAgents) {
        await deleteAgent.mutateAsync(agent.name);
      }
      toast.success(t.common.deleteAllSuccess);
    } catch {
      toast.error("Failed to delete some agents");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex size-full flex-col">
      {/* Page header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold">{t.agents.title}</h1>
          <p className="text-muted-foreground mt-0.5 text-sm">
            {t.agents.description}
          </p>
        </div>
        <div className="flex gap-2">
          {agents.some((agent) => agent.deletable !== false) && (
            <Button
              size="sm"
              variant="destructive"
              disabled={deleting}
              onClick={handleDeleteAll}
            >
              <Trash2Icon className="mr-1 size-3.5" />
              {t.common.deleteAll}
            </Button>
          )}
          <Button onClick={handleNewAgent}>
            <PlusIcon className="mr-1.5 h-4 w-4" />
            {t.agents.newAgent}
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <div className="text-muted-foreground flex h-40 items-center justify-center text-sm">
            {t.common.loading}
          </div>
        ) : error ? (
          <div className="flex h-64 flex-col items-center justify-center gap-3 text-center text-muted-foreground">
            <AlertCircleIcon className="size-10" />
            <div>
              <p className="font-medium text-foreground">{t.agents.loadFailedTitle}</p>
              <p className="mt-1 max-w-sm text-sm">
                {error instanceof Error ? error.message : t.agents.loadFailedDescription}
              </p>
            </div>
            <Button variant="outline" className="mt-2" onClick={() => window.location.reload()}>
              {t.agents.reloadAgents}
            </Button>
          </div>
        ) : agents.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center gap-3 text-center">
            <AgentAvatar size={56} />
            <div>
              <p className="font-medium">{t.agents.emptyTitle}</p>
              <p className="text-muted-foreground mt-1 text-sm">
                {t.agents.emptyDescription}
              </p>
            </div>
            <Button variant="outline" className="mt-2" onClick={handleNewAgent}>
              <PlusIcon className="mr-1.5 h-4 w-4" />
              {t.agents.newAgent}
            </Button>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {agents.map((agent) => (
              <AgentCard key={agent.id ?? agent.name} agent={agent} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
