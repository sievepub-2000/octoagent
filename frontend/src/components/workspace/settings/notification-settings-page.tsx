"use client";

import { BellIcon, BellOffIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/core/i18n/hooks";
import { useNotification } from "@/core/notification/hooks";
import { useLocalSettings } from "@/core/settings";

import { SettingsSection } from "./settings-section";

export function NotificationSettingsPage() {
  const { t } = useI18n();
  const { permission, isSupported, requestPermission, showNotification } =
    useNotification();

  const [settings, setSettings] = useLocalSettings();

  const handleRequestPermission = async () => {
    await requestPermission();
  };

  const handleTestNotification = () => {
    showNotification(t.settings.notification.testTitle, {
      body: t.settings.notification.testBody,
    });
  };

  const handleEnableNotification = async (enabled: boolean) => {
    setSettings("notification", {
      enabled,
    });
  };

  if (!isSupported) {
    return (
      <SettingsSection
        title={t.settings.notification.title}
        description={t.settings.notification.description}
      >
        <p className="text-muted-foreground text-sm">
          {t.settings.notification.notSupported}
        </p>
      </SettingsSection>
    );
  }

  return (
    <SettingsSection
      title={t.settings.notification.title}
      description={
        <div className="flex items-center gap-2">
          <div>{t.settings.notification.description}</div>
          <div>
            <Switch
              disabled={permission !== "granted"}
              checked={
                permission === "granted" && settings.notification.enabled
              }
              onCheckedChange={handleEnableNotification}
            />
          </div>
        </div>
      }
    >
      <div className="space-y-3">
        {permission === "default" && (
          <Card variant="compact">
            <CardContent className="pt-4">
              <Button size="sm" onClick={handleRequestPermission} variant="default">
                <BellIcon className="size-3.5" />
                {t.settings.notification.requestPermission}
              </Button>
            </CardContent>
          </Card>
        )}

        {permission === "denied" && (
          <Card variant="status" className="border-l-amber-500/60">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
                <BellOffIcon className="size-4" />
                Permission denied
              </CardTitle>
              <CardDescription>
                {t.settings.notification.deniedHint}
              </CardDescription>
            </CardHeader>
          </Card>
        )}

        {permission === "granted" && settings.notification.enabled && (
          <Card variant="compact">
            <CardContent className="pt-4">
              <Button size="sm" onClick={handleTestNotification} variant="outline">
                <BellIcon className="size-3.5" />
                {t.settings.notification.testButton}
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </SettingsSection>
  );
}
