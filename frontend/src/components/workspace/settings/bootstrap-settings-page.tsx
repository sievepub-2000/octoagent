"use client";

import { CpuIcon, DownloadIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useBootstrapStatus,
  useInstallBootstrapModel,
} from "@/core/bootstrap";
import { useI18n } from "@/core/i18n/hooks";

import { SettingsSection } from "./settings-section";

export function BootstrapSettingsPage() {
  const { t } = useI18n();
  const b = t.settings.bootstrap;
  const { bootstrap, isLoading } = useBootstrapStatus();
  const install = useInstallBootstrapModel();

  return (
    <SettingsSection
      title={b.title}
      description={b.description}
    >
      {isLoading || !bootstrap ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
        </div>
      ) : (
        <div className="space-y-3">
          <Card variant="status" className="border-l-blue-500/60">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CpuIcon className="size-4 text-blue-500" />
                {b.recommendedRuntime}
              </CardTitle>
              <CardDescription>
                {bootstrap.framework} + {bootstrap.recommended_model}
              </CardDescription>
            </CardHeader>
          </Card>

          <div className="grid gap-3 md:grid-cols-2">
            <Card variant="compact">
              <CardHeader>
                <CardTitle>{b.modelStatus}</CardTitle>
                <CardAction>
                  <Badge variant={bootstrap.installed ? "secondary" : "outline"} className="text-xs">
                    {bootstrap.installed ? b.installed : b.notInstalled}
                  </Badge>
                </CardAction>
              </CardHeader>
              <CardContent>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <p className="truncate" title={bootstrap.repo_id}>{bootstrap.repo_id}</p>
                  <p className="truncate" title={bootstrap.filename}>{bootstrap.filename}</p>
                  <p className="truncate" title={bootstrap.model_path}>{bootstrap.model_path}</p>
                  <p>
                    ctx {bootstrap.n_ctx} / batch {bootstrap.n_batch} / threads{" "}
                    {bootstrap.n_threads}
                  </p>
                </div>
                <Button
                  className="mt-3"
                  disabled={install.isPending}
                  onClick={() => install.mutate()}
                  size="sm"
                >
                  <DownloadIcon className="size-3.5" />
                  {install.isPending ? b.installing : b.installModel}
                </Button>
              </CardContent>
            </Card>

            <Card variant="compact">
              <CardHeader>
                <CardTitle>{b.semanticStore}</CardTitle>
                <CardAction>
                  <Badge variant="secondary" className="text-xs">
                    {bootstrap.documents} docs / {bootstrap.namespaces} ns
                  </Badge>
                </CardAction>
              </CardHeader>
              <CardContent>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <p>{b.vectorDb}</p>
                  <p>{bootstrap.vector_store_path}</p>
                  <p>
                    Embeddings:{" "}
                    {bootstrap.use_for_embeddings
                      ? b.embeddingsShared
                      : b.embeddingsDisabled}
                  </p>
                  <p>{b.indexedCorpusFiles}: {bootstrap.corpus_files.length}</p>
                </div>
              </CardContent>
            </Card>
          </div>

        </div>
      )}
    </SettingsSection>
  );
}
