"use client";

import { RefreshCcwIcon, WaypointsIcon } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/core/i18n/hooks";
import { useRepoHooks, useUpdateRepoHook } from "@/core/repo-hooks/hooks";

export function HooksSettingsPage() {
  const { t } = useI18n();
  const { hooks, isLoading, error, refetch } = useRepoHooks();
  const updateHook = useUpdateRepoHook();

  async function handleToggle(hookName: string, enabled: boolean) {
    try {
      await updateHook.mutateAsync({ hookName, enabled });
    } catch (toggleError) {
      toast.error(toggleError instanceof Error ? toggleError.message : "Failed to update hook.");
    }
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <WaypointsIcon className="size-5 text-primary" />
              <h1 className="text-lg font-semibold text-foreground">{t.settings.hooks.title}</h1>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{t.settings.hooks.description}</p>
          </div>
          <Button size="sm" variant="outline" onClick={() => void refetch()}>
            <RefreshCcwIcon className="size-4" />
            {t.settings.system.refresh}
          </Button>
        </div>
      </header>

      {isLoading ? (
        <div className="text-sm text-muted-foreground">{t.common.loading}</div>
      ) : error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {error instanceof Error ? error.message : "Failed to load hooks."}
        </div>
      ) : hooks.length === 0 ? (
        <div className="octo-panel rounded-[1.5rem] p-6 text-sm text-muted-foreground">
          <div className="font-medium text-foreground">{t.settings.hooks.emptyTitle}</div>
          <p className="mt-1">{t.settings.hooks.emptyDescription}</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {hooks.map((hook) => (
            <div key={hook.name} className="octo-panel flex flex-col justify-between rounded-[1.5rem] p-4 transition-shadow hover:translate-y-[-1px] hover:shadow-[3px_3px_7px_var(--neu-dark-strong),_-3px_-3px_7px_var(--neu-light-strong)]">
              <div className="mb-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-medium text-foreground">{hook.name}</h3>
                    <p className="mt-1 text-xs text-muted-foreground">{hook.description || hook.files.join(", ")}</p>
                  </div>
                  <Badge variant="outline" className="text-[10px]">
                    {hook.triggers.length} trigger{hook.triggers.length === 1 ? "" : "s"}
                  </Badge>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {hook.triggers.map((trigger) => (
                    <Badge key={trigger.trigger} variant="secondary" className="text-[10px]">
                      {trigger.trigger} · {trigger.command_count}
                    </Badge>
                  ))}
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">{hook.files.length} file{hook.files.length === 1 ? "" : "s"}</span>
                <Switch checked={hook.enabled} onCheckedChange={(checked) => void handleToggle(hook.name, checked)} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}