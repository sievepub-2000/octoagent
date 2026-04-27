"use client";

import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/core/i18n/hooks";
import { useMCPConfig, useEnableMCPServer } from "@/core/mcp/hooks";
import type { MCPServerConfig } from "@/core/mcp/types";
import { env } from "@/env";

import { SettingsSection } from "./settings-section";

export function ToolSettingsPage() {
  const { t } = useI18n();
  const { config, isLoading, error } = useMCPConfig();
  return (
    <SettingsSection
      title={t.settings.tools.title}
      description={t.settings.tools.description}
    >
      {isLoading ? (
        <div className="text-muted-foreground text-sm">{t.common.loading}</div>
      ) : error ? (
        <div>Error: {error.message}</div>
      ) : (
        config && <MCPServerList servers={config.mcp_servers} />
      )}
    </SettingsSection>
  );
}

function MCPServerList({
  servers,
}: {
  servers: Record<string, MCPServerConfig>;
}) {
  const { mutate: enableMCPServer } = useEnableMCPServer();
  return (
    <div className="flex w-full flex-col gap-2">
      {Object.entries(servers).map(([name, config]) => (
        <Card variant="compact" interactive key={name}>
          <CardHeader>
            <CardTitle>{name}</CardTitle>
            <CardAction>
              <Switch
                checked={config.enabled}
                disabled={env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"}
                onCheckedChange={(checked) =>
                  enableMCPServer({ serverName: name, enabled: checked })
                }
              />
            </CardAction>
          </CardHeader>
          {config.description ? (
            <CardContent>
              <p className="line-clamp-3 text-xs text-muted-foreground">
                {config.description}
              </p>
            </CardContent>
          ) : null}
        </Card>
      ))}
    </div>
  );
}
