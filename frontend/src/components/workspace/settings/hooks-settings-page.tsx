"use client";

import { KeyRoundIcon, RefreshCcwIcon, WaypointsIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/core/i18n/hooks";
import { getSurfaceCopy } from "@/core/i18n/surface-copy";
import { useRepoHooks, useUpdateRepoHook } from "@/core/repo-hooks/hooks";

export function HooksSettingsPage() {
  const { locale, t } = useI18n();
  const copy = getSurfaceCopy(locale).hooks;
  const { hooks, isLoading, error, refetch } = useRepoHooks();
  const updateHook = useUpdateRepoHook();
  const [operatorToken, setOperatorToken] = useState("");

  useEffect(() => {
    setOperatorToken(sessionStorage.getItem("octoagent_operator_token") ?? "");
  }, []);

  function saveOperatorToken() {
    const value = operatorToken.trim();
    if (value) sessionStorage.setItem("octoagent_operator_token", value);
    else sessionStorage.removeItem("octoagent_operator_token");
    toast.success(value ? copy.authorizationSaved : copy.authorizationCleared);
  }

  async function handleToggle(hookName: string, enabled: boolean) {
    try {
      await updateHook.mutateAsync({ hookName, enabled });
    } catch (toggleError) {
      toast.error(toggleError instanceof Error ? toggleError.message : copy.updateFailed);
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

      <div className="mb-5 flex flex-wrap items-end gap-2 border-b border-border/60 pb-5">
        <label className="min-w-64 flex-1 space-y-1">
          <span className="text-xs font-medium text-muted-foreground">{copy.operatorToken}</span>
          <Input type="password" autoComplete="off" value={operatorToken} onChange={(event) => setOperatorToken(event.target.value)} placeholder={copy.tokenPlaceholder} />
        </label>
        <Button size="sm" variant="outline" onClick={saveOperatorToken}>
          <KeyRoundIcon className="size-4" />
          {copy.authorize}
        </Button>
      </div>

      {isLoading ? (
        <div className="text-sm text-muted-foreground">{t.common.loading}</div>
      ) : error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {error instanceof Error ? error.message : copy.loadFailed}
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
                    {hook.triggers.length} {copy.triggers}
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
                <span className="text-xs text-muted-foreground">{hook.files.length} {copy.files}</span>
                <Switch checked={hook.enabled} onCheckedChange={(checked) => void handleToggle(hook.name, checked)} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
